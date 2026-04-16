import uuid
import hashlib
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Cohort, Submission, Answer, Extraction
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


@router.post("/submissions/start", response_model=StartSubmissionResponse)
async def start_submission(req: StartSubmissionRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cohort).where(Cohort.id == req.cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    client_ip = _get_client_ip(request)
    ip_hash = _hash_ip(client_ip)
    limit = cohort.max_submissions_per_ip or 1

    if limit > 0:
        completed_q = await db.execute(
            select(Submission).where(
                Submission.ip_hash == ip_hash,
                Submission.cohort_id == req.cohort_id,
                Submission.status == "completed",
            )
        )
        completed = completed_q.scalars().all()
        if len(completed) >= limit:
            raise HTTPException(
                status_code=429,
                detail="You have already submitted feedback for this course.",
            )

    # Return existing in-progress submission if found
    in_progress_q = await db.execute(
        select(Submission).where(
            Submission.ip_hash == ip_hash,
            Submission.cohort_id == req.cohort_id,
            Submission.status == "started",
        )
    )
    in_progress = in_progress_q.scalars().all()
    if in_progress:
        in_progress.sort(key=lambda s: s.created_at or datetime.min, reverse=True)
        return StartSubmissionResponse(submission_id=in_progress[0].id)

    submission = Submission(
        id=uuid.uuid4(),
        cohort_id=req.cohort_id,
        status="started",
        consent_version=req.consent_version,
        survey_version=cohort.active_version,
        ip_hash=ip_hash,
        client_metadata=req.client_metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(submission)
    await db.flush()

    return StartSubmissionResponse(submission_id=submission.id)


@router.post("/submissions/{submission_id}/answer", response_model=AnswerResponse)
async def save_answer(submission_id: uuid.UUID, req: AnswerRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    answer_raw = strip_pii(req.answer_raw)
    transcript = strip_pii(req.transcript)
    followup_1_answer = strip_pii(req.followup_1_answer) if req.followup_1_answer else None
    followup_2_answer = strip_pii(req.followup_2_answer) if req.followup_2_answer else None

    # Upsert answer for this question
    existing_q = await db.execute(
        select(Answer).where(
            Answer.submission_id == submission_id,
            Answer.question_id == req.question_id,
        )
    )
    existing = existing_q.scalar_one_or_none()

    if existing:
        answer_id = existing.id
        existing.answer_raw = answer_raw
        existing.transcript = transcript
        existing.question_type = req.question_type or existing.question_type
        existing.input_mode = req.input_mode or existing.input_mode
        existing.is_vague = req.is_vague
        existing.followups_asked = req.followups_asked if req.followups_asked is not None else existing.followups_asked
        existing.followup_1 = req.followup_1
        existing.followup_1_answer = followup_1_answer
        existing.followup_2 = req.followup_2
        existing.followup_2_answer = followup_2_answer
    else:
        answer_id = uuid.uuid4()
        answer = Answer(
            id=answer_id,
            submission_id=submission_id,
            question_id=req.question_id,
            question_type=req.question_type or "open",
            answer_raw=answer_raw,
            input_mode=req.input_mode or "none",
            transcript=transcript,
            is_vague=req.is_vague,
            followups_asked=req.followups_asked or 0,
            followup_1=req.followup_1,
            followup_1_answer=followup_1_answer,
            followup_2=req.followup_2,
            followup_2_answer=followup_2_answer,
        )
        db.add(answer)

    return AnswerResponse(id=answer_id, question_id=req.question_id)


def _build_answers_for_extraction(answers: list) -> list[dict]:
    result = []
    for a in answers:
        answer_data = {
            "question_id": a.question_id,
            "question_type": a.question_type,
            "answer": a.answer_raw,
        }
        if a.transcript:
            answer_data["transcript"] = a.transcript
        if a.followup_1_answer:
            answer_data["followup_1"] = a.followup_1
            answer_data["followup_1_answer"] = a.followup_1_answer
        if a.followup_2_answer:
            answer_data["followup_2"] = a.followup_2
            answer_data["followup_2_answer"] = a.followup_2_answer
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
async def preview_extraction(submission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    answers_q = await db.execute(select(Answer).where(Answer.submission_id == submission_id))
    answers = answers_q.scalars().all()
    answers_for_extraction = _build_answers_for_extraction(answers)

    extraction_data = None
    try:
        extraction_data = await extract_structured(answers_for_extraction)
    except Exception as e:
        logger.warning(f"Preview extraction failed for {submission_id}: {e}")
        extraction_data = dict(_EMPTY_EXTRACTION)

    return CompleteSubmissionResponse(status="preview", extraction=extraction_data)


@router.post("/submissions/{submission_id}/complete", response_model=CompleteSubmissionResponse)
async def complete_submission(submission_id: uuid.UUID, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    answers_q = await db.execute(select(Answer).where(Answer.submission_id == submission_id))
    answers = answers_q.scalars().all()
    answers_for_extraction = _build_answers_for_extraction(answers)

    extraction_data = None
    try:
        extraction_data = await extract_structured(answers_for_extraction)
    except Exception as e:
        logger.warning(f"Extraction failed for submission {submission_id}: {e}")
        extraction_data = dict(_EMPTY_EXTRACTION)

    now = datetime.now(timezone.utc)
    time_to_complete = None
    if sub.created_at:
        try:
            created = sub.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            time_to_complete = int((now - created).total_seconds())
        except Exception:
            pass

    sub.status = "completed"
    sub.completed_at = now
    sub.time_to_complete_sec = time_to_complete

    # Save extraction
    existing_ext = await db.execute(select(Extraction).where(Extraction.submission_id == submission_id))
    ext_row = existing_ext.scalar_one_or_none()
    if ext_row:
        ext_row.what_was_tried = extraction_data.get("what_was_tried")
        ext_row.planned_task_or_workflow = extraction_data.get("planned_task_or_workflow")
        ext_row.outcome_or_expected_outcome = extraction_data.get("outcome_or_expected_outcome")
        ext_row.barriers = extraction_data.get("barriers")
        ext_row.enablers = extraction_data.get("enablers")
        ext_row.public_benefit = extraction_data.get("public_benefit")
        ext_row.top_themes = extraction_data.get("top_themes")
        ext_row.success_story_candidate = extraction_data.get("success_story_candidate")
    else:
        ext = Extraction(
            submission_id=submission_id,
            what_was_tried=extraction_data.get("what_was_tried"),
            planned_task_or_workflow=extraction_data.get("planned_task_or_workflow"),
            outcome_or_expected_outcome=extraction_data.get("outcome_or_expected_outcome"),
            barriers=extraction_data.get("barriers"),
            enablers=extraction_data.get("enablers"),
            public_benefit=extraction_data.get("public_benefit"),
            top_themes=extraction_data.get("top_themes"),
            success_story_candidate=extraction_data.get("success_story_candidate"),
        )
        db.add(ext)

    # Qualtrics sync needs committed data (it opens its own session)
    await db.commit()

    # Qualtrics sync
    try:
        from app.services.qualtrics_service import sync_submission as qualtrics_sync
        qualtrics_result = await qualtrics_sync(submission_id)
        if not qualtrics_result.get("success") and qualtrics_result.get("error") != "Qualtrics not configured":
            logger.warning("Qualtrics sync failed for %s: %s", submission_id, qualtrics_result.get("error"))
    except Exception as e:
        logger.warning("Qualtrics sync error for %s: %s", submission_id, e)

    # Set duplicate-prevention cookie
    cohort_q = await db.execute(select(Cohort).where(Cohort.id == sub.cohort_id))
    cohort = cohort_q.scalar_one_or_none()
    if cohort and (cohort.max_submissions_per_ip or 0) > 0:
        cookie_name = f"submitted_{sub.cohort_id}"
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
async def save_experience_rating(submission_id: uuid.UUID, req: ExperienceRatingRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    sub.experience_rating = req.rating
    sub.experience_feedback = strip_pii(req.feedback_text) if req.feedback_text else None

    return {"status": "saved", "rating": req.rating}
