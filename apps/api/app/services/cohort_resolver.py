"""Resolve a cohort lookup key to a Cohort row.

The ``/c/<param>`` URL accepts either the cohort's UUID primary key or its
human-friendly slug (``generative-ai``). Routers should call
``resolve_cohort`` rather than ``db.get(Cohort, cohort_id)`` so both forms
work transparently. UUID lookups stay back-compatible with every link/QR
code that has ever been shared, slug lookups give us the pretty URL.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cohort


# Slug rules: lowercase letters, digits, and ``-``. 2-60 chars. Anchored.
# Same regex used by the admin endpoints when an editor types a slug, so the
# create path and the resolve path agree on what a "valid slug" looks like.
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$")


def is_valid_slug(value: str) -> bool:
    return bool(SLUG_RE.match(value))


def slugify(value: str) -> str:
    """Best-effort slug suggestion from a free-form survey name.

    Admin clients pre-fill the slug field with this, but the canonical
    validation lives in ``is_valid_slug``.
    """
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return cleaned[:60] if cleaned else ""


async def resolve_cohort(db: AsyncSession, key: str) -> Optional[Cohort]:
    """Return the Cohort matching ``key`` (UUID string or slug), or None.

    Tries UUID first because the primary key is indexed and most legacy
    callers still pass UUIDs. Falls back to slug only when ``key`` is not
    parseable as a UUID, which means slug lookups never compete with the
    primary-key index.
    """
    if not key:
        return None

    try:
        cohort_uuid = uuid.UUID(str(key))
    except (ValueError, TypeError, AttributeError):
        cohort_uuid = None

    if cohort_uuid is not None:
        cohort = await db.get(Cohort, cohort_uuid)
        if cohort is not None:
            return cohort
        # Fall through — a UUID-shaped string that doesn't resolve in the
        # DB might still match a slug (extremely unlikely given the regex,
        # but cheap to attempt).

    if not is_valid_slug(str(key)):
        return None

    result = await db.execute(select(Cohort).where(Cohort.slug == key))
    return result.scalar_one_or_none()
