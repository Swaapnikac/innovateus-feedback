import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Cohort

router = APIRouter()

SURVEY_CONFIG_DIR = Path(__file__).resolve().parents[4] / "docs" / "survey-config"


def _load_default_survey() -> dict:
    path = SURVEY_CONFIG_DIR / "survey-en.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/survey/{cohort_id}")
async def get_survey(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cohort = await db.get(Cohort, cohort_id)

    config = cohort.survey_config if cohort else None
    if not config:
        try:
            config = _load_default_survey()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Survey configuration not found")

    return {"cohort_id": str(cohort_id), "survey": config}
