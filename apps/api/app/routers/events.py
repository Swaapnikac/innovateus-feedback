import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response, status
from app.dynamo import get_events_table
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
def track_events(req: TrackEventsRequest, request: Request):
    table = get_events_table()
    ip_hash = _hash_ip(_get_client_ip(request))
    now = datetime.now(timezone.utc).isoformat()

    with table.batch_writer() as batch:
        for evt in req.events:
            ts = evt.timestamp or now
            batch.put_item(Item={
                "pk": f"SESSION#{req.session_token}",
                "sk": f"EVT#{ts}#{evt.event_type}",
                "gsi1_pk": f"COHORT#{req.cohort_id}" if req.cohort_id else "COHORT#unknown",
                "gsi1_sk": f"{evt.event_type}#{ts}",
                "session_token": req.session_token,
                "cohort_id": req.cohort_id or "",
                "submission_id": req.submission_id or "",
                "event_type": evt.event_type,
                "event_data": evt.event_data,
                "timestamp": ts,
                "ip_hash": ip_hash,
            })

    return {"status": "accepted", "count": len(req.events)}


@router.post("/events/dropout", status_code=status.HTTP_202_ACCEPTED)
def track_dropout(req: DropoutRequest, request: Request):
    table = get_events_table()
    ip_hash = _hash_ip(_get_client_ip(request))
    now = datetime.now(timezone.utc).isoformat()

    table.put_item(Item={
        "pk": f"SESSION#{req.session_token}",
        "sk": f"EVT#{now}#question_dropout",
        "gsi1_pk": f"COHORT#{req.cohort_id}",
        "gsi1_sk": f"question_dropout#{now}",
        "session_token": req.session_token,
        "cohort_id": req.cohort_id,
        "submission_id": req.submission_id or "",
        "event_type": "question_dropout",
        "event_data": {
            "last_question_id": req.last_question_id,
            "questions_answered": req.questions_answered,
        },
        "timestamp": now,
        "ip_hash": ip_hash,
    })

    return {"status": "accepted"}
