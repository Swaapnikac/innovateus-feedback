"""Qualtrics integration — push completed submissions via Response Import API.

Thin HTTP layer on top of :mod:`app.services.qualtrics_mapper`. The mapper
owns all formatting decisions (combined open answers, voice/text indicator,
recodes, target resolution); this module owns *only* the network call and
the per-submission sync-health bookkeeping that S8 ("Qualtrics sync
reliability >95%") reads off the submission row.

Sync-health fields written here:

- qualtrics_sync_attempt_count
- qualtrics_sync_first_attempt_at / qualtrics_sync_last_attempt_at
- qualtrics_sync_last_error
- qualtrics_sync_latency_ms
- qualtrics_response_id
- qualtrics_synced_at
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import get_settings
from app.services import qualtrics_mapper
from app.services.qualtrics_mapper import (
    MissingQualtricsMappingError,
    PAYLOAD_VERSION,
    QualtricsConfigError,
    ResolvedTarget,
)

# Re-exported for callers (export_service uses PAYLOAD_VERSION).
__all__ = ["sync_submission", "PAYLOAD_VERSION"]

logger = logging.getLogger(__name__)


# Survey-config loader — used when a cohort row has no embedded
# survey_config (older cohorts created before the JSONB column existed).
_DEFAULT_SURVEY_PATH = Path(__file__).resolve().parents[4] / "docs" / "survey-config" / "survey-en.json"


def _load_default_questions() -> list[dict]:
    import json

    try:
        with open(_DEFAULT_SURVEY_PATH, "r", encoding="utf-8") as f:
            return list((json.load(f) or {}).get("questions") or [])
    except FileNotFoundError:
        return []


def _questions_from_cohort(cohort) -> list[dict]:
    if cohort is not None and isinstance(cohort.survey_config, dict):
        qs = cohort.survey_config.get("questions")
        if isinstance(qs, list) and qs:
            return qs
    return _load_default_questions()


async def _post_response(payload: dict, target: ResolvedTarget) -> tuple[bool, str | None, str | None]:
    """POST to the Qualtrics Response Import endpoint. Returns (ok, error, response_id)."""
    settings = get_settings()
    url = (
        f"https://{target.datacenter_id}.qualtrics.com"
        f"/API/v3/surveys/{target.survey_id}/responses"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={
                "X-API-TOKEN": settings.qualtrics_api_token,
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code in (200, 201):
        try:
            response_id = response.json().get("result", {}).get("responseId")
        except ValueError:
            response_id = None
        return True, None, response_id

    body = response.text
    if len(body) > 500:
        body = body[:500] + "…(truncated)"
    return False, f"Qualtrics API returned {response.status_code}: {body}", None


async def sync_submission(submission_id: uuid.UUID, force: bool = False) -> dict:
    """Sync one completed submission to its cohort's Qualtrics target.

    Returns ``{"success": bool, "error": str | None}``. The submission row's
    sync-health columns are updated regardless of outcome (so the dashboard
    can show progress) unless the call fails before we even reach the DB.
    """
    settings = get_settings()
    if not qualtrics_mapper.is_token_configured(settings):
        logger.info("qualtrics.config.skip token_missing submission_id=%s", submission_id)
        return {"success": False, "error": "Qualtrics API token not configured"}

    from sqlalchemy import select
    from app.db import async_session
    from app.models import Answer, Cohort, Submission

    try:
        async with async_session() as db:
            sub = (await db.execute(select(Submission).where(Submission.id == submission_id))).scalar_one_or_none()
            if sub is None:
                return {"success": False, "error": "Submission not found"}
            if sub.status != "completed":
                return {"success": False, "error": "Submission not completed"}
            if sub.qualtrics_synced_at and not force:
                return {"success": True, "error": None}

            cohort = (await db.execute(select(Cohort).where(Cohort.id == sub.cohort_id))).scalar_one_or_none()

            try:
                target = qualtrics_mapper.resolve_target(cohort, settings=settings)
            except QualtricsConfigError as exc:
                logger.warning(
                    "qualtrics.config.error submission_id=%s cohort_id=%s reason=%s",
                    submission_id, sub.cohort_id, exc,
                )
                _record_failure(sub, str(exc))
                await db.commit()
                return {"success": False, "error": str(exc)}

            answers = (
                await db.execute(select(Answer).where(Answer.submission_id == submission_id))
            ).scalars().all()
            questions = _questions_from_cohort(cohort)

            try:
                payload = qualtrics_mapper.build_qualtrics_payload(
                    submission=sub,
                    answers=answers,
                    cohort=cohort,
                    questions=questions,
                    target=target,
                )
            except MissingQualtricsMappingError as exc:
                logger.warning(
                    "qualtrics.mapping.missing submission_id=%s target=%s reason=%s",
                    submission_id, target.name, exc,
                )
                _record_failure(sub, f"Mapping incomplete: {exc}")
                await db.commit()
                return {"success": False, "error": f"Mapping incomplete: {exc}"}

            attempt_started = datetime.now(timezone.utc)
            attempt_monotonic = time.monotonic()
            sub.qualtrics_sync_attempt_count = (sub.qualtrics_sync_attempt_count or 0) + 1
            if sub.qualtrics_sync_first_attempt_at is None:
                sub.qualtrics_sync_first_attempt_at = attempt_started
            sub.qualtrics_sync_last_attempt_at = attempt_started

            logger.info(
                "qualtrics.sync.start submission_id=%s cohort_id=%s target=%s survey_id=%s",
                submission_id, sub.cohort_id, target.name, target.survey_id,
            )

            ok, error, response_id = await _post_response(payload, target)
            latency_ms = int((time.monotonic() - attempt_monotonic) * 1000)
            sub.qualtrics_sync_latency_ms = latency_ms

            if ok:
                sub.qualtrics_synced_at = datetime.now(timezone.utc)
                sub.qualtrics_sync_last_error = None
                if response_id:
                    sub.qualtrics_response_id = response_id
                logger.info(
                    "qualtrics.sync.success submission_id=%s response_id=%s latency_ms=%d",
                    submission_id, response_id, latency_ms,
                )
                await db.commit()
                return {"success": True, "error": None, "qualtrics_response_id": response_id}

            sub.qualtrics_sync_last_error = (error or "")[:1000]
            logger.warning(
                "qualtrics.sync.failure submission_id=%s latency_ms=%d error=%s",
                submission_id, latency_ms, sub.qualtrics_sync_last_error,
            )
            await db.commit()
            return {"success": False, "error": error}

    except Exception as exc:
        error_msg = f"Unexpected error: {exc}"
        logger.exception("qualtrics.sync.crash submission_id=%s", submission_id)
        # Best-effort: record the failure so it shows up on the dashboard.
        try:
            async with async_session() as db:
                sub = (await db.execute(select(Submission).where(Submission.id == submission_id))).scalar_one_or_none()
                if sub is not None:
                    _record_failure(sub, error_msg)
                    await db.commit()
        except Exception:
            pass
        return {"success": False, "error": error_msg}


def _record_failure(sub, message: str) -> None:
    """Stamp a failed sync attempt onto the submission row."""
    now_ts = datetime.now(timezone.utc)
    sub.qualtrics_sync_attempt_count = (sub.qualtrics_sync_attempt_count or 0) + 1
    if sub.qualtrics_sync_first_attempt_at is None:
        sub.qualtrics_sync_first_attempt_at = now_ts
    sub.qualtrics_sync_last_attempt_at = now_ts
    sub.qualtrics_sync_last_error = (message or "")[:1000]
