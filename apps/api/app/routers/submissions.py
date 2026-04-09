import uuid
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Request, Response
from boto3.dynamodb.conditions import Key, Attr
from app.dynamo import get_submissions_table, get_surveys_table, query_all_items, scan_all_items
from app.schemas import (
    StartSubmissionRequest,
    StartSubmissionResponse,
    AnswerRequest,
    AnswerResponse,
    CompleteSubmissionResponse,
    ExperienceRatingRequest,
)
from app.services.ai_service import extract_structured
from app.services.pii_service import strip_pii
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _hash_ip(ip: str) -> str:
    salt = get_settings().jwt_secret
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/submissions/start", response_model=StartSubmissionResponse)
def start_submission(req: StartSubmissionRequest, request: Request):
    surveys_table = get_surveys_table()
    subs_table = get_submissions_table()

    # Get cohort metadata
    cohort_result = surveys_table.get_item(
        Key={"pk": f"COHORT#{req.cohort_id}", "sk": "METADATA"}
    )
    cohort = cohort_result.get("Item")
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    client_ip = _get_client_ip(request)
    ip_hash = _hash_ip(client_ip)
    limit = int(cohort.get("max_submissions_per_ip", 1))

    # Check for duplicate completed submissions using GSI
    if limit > 0:
        completed = query_all_items(
            subs_table,
            IndexName="IpHashIndex",
            KeyConditionExpression=Key("ip_hash").eq(ip_hash),
            FilterExpression=Attr("cohort_id").eq(str(req.cohort_id)) & Attr("status").eq("completed"),
        )
        if len(completed) >= limit:
            raise HTTPException(
                status_code=429,
                detail="You have already submitted feedback for this course.",
            )

    # Check for existing in-progress submission
    all_for_ip = query_all_items(
        subs_table,
        IndexName="IpHashIndex",
        KeyConditionExpression=Key("ip_hash").eq(ip_hash),
        FilterExpression=Attr("cohort_id").eq(str(req.cohort_id)) & Attr("status").eq("started"),
    )
    if all_for_ip:
        # Return most recent started submission
        all_for_ip.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        existing_id = all_for_ip[0]["submission_id"]
        return StartSubmissionResponse(submission_id=uuid.UUID(existing_id))

    # Create new submission
    submission_id = str(uuid.uuid4())
    now = _now_iso()
    subs_table.put_item(Item={
        "pk": f"COHORT#{req.cohort_id}",
        "sk": f"SUB#{submission_id}",
        "submission_id": submission_id,
        "cohort_id": str(req.cohort_id),
        "created_at": now,
        "completed_at": None,
        "status": "started",
        "time_to_complete_sec": None,
        "consent_version": req.consent_version,
        "survey_version": cohort.get("active_version"),
        "ip_hash": ip_hash,
        "client_metadata": req.client_metadata,
        "answers": [],
        "extraction": None,
        "jotform_synced_at": None,
        "qualtrics_synced_at": None,
    })

    return StartSubmissionResponse(submission_id=uuid.UUID(submission_id))


@router.post("/submissions/{submission_id}/answer", response_model=AnswerResponse)
def save_answer(submission_id: uuid.UUID, req: AnswerRequest):
    subs_table = get_submissions_table()
    sub_id_str = str(submission_id)

    # Find submission by scanning
    items = scan_all_items(
        subs_table,
        FilterExpression=Attr("submission_id").eq(sub_id_str),
    )
    if not items:
        raise HTTPException(status_code=404, detail="Submission not found")

    item = items[0]
    answers = item.get("answers", [])

    # Build answer data with PII stripped
    answer_data = req.model_dump()
    answer_data["answer_raw"] = strip_pii(answer_data.get("answer_raw"))
    answer_data["transcript"] = strip_pii(answer_data.get("transcript"))
    answer_data["followup_1_answer"] = strip_pii(answer_data.get("followup_1_answer"))
    answer_data["followup_2_answer"] = strip_pii(answer_data.get("followup_2_answer"))
    answer_id = None

    # Check if answer for this question already exists
    for i, a in enumerate(answers):
        if a.get("question_id") == req.question_id:
            answer_id = a.get("id")
            # Update existing answer
            for field, value in answer_data.items():
                if value is not None:
                    a[field] = value
            answers[i] = a
            break
    else:
        # New answer
        answer_id = str(uuid.uuid4())
        answer_data["id"] = answer_id
        answers.append(answer_data)

    # Write back
    subs_table.update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression="SET answers = :a",
        ExpressionAttributeValues={":a": answers},
    )

    return AnswerResponse(id=uuid.UUID(answer_id), question_id=req.question_id)


def _build_answers_for_extraction(answers: list[dict]) -> list[dict]:
    """Build the answer payload for AI extraction from stored answer records."""
    result = []
    for a in answers:
        answer_data = {
            "question_id": a.get("question_id"),
            "question_type": a.get("question_type"),
            "answer": a.get("answer_raw"),
        }
        if a.get("transcript"):
            answer_data["transcript"] = a["transcript"]
        if a.get("followup_1_answer"):
            answer_data["followup_1"] = a.get("followup_1")
            answer_data["followup_1_answer"] = a["followup_1_answer"]
        if a.get("followup_2_answer"):
            answer_data["followup_2"] = a.get("followup_2")
            answer_data["followup_2_answer"] = a["followup_2_answer"]
        result.append(answer_data)
    return result


_EMPTY_EXTRACTION = {
    "what_was_tried": None,
    "planned_task_or_workflow": None,
    "outcome_or_expected_outcome": None,
    "barriers": [],
    "enablers": [],
    "public_benefit": None,
    "top_themes": [],
    "success_story_candidate": None,
}


@router.post("/submissions/{submission_id}/preview-extraction", response_model=CompleteSubmissionResponse)
async def preview_extraction(submission_id: uuid.UUID):
    """Run AI extraction without marking submission as completed."""
    subs_table = get_submissions_table()
    sub_id_str = str(submission_id)

    items = scan_all_items(
        subs_table,
        FilterExpression=Attr("submission_id").eq(sub_id_str),
    )
    if not items:
        raise HTTPException(status_code=404, detail="Submission not found")

    item = items[0]
    answers_for_extraction = _build_answers_for_extraction(item.get("answers", []))

    extraction_data = None
    try:
        extraction_data = await extract_structured(answers_for_extraction)
    except Exception as e:
        logger.warning(f"Preview extraction failed for {submission_id}: {e}")
        extraction_data = dict(_EMPTY_EXTRACTION)

    return CompleteSubmissionResponse(status="preview", extraction=extraction_data)


@router.post("/submissions/{submission_id}/complete", response_model=CompleteSubmissionResponse)
async def complete_submission(submission_id: uuid.UUID, response: Response):
    subs_table = get_submissions_table()
    surveys_table = get_surveys_table()
    sub_id_str = str(submission_id)

    # Find submission
    items = scan_all_items(
        subs_table,
        FilterExpression=Attr("submission_id").eq(sub_id_str),
    )
    if not items:
        raise HTTPException(status_code=404, detail="Submission not found")

    item = items[0]
    answers_for_extraction = _build_answers_for_extraction(item.get("answers", []))

    # Run AI extraction
    extraction_data = None
    try:
        extraction_data = await extract_structured(answers_for_extraction)
    except Exception as e:
        logger.warning(f"Extraction failed for submission {submission_id}: {e}")
        extraction_data = dict(_EMPTY_EXTRACTION)

    now = _now_iso()
    created_at = item.get("created_at", now)
    try:
        created_dt = datetime.fromisoformat(created_at)
        now_dt = datetime.now(timezone.utc)
        time_to_complete = int((now_dt - created_dt).total_seconds())
    except (ValueError, TypeError):
        time_to_complete = None

    # Update submission with completion data
    subs_table.update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression=(
            "SET #s = :status, completed_at = :completed, "
            "time_to_complete_sec = :ttc, extraction = :ext"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "completed",
            ":completed": now,
            ":ttc": time_to_complete,
            ":ext": extraction_data,
        },
    )

    # Qualtrics sync
    try:
        from app.services.qualtrics_service import sync_submission as qualtrics_sync
        qualtrics_result = await qualtrics_sync(submission_id)
        if not qualtrics_result.get("success") and qualtrics_result.get("error") != "Qualtrics not configured":
            logger.warning("Qualtrics sync failed for %s: %s", submission_id, qualtrics_result.get("error"))
    except Exception as e:
        logger.warning("Qualtrics sync error for %s: %s", submission_id, e)

    # Set duplicate-prevention cookie
    cohort_id = item.get("cohort_id")
    cohort_result = surveys_table.get_item(
        Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"}
    )
    cohort = cohort_result.get("Item")
    if cohort and int(cohort.get("max_submissions_per_ip", 0)) > 0:
        cookie_name = f"submitted_{cohort_id}"
        response.set_cookie(
            key=cookie_name,
            value="1",
            httponly=True,
            secure=get_settings().environment != "development",
            samesite="lax",
            max_age=30 * 24 * 3600,
        )

    return CompleteSubmissionResponse(status="completed", extraction=extraction_data)


@router.post("/submissions/{submission_id}/experience-rating")
def save_experience_rating(submission_id: uuid.UUID, req: ExperienceRatingRequest):
    subs_table = get_submissions_table()
    sub_id_str = str(submission_id)

    items = scan_all_items(
        subs_table,
        FilterExpression=Attr("submission_id").eq(sub_id_str),
    )
    if not items:
        raise HTTPException(status_code=404, detail="Submission not found")

    item = items[0]
    feedback_text = strip_pii(req.feedback_text) if req.feedback_text else None

    subs_table.update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression="SET experience_rating = :r, experience_feedback = :f",
        ExpressionAttributeValues={
            ":r": req.rating,
            ":f": feedback_text,
        },
    )

    return {"status": "saved", "rating": req.rating}
