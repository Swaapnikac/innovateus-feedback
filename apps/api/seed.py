"""Seed script to create a default cohort in PostgreSQL for development."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from app.config import get_settings
from app.db import async_session
from app.models import Cohort, SurveyConfigVersion

DEFAULT_COHORT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SURVEY_CONFIG_PATH = Path(__file__).resolve().parents[2] / "docs" / "survey-config" / "survey-en.json"


def _load_default_survey() -> dict:
    with open(SURVEY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def seed():
    get_settings()
    default_survey = _load_default_survey()
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        result = await session.execute(select(Cohort).where(Cohort.id == DEFAULT_COHORT_ID))
        existing = result.scalar_one_or_none()

        if not existing:
            cohort = Cohort(
                id=DEFAULT_COHORT_ID,
                name="Pilot Cohort 1",
                course_name="Generative AI for Government",
                survey_config=default_survey,
                active_version="v1",
                max_submissions_per_ip=1,
                created_at=now,
            )
            session.add(cohort)

            version = SurveyConfigVersion(
                cohort_id=DEFAULT_COHORT_ID,
                version_label="v1",
                config=default_survey,
                change_summary="Initial survey configuration",
                created_by="seed",
                created_at=now,
            )
            session.add(version)
            await session.commit()
            print(f"Seeded cohort: Pilot Cohort 1 ({DEFAULT_COHORT_ID})")
        else:
            existing.survey_config = default_survey
            await session.commit()
            print(f"Updated survey_config for: {existing.name}")


if __name__ == "__main__":
    asyncio.run(seed())
