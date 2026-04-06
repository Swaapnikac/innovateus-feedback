import json
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from boto3.dynamodb.conditions import Key
from app.dynamo import get_surveys_table, query_all_items, DecimalEncoder, decimals_to_native
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

    old_groups = json.dumps(old_config.get("question_groups", []), sort_keys=True, cls=DecimalEncoder)
    new_groups = json.dumps(new_config.get("question_groups", []), sort_keys=True, cls=DecimalEncoder)
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
        elif json.dumps(oq.get("options"), sort_keys=True, cls=DecimalEncoder) != json.dumps(nq.get("options"), sort_keys=True, cls=DecimalEncoder):
            changes.append(f"Changed options: {qid}")
        elif oq.get("group") != nq.get("group"):
            changes.append(f"Changed group: {qid}")

    old_order = [q["id"] for q in old_config.get("questions", [])]
    new_order = [q["id"] for q in new_config.get("questions", [])]
    if old_order != new_order and not added and not removed:
        changes.append("Reordered questions")

    return "; ".join(changes) if changes else ""


def _strip_none(obj):
    """Recursively remove None values from dicts so DynamoDB round-trips compare equal."""
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none(i) for i in obj]
    return obj


def _configs_equal(a: dict | None, b: dict) -> bool:
    """Deep-compare two configs, ignoring key order and None fields."""
    if a is None:
        return False
    a_clean = _strip_none(decimals_to_native(a))
    b_clean = _strip_none(decimals_to_native(b))
    return json.dumps(a_clean, sort_keys=True, cls=DecimalEncoder) == json.dumps(b_clean, sort_keys=True, cls=DecimalEncoder)


def _count_versions(table, cohort_id: uuid.UUID) -> int:
    versions = query_all_items(
        table,
        KeyConditionExpression=Key("pk").eq(f"COHORT#{cohort_id}") & Key("sk").begins_with("VERSION#"),
    )
    return len(versions)


def _next_version_label(table, cohort_id: uuid.UUID) -> str:
    count = _count_versions(table, cohort_id)
    return f"v{count + 1}"


@router.post("/editor/login", response_model=AdminLoginResponse)
def editor_login(req: EditorLoginRequest, response: Response):
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
        samesite="none" if settings.environment != "development" else "lax",
        max_age=86400,
    )
    return AdminLoginResponse(token=token)


@router.get("/editor/cohorts", dependencies=[Depends(require_editor)])
def editor_list_cohorts():
    """List cohorts — accessible with editor credentials."""
    from app.dynamo import scan_all_items
    from boto3.dynamodb.conditions import Attr
    table = get_surveys_table()
    results = scan_all_items(table, FilterExpression=Attr("sk").eq("METADATA"))
    cohorts = sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)
    return [
        {
            "id": c["cohort_id"],
            "name": c["name"],
            "course_name": c["course_name"],
            "max_submissions_per_ip": int(c.get("max_submissions_per_ip", 1)),
            "created_at": c["created_at"],
        }
        for c in cohorts
    ]


@router.get("/editor/survey/{cohort_id}", dependencies=[Depends(require_editor)])
def get_editor_survey(cohort_id: uuid.UUID):
    table = get_surveys_table()
    result = table.get_item(Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"})
    cohort = result.get("Item")
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    config = decimals_to_native(cohort.get("survey_config"))
    if not config:
        try:
            config = _load_default_survey()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="No survey configuration found")

    return {
        "cohort_id": str(cohort_id),
        "survey": config,
        "active_version": cohort.get("active_version"),
    }


@router.put("/editor/survey/{cohort_id}", dependencies=[Depends(require_editor)])
def save_editor_survey(cohort_id: uuid.UUID, req: SaveSurveyRequest):
    table = get_surveys_table()
    result = table.get_item(Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"})
    cohort = result.get("Item")
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    new_config = req.model_dump()

    if _configs_equal(decimals_to_native(cohort.get("survey_config")), new_config):
        return {
            "status": "no_changes",
            "cohort_id": str(cohort_id),
            "version_label": cohort.get("active_version"),
        }

    change_summary = _compute_change_summary(decimals_to_native(cohort.get("survey_config")), new_config)
    version_label = _next_version_label(table, cohort_id)
    now = datetime.utcnow().isoformat()

    # Create version record
    table.put_item(Item={
        "pk": f"COHORT#{cohort_id}",
        "sk": f"VERSION#{version_label}",
        "cohort_id": str(cohort_id),
        "version_label": version_label,
        "config": new_config,
        "change_summary": change_summary or None,
        "created_by": "editor",
        "created_at": now,
    })

    # Update cohort metadata
    table.update_item(
        Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"},
        UpdateExpression="SET survey_config = :config, active_version = :ver",
        ExpressionAttributeValues={":config": new_config, ":ver": version_label},
    )

    return {
        "status": "saved",
        "cohort_id": str(cohort_id),
        "version_label": version_label,
        "change_summary": change_summary,
    }


@router.get("/editor/survey/{cohort_id}/versions", dependencies=[Depends(require_editor)])
def list_versions(
    cohort_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    table = get_surveys_table()

    # Check cohort exists
    cohort_result = table.get_item(Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"})
    cohort = cohort_result.get("Item")
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    # Get all versions
    versions = query_all_items(
        table,
        KeyConditionExpression=Key("pk").eq(f"COHORT#{cohort_id}") & Key("sk").begins_with("VERSION#"),
    )
    versions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    total = len(versions)
    start_idx = (page - 1) * page_size
    page_items = versions[start_idx:start_idx + page_size]

    return {
        "items": [
            SurveyVersionSummary(
                version_label=v["version_label"],
                change_summary=v.get("change_summary"),
                created_at=datetime.fromisoformat(v["created_at"]),
                created_by=v.get("created_by", "editor"),
            )
            for v in page_items
        ],
        "total": total,
        "active_version": cohort.get("active_version"),
    }


@router.get(
    "/editor/survey/{cohort_id}/versions/{version_label}",
    response_model=SurveyVersionDetail,
    dependencies=[Depends(require_editor)],
)
def get_version(cohort_id: uuid.UUID, version_label: str):
    table = get_surveys_table()
    result = table.get_item(
        Key={"pk": f"COHORT#{cohort_id}", "sk": f"VERSION#{version_label}"}
    )
    version = result.get("Item")
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return SurveyVersionDetail(
        version_label=version["version_label"],
        change_summary=version.get("change_summary"),
        created_at=datetime.fromisoformat(version["created_at"]),
        created_by=version.get("created_by", "editor"),
        config=decimals_to_native(version["config"]),
    )


@router.post(
    "/editor/survey/{cohort_id}/versions/{version_label}/restore",
    dependencies=[Depends(require_editor)],
)
def restore_version(cohort_id: uuid.UUID, version_label: str):
    table = get_surveys_table()

    # Check cohort
    cohort_result = table.get_item(Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"})
    cohort = cohort_result.get("Item")
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    # Get old version
    version_result = table.get_item(
        Key={"pk": f"COHORT#{cohort_id}", "sk": f"VERSION#{version_label}"}
    )
    old_version = version_result.get("Item")
    if not old_version:
        raise HTTPException(status_code=404, detail="Version not found")

    new_label = _next_version_label(table, cohort_id)
    now = datetime.utcnow().isoformat()

    # Create new version from restored config
    table.put_item(Item={
        "pk": f"COHORT#{cohort_id}",
        "sk": f"VERSION#{new_label}",
        "cohort_id": str(cohort_id),
        "version_label": new_label,
        "config": old_version["config"],
        "change_summary": f"Restored from {version_label}",
        "created_by": "editor",
        "created_at": now,
    })

    # Update cohort metadata
    table.update_item(
        Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"},
        UpdateExpression="SET survey_config = :config, active_version = :ver",
        ExpressionAttributeValues={":config": old_version["config"], ":ver": new_label},
    )

    return {
        "status": "restored",
        "cohort_id": str(cohort_id),
        "version_label": new_label,
        "restored_from": version_label,
    }
