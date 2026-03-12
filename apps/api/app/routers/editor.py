import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Cohort
from app.schemas import EditorLoginRequest, AdminLoginResponse, SaveSurveyRequest
from app.auth import verify_password, create_access_token, require_editor
from app.config import get_settings

router = APIRouter()

SURVEY_CONFIG_DIR = Path(__file__).resolve().parents[4] / "docs" / "survey-config"


def _load_default_survey() -> dict:
    path = SURVEY_CONFIG_DIR / "survey-en.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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

    return {"cohort_id": str(cohort_id), "survey": config}


@router.put("/editor/survey/{cohort_id}", dependencies=[Depends(require_editor)])
async def save_editor_survey(
    cohort_id: uuid.UUID,
    req: SaveSurveyRequest,
    db: AsyncSession = Depends(get_db),
):
    cohort = await db.get(Cohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    cohort.survey_config = req.model_dump()
    await db.flush()
    return {"status": "saved", "cohort_id": str(cohort_id)}
