"""Seed script to create a default cohort for development."""
import json
import uuid
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings
from app.models import Cohort
from app.db import Base

DEFAULT_COHORT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SURVEY_CONFIG_PATH = Path(__file__).resolve().parent.parent / "docs" / "survey-config" / "survey-en.json"


def _load_default_survey() -> dict:
    with open(SURVEY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    default_survey = _load_default_survey()

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        existing = await session.get(Cohort, DEFAULT_COHORT_ID)
        if not existing:
            cohort = Cohort(
                id=DEFAULT_COHORT_ID,
                name="Pilot Cohort 1",
                course_name="Generative AI for Government",
                survey_config=default_survey,
            )
            session.add(cohort)
            await session.commit()
            print(f"Seeded cohort: {cohort.name} ({cohort.id})")
        else:
            if not existing.survey_config:
                existing.survey_config = default_survey
                await session.commit()
                print(f"Populated survey_config for: {existing.name}")
            else:
                print(f"Cohort already exists: {existing.name}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
