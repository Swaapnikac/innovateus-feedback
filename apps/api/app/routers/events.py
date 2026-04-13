import hashlib
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Event
from app.schemas import TrackEventsRequest, DropoutRequest
from app.config import get_settings

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


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def track_events(req: TrackEventsRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_hash = _hash_ip(_get_client_ip(request))
    now = datetime.now(timezone.utc).isoformat()

    for evt in req.events:
        event = Event(
            id=uuid.uuid4(),
            session_token=req.session_token,
            cohort_id=req.cohort_id or "",
            submission_id=req.submission_id or "",
            event_type=evt.event_type,
            event_data=evt.event_data,
            ip_hash=ip_hash,
            timestamp=datetime.fromisoformat(evt.timestamp) if evt.timestamp else datetime.now(timezone.utc),
        )
        db.add(event)

    await db.flush()
    return {"status": "accepted", "count": len(req.events)}


@router.post("/events/dropout", status_code=status.HTTP_202_ACCEPTED)
async def track_dropout(req: DropoutRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip_hash = _hash_ip(_get_client_ip(request))

    event = Event(
        id=uuid.uuid4(),
        session_token=req.session_token,
        cohort_id=req.cohort_id or "",
        submission_id=req.submission_id or "",
        event_type="question_dropout",
        event_data={
            "last_question_id": req.last_question_id,
            "questions_answered": req.questions_answered,
        },
        ip_hash=ip_hash,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.flush()

    return {"status": "accepted"}
