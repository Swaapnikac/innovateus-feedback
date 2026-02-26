"""Seed script to create a default cohort for development."""
import uuid
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings
from app.models import Cohort
from app.db import Base

DEFAULT_COHORT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        existing = await session.get(Cohort, DEFAULT_COHORT_ID)
        if not existing:
            cohort = Cohort(
                id=DEFAULT_COHORT_ID,
                name="Pilot Cohort 1",
                course_name="Generative AI for Government",
                language_default="en",
            )
            session.add(cohort)
            await session.commit()
            print(f"Seeded cohort: {cohort.name} ({cohort.id})")
        else:
            print(f"Cohort already exists: {existing.name}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
