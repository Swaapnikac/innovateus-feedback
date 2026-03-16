import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db import get_db
from app.models import Cohort, SurveyConfigVersion
from app.schemas import (
    EditorLoginRequest,
    AdminLoginResponse,
    SaveSurveyRequest,
    SurveyVersionSummary,
    SurveyVersionDetail,
)
from app.auth import verify_password, create_access_token, require_editor
from app.config import get_settings

router = APIRouter()

SURVEY_CONFIG_DIR = Path(__file__).resolve().parents[4] / "docs" / "survey-config"


def _load_default_survey() -> dict:
    path = SURVEY_CONFIG_DIR / "survey-en.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compute_change_summary(old_config: dict | None, new_config: dict) -> str:
    """Generate a human-readable summary of what changed between two configs."""
    if not old_config:
        return "Initial version"

    changes: list[str] = []

    if old_config.get("title") != new_config.get("title"):
        changes.append("Changed survey title")

    old_groups = json.dumps(old_config.get("question_groups", []), sort_keys=True)
    new_groups = json.dumps(new_config.get("question_groups", []), sort_keys=True)
    if old_groups != new_groups:
        changes.append("Changed question groups")

    old_qs = {q["id"]: q for q in old_config.get("questions", [])}
    new_qs = {q["id"]: q for q in new_config.get("questions", [])}

    added = set(new_qs) - set(old_qs)
    removed = set(old_qs) - set(new_qs)
    common = set(old_qs) & set(new_qs)

    for qid in sorted(added):
        changes.append(f"Added: {qid}")
    for qid in sorted(removed):
        changes.append(f"Removed: {qid}")

    for qid in sorted(common):
        oq, nq = old_qs[qid], new_qs[qid]
        if oq.get("text") != nq.get("text"):
            changes.append(f"Changed text: {qid}")
        elif oq.get("type") != nq.get("type"):
            changes.append(f"Changed type: {qid}")
        elif json.dumps(oq.get("options"), sort_keys=True) != json.dumps(nq.get("options"), sort_keys=True):
            changes.append(f"Changed options: {qid}")
        elif oq.get("group") != nq.get("group"):
            changes.append(f"Changed group: {qid}")

    old_order = [q["id"] for q in old_config.get("questions", [])]
    new_order = [q["id"] for q in new_config.get("questions", [])]
    if old_order != new_order and not added and not removed:
        changes.append("Reordered questions")

    return "; ".join(changes) if changes else ""


def _configs_equal(a: dict | None, b: dict) -> bool:
    """Deep-compare two configs, ignoring key order."""
    if a is None:
        return False
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


async def _next_version_label(cohort_id: uuid.UUID, db: AsyncSession) -> str:
    result = await db.execute(
        select(func.count(SurveyConfigVersion.id)).where(
            SurveyConfigVersion.cohort_id == cohort_id
        )
    )
    count = result.scalar() or 0
    return f"v{count + 1}"


@router.post("/editor/login", response_model=AdminLoginResponse)
async def editor_login(req: EditorLoginRequest, response: Response):
    settings = get_settings()
    if not settings.editor_password_hash:
        raise HTTPException(status_code=500, detail="Editor password not configured")

    if not verify_password(req.password, settings.editor_password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_access_token({"sub": "editor", "role": "editor"})
    response.set_cookie(
        key="editor_token",
        value=token,
        httponly=True,
        secure=settings.environment != "development",
        samesite="lax",
        max_age=86400,
    )
    return AdminLoginResponse(token=token)


@router.get("/editor/survey/{cohort_id}", dependencies=[Depends(require_editor)])
async def get_editor_survey(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cohort = await db.get(Cohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    config = cohort.survey_config
    if not config:
        try:
            config = _load_default_survey()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="No survey configuration found")

    return {
        "cohort_id": str(cohort_id),
        "survey": config,
        "active_version": cohort.active_version,
    }


@router.put("/editor/survey/{cohort_id}", dependencies=[Depends(require_editor)])
async def save_editor_survey(
    cohort_id: uuid.UUID,
    req: SaveSurveyRequest,
    db: AsyncSession = Depends(get_db),
):
    cohort = await db.get(Cohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    new_config = req.model_dump()

    if _configs_equal(cohort.survey_config, new_config):
        return {
            "status": "no_changes",
            "cohort_id": str(cohort_id),
            "version_label": cohort.active_version,
        }

    change_summary = _compute_change_summary(cohort.survey_config, new_config)
    version_label = await _next_version_label(cohort_id, db)

    version = SurveyConfigVersion(
        cohort_id=cohort_id,
        version_label=version_label,
        config=new_config,
        change_summary=change_summary or None,
        created_by="editor",
    )
    db.add(version)

    cohort.survey_config = new_config
    cohort.active_version = version_label
    await db.flush()

    return {
        "status": "saved",
        "cohort_id": str(cohort_id),
        "version_label": version_label,
        "change_summary": change_summary,
    }


@router.get(
    "/editor/survey/{cohort_id}/versions",
    dependencies=[Depends(require_editor)],
)
async def list_versions(
    cohort_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    cohort = await db.get(Cohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    count_result = await db.execute(
        select(func.count(SurveyConfigVersion.id)).where(
            SurveyConfigVersion.cohort_id == cohort_id
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(SurveyConfigVersion)
        .where(SurveyConfigVersion.cohort_id == cohort_id)
        .order_by(SurveyConfigVersion.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    versions = result.scalars().all()

    return {
        "items": [
            SurveyVersionSummary.model_validate(v) for v in versions
        ],
        "total": total,
        "active_version": cohort.active_version,
    }


@router.get(
    "/editor/survey/{cohort_id}/versions/{version_label}",
    response_model=SurveyVersionDetail,
    dependencies=[Depends(require_editor)],
)
async def get_version(
    cohort_id: uuid.UUID,
    version_label: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SurveyConfigVersion).where(
            SurveyConfigVersion.cohort_id == cohort_id,
            SurveyConfigVersion.version_label == version_label,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return SurveyVersionDetail.model_validate(version)


@router.post(
    "/editor/survey/{cohort_id}/versions/{version_label}/restore",
    dependencies=[Depends(require_editor)],
)
async def restore_version(
    cohort_id: uuid.UUID,
    version_label: str,
    db: AsyncSession = Depends(get_db),
):
    cohort = await db.get(Cohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    result = await db.execute(
        select(SurveyConfigVersion).where(
            SurveyConfigVersion.cohort_id == cohort_id,
            SurveyConfigVersion.version_label == version_label,
        )
    )
    old_version = result.scalar_one_or_none()
    if not old_version:
        raise HTTPException(status_code=404, detail="Version not found")

    new_label = await _next_version_label(cohort_id, db)

    new_version = SurveyConfigVersion(
        cohort_id=cohort_id,
        version_label=new_label,
        config=old_version.config,
        change_summary=f"Restored from {version_label}",
        created_by="editor",
    )
    db.add(new_version)

    cohort.survey_config = old_version.config
    cohort.active_version = new_label
    await db.flush()

    return {
        "status": "restored",
        "cohort_id": str(cohort_id),
        "version_label": new_label,
        "restored_from": version_label,
    }
