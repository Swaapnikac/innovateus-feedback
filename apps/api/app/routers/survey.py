import json
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.schemas import SurveyConfig

router = APIRouter()

SURVEY_CONFIG_DIR = Path(__file__).resolve().parents[4] / "docs" / "survey-config"


def _load_survey(language: str) -> dict:
    path = SURVEY_CONFIG_DIR / f"survey-{language}.json"
    if not path.exists():
        path = SURVEY_CONFIG_DIR / "survey-en.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/survey/{cohort_id}")
async def get_survey(cohort_id: uuid.UUID, lang: str = "en"):
    try:
        config = _load_survey(lang)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Survey configuration not found")
    return {"cohort_id": str(cohort_id), "language": lang, "survey": config}
