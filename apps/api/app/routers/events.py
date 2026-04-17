"""Event ingestion endpoint.

Two jobs:

1. Store the raw event in the ``events`` table (auditable stream).
2. Denormalize interesting events directly onto the ``submissions`` and
   ``answers`` tables so the analytics dashboard and CSV exports do not have
   to aggregate from the events stream on every query. This is the single
   most important change for the Apr 22 soft launch because it makes almost
   every user-testing metric readable with a simple ``SELECT`` instead of a
   ``GROUP BY ... FROM events`` scan.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, status, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Answer, Event, Submission
from app.schemas import TrackEventsRequest, DropoutRequest, EventPayload
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _hash_ip(ip: str) -> str:
    salt = get_settings().jwt_secret
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _parse_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


async def _get_submission(db: AsyncSession, sid: Optional[uuid.UUID]) -> Optional[Submission]:
    if not sid:
        return None
    result = await db.execute(select(Submission).where(Submission.id == sid))
    return result.scalar_one_or_none()


async def _get_answer(db: AsyncSession, sid: Optional[uuid.UUID], question_id: Optional[str]) -> Optional[Answer]:
    if not sid or not question_id:
        return None
    result = await db.execute(
        select(Answer).where(
            Answer.submission_id == sid,
            Answer.question_id == question_id,
        )
    )
    return result.scalar_one_or_none()


async def _denormalize_event(
    db: AsyncSession,
    submission_id: Optional[uuid.UUID],
    evt: EventPayload,
    ts: datetime,
) -> None:
    """Write event payload to the right columns on submission/answer rows.

    Silent on failure — the raw event is always stored, so we can backfill
    later if denorm fails.
    """
    data = evt.event_data or {}
    etype = evt.event_type
    sub = await _get_submission(db, submission_id)
    if sub is not None:
        sub.last_activity_at = ts

    if etype == "survey_start" and sub is not None:
        mode = data.get("initial_mode") or data.get("mode")
        if mode in {"voice", "text"} and sub.started_in_voice is None:
            sub.started_in_voice = mode == "voice"
        return

    if etype == "question_started" and sub is not None:
        q_id = data.get("question_id")
        ans = await _get_answer(db, submission_id, q_id)
        if ans is None and q_id:
            ans = Answer(
                id=uuid.uuid4(),
                submission_id=submission_id,
                question_id=q_id,
                question_type=data.get("question_type") or "unknown",
                input_mode="none",
                answer_started_at=ts,
            )
            db.add(ans)
        elif ans is not None and ans.answer_started_at is None:
            ans.answer_started_at = ts
        return

    if etype == "question_answer" and sub is not None:
        q_id = data.get("question_id")
        ans = await _get_answer(db, submission_id, q_id)
        if ans is not None:
            ans.answer_completed_at = ts
            if ans.answer_started_at and ans.answer_duration_sec is None:
                started = ans.answer_started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                ans.answer_duration_sec = max(0, int((ts - started).total_seconds()))
        return

    if etype == "input_mode_switched" and sub is not None:
        from_mode = data.get("from")
        to_mode = data.get("to")
        q_id = data.get("question_id")
        ans = await _get_answer(db, submission_id, q_id) if q_id else None
        if from_mode == "voice" and to_mode == "text":
            sub.switched_voice_to_text_any = True
            if ans is not None:
                ans.switched_from_voice_to_text_flag = True
        elif from_mode == "text" and to_mode == "voice":
            sub.switched_text_to_voice_any = True
            if ans is not None:
                ans.switched_from_text_to_voice_flag = True
        return

    if etype == "transcript_edited" and sub is not None:
        q_id = data.get("question_id")
        ans = await _get_answer(db, submission_id, q_id) if q_id else None
        if ans is not None:
            ans.user_edited_transcript_flag = True
            if "edit_distance" in data:
                try:
                    ans.transcript_edit_distance = int(data["edit_distance"])
                except (TypeError, ValueError):
                    pass
        return

    if etype == "voice_recording_stopped" and sub is not None:
        q_id = data.get("question_id")
        ans = await _get_answer(db, submission_id, q_id) if q_id else None
        if ans is not None:
            try:
                if data.get("duration_sec") is not None:
                    ans.voice_duration_sec = int(data["duration_sec"])
            except (TypeError, ValueError):
                pass
            if data.get("silence_auto_stop"):
                ans.silence_auto_stop_triggered_flag = True
        return

    if etype == "mic_permission_result" and sub is not None:
        status_val = data.get("status")
        if status_val in {"granted", "denied", "prompt", "unknown"}:
            sub.mic_permission_status = status_val
            sub.mic_permission_prompted_at = ts
        return

    if etype == "audio_capture_error" and sub is not None:
        q_id = data.get("question_id")
        ans = await _get_answer(db, submission_id, q_id) if q_id else None
        if ans is not None:
            ans.audio_capture_error_flag = True
        sub.client_error_count = (sub.client_error_count or 0) + 1
        return

    if etype == "api_latency" and sub is not None:
        # Accept both ``duration_ms`` (frontend ``trackApiLatency`` payload)
        # and ``latency_ms`` (older name) so we don't silently record 0ms
        # for every call if the two diverge.
        raw_latency = data.get("duration_ms")
        if raw_latency is None:
            raw_latency = data.get("latency_ms")
        try:
            latency = max(0, int(raw_latency)) if raw_latency is not None else 0
        except (TypeError, ValueError):
            latency = 0
        ok = bool(data.get("ok", True))
        is_timeout = bool(data.get("timeout"))
        total_calls = (sub.total_api_calls or 0) + 1
        prev_avg = float(sub.avg_api_latency_ms or 0)
        # Running mean in float space; only cast to int at the end so we
        # don't accumulate truncation error across hundreds of calls.
        new_avg = ((prev_avg * (total_calls - 1)) + latency) / total_calls
        sub.total_api_calls = total_calls
        sub.avg_api_latency_ms = int(round(new_avg))
        sub.max_api_latency_ms = max(sub.max_api_latency_ms or 0, latency)
        if not ok:
            sub.total_api_failures = (sub.total_api_failures or 0) + 1
        if is_timeout:
            sub.timeout_count = (sub.timeout_count or 0) + 1
        return

    if etype == "client_error" and sub is not None:
        sub.client_error_count = (sub.client_error_count or 0) + 1
        if data.get("severity") == "critical":
            sub.critical_error_flag = True
        return

    if etype == "question_dropout" and sub is not None:
        last_q = data.get("last_question_id") or data.get("question_id")
        if last_q:
            sub.abandonment_stage = last_q
        return


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def track_events(req: TrackEventsRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_hash = _hash_ip(_get_client_ip(request))
    submission_uuid = _parse_uuid(req.submission_id)

    for evt in req.events:
        ts = (
            datetime.fromisoformat(evt.timestamp)
            if evt.timestamp
            else datetime.now(timezone.utc)
        )
        event = Event(
            id=uuid.uuid4(),
            session_token=req.session_token,
            cohort_id=req.cohort_id or None,
            submission_id=req.submission_id or None,
            event_type=evt.event_type,
            event_data=evt.event_data,
            ip_hash=ip_hash,
            timestamp=ts,
        )
        db.add(event)
        try:
            await _denormalize_event(db, submission_uuid, evt, ts)
        except Exception as exc:
            logger.debug("denormalize failed for %s: %s", evt.event_type, exc)

    return {"status": "accepted", "count": len(req.events)}


@router.post("/events/dropout", status_code=status.HTTP_202_ACCEPTED)
async def track_dropout(req: DropoutRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_hash = _hash_ip(_get_client_ip(request))
    ts = datetime.now(timezone.utc)

    event = Event(
        id=uuid.uuid4(),
        session_token=req.session_token,
        cohort_id=req.cohort_id or None,
        submission_id=req.submission_id or None,
        event_type="question_dropout",
        event_data={
            "last_question_id": req.last_question_id,
            "questions_answered": req.questions_answered,
        },
        ip_hash=ip_hash,
        timestamp=ts,
    )
    db.add(event)

    submission_uuid = _parse_uuid(req.submission_id)
    sub = await _get_submission(db, submission_uuid)
    if sub is not None:
        sub.abandonment_stage = req.last_question_id
        sub.last_activity_at = ts

    return {"status": "accepted"}
