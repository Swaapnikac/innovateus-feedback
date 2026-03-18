import uuid
import hashlib
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db import get_db
from app.models import Submission, Answer, Extraction, Cohort
from app.schemas import (
    StartSubmissionRequest,
    StartSubmissionResponse,
    AnswerRequest,
    AnswerResponse,
    CompleteSubmissionResponse,
)
from app.services.ai_service import extract_structured
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
async def start_submission(
    req: StartSubmissionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    cohort = await db.get(Cohort, req.cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    client_ip = _get_client_ip(request)
    ip_hash = _hash_ip(client_ip)
    limit = cohort.max_submissions_per_ip

    if limit > 0:
        cookie_name = f"submitted_{req.cohort_id}"
        if request.cookies.get(cookie_name):
            raise HTTPException(
                status_code=429,
                detail="You have already submitted feedback for this course.",
            )

        result = await db.execute(
            select(func.count(Submission.id)).where(
                Submission.cohort_id == req.cohort_id,
                Submission.ip_hash == ip_hash,
                Submission.status == "completed",
            )
        )
        completed_count = result.scalar() or 0

        if completed_count >= limit:
            raise HTTPException(
                status_code=429,
                detail="You have already submitted feedback for this course.",
            )

    existing = await db.execute(
        select(Submission).where(
            Submission.cohort_id == req.cohort_id,
            Submission.ip_hash == ip_hash,
            Submission.status == "started",
        ).order_by(Submission.created_at.desc()).limit(1)
    )
    existing_sub = existing.scalar_one_or_none()

    if existing_sub:
        return StartSubmissionResponse(submission_id=existing_sub.id)

    submission = Submission(
        cohort_id=req.cohort_id,
        consent_version=req.consent_version,
        survey_version=cohort.active_version,
        ip_hash=ip_hash,
        client_metadata=req.client_metadata,
    )
    db.add(submission)
    await db.flush()

    return StartSubmissionResponse(submission_id=submission.id)


@router.post("/submissions/{submission_id}/answer", response_model=AnswerResponse)
async def save_answer(
    submission_id: uuid.UUID, req: AnswerRequest, db: AsyncSession = Depends(get_db)
):
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    result = await db.execute(
        select(Answer).where(
            Answer.submission_id == submission_id,
            Answer.question_id == req.question_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        for field, value in req.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        await db.flush()
        return AnswerResponse(id=existing.id, question_id=existing.question_id)

    answer = Answer(submission_id=submission_id, **req.model_dump())
    db.add(answer)
    await db.flush()
    return AnswerResponse(id=answer.id, question_id=answer.question_id)


@router.post("/submissions/{submission_id}/complete", response_model=CompleteSubmissionResponse)
async def complete_submission(
    submission_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    result = await db.execute(
        select(Answer).where(Answer.submission_id == submission_id)
    )
    answers = result.scalars().all()

    answers_for_extraction = []
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
        answers_for_extraction.append(answer_data)

    extraction_data = None
    try:
        extraction_data = await extract_structured(answers_for_extraction)
    except Exception as e:
        logger.warning(f"Extraction failed for submission {submission_id}: {e}")
        extraction_data = {
            "what_was_tried": None,
            "planned_task_or_workflow": None,
            "outcome_or_expected_outcome": None,
            "barriers": [],
            "enablers": [],
            "public_benefit": None,
            "top_themes": [],
            "success_story_candidate": None,
        }

    existing_extraction = await db.get(Extraction, submission_id)
    if existing_extraction:
        for field, value in extraction_data.items():
            setattr(existing_extraction, field, value)
    else:
        extraction = Extraction(submission_id=submission_id, **extraction_data)
        db.add(extraction)

    now = datetime.utcnow()
    submission.status = "completed"
    submission.completed_at = now
    if submission.created_at:
        submission.time_to_complete_sec = int((now - submission.created_at).total_seconds())

    await db.flush()

    cohort = await db.get(Cohort, submission.cohort_id)
    if cohort and cohort.max_submissions_per_ip > 0:
        cookie_name = f"submitted_{submission.cohort_id}"
        response.set_cookie(
            key=cookie_name,
            value="1",
            httponly=True,
            secure=get_settings().environment != "development",
            samesite="lax",
            max_age=30 * 24 * 3600,
        )

    return CompleteSubmissionResponse(status="completed", extraction=extraction_data)
