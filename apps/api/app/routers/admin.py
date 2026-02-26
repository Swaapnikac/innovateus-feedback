import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.db import get_db
from app.models import Submission, Answer, Extraction, Cohort
from app.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    MetricsResponse,
    PaginatedResponses,
    SubmissionSummary,
    CohortResponse,
)
from app.auth import verify_password, create_access_token, require_admin
from app.config import get_settings
from app.services.export_service import (
    generate_raw_csv,
    generate_structured_csv,
    generate_summary_pdf,
    generate_summary_pptx,
)

router = APIRouter()


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(req: AdminLoginRequest, response: Response):
    settings = get_settings()
    if not settings.admin_password_hash:
        raise HTTPException(status_code=500, detail="Admin password not configured")

    if not verify_password(req.password, settings.admin_password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_access_token({"sub": "admin", "role": "manager"})
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=settings.environment != "development",
        samesite="lax",
        max_age=86400,
    )
    return AdminLoginResponse(token=token)


@router.get("/cohorts", dependencies=[Depends(require_admin)])
async def list_cohorts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cohort).order_by(Cohort.created_at.desc()))
    cohorts = result.scalars().all()
    return [CohortResponse.model_validate(c) for c in cohorts]


@router.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(require_admin)])
async def get_metrics(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    base_query = select(Submission)
    if cohort_id:
        base_query = base_query.where(Submission.cohort_id == cohort_id)
    if start:
        base_query = base_query.where(Submission.created_at >= start)
    if end:
        base_query = base_query.where(Submission.created_at <= end)

    result = await db.execute(base_query)
    submissions = result.scalars().all()

    total = len(submissions)
    completed = [s for s in submissions if s.status == "completed"]
    completion_rate = len(completed) / total if total > 0 else 0

    times = [s.time_to_complete_sec for s in completed if s.time_to_complete_sec]
    avg_time = sum(times) / len(times) if times else None

    answer_query = select(Answer).join(Submission).where(
        Answer.question_id == "q1_recommend"
    )
    if cohort_id:
        answer_query = answer_query.where(Submission.cohort_id == cohort_id)
    result = await db.execute(answer_query)
    recommend_answers = result.scalars().all()
    scores = []
    for a in recommend_answers:
        try:
            scores.append(int(a.answer_raw))
        except (ValueError, TypeError):
            pass
    avg_score = sum(scores) / len(scores) if scores else None

    confidence_query = select(Answer).join(Submission).where(
        Answer.question_id == "q2_confidence"
    )
    if cohort_id:
        confidence_query = confidence_query.where(Submission.cohort_id == cohort_id)
    result = await db.execute(confidence_query)
    confidence_answers = result.scalars().all()
    conf_dist: dict[str, int] = {}
    for a in confidence_answers:
        val = a.answer_raw or "Unknown"
        conf_dist[val] = conf_dist.get(val, 0) + 1

    open_query = select(Answer).join(Submission).where(Answer.question_type == "open")
    if cohort_id:
        open_query = open_query.where(Submission.cohort_id == cohort_id)
    result = await db.execute(open_query)
    open_answers = result.scalars().all()
    vague_count = sum(1 for a in open_answers if a.is_vague is True)
    vagueness_rate = vague_count / len(open_answers) if open_answers else None

    return MetricsResponse(
        total_submissions=total,
        completed_submissions=len(completed),
        completion_rate=round(completion_rate, 3),
        avg_time_to_complete_sec=round(avg_time, 1) if avg_time else None,
        avg_recommend_score=round(avg_score, 2) if avg_score else None,
        confidence_distribution=conf_dist,
        vagueness_rate=round(vagueness_rate, 3) if vagueness_rate is not None else None,
    )


@router.get("/responses", response_model=PaginatedResponses, dependencies=[Depends(require_admin)])
async def get_responses(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Submission)
    count_query = select(func.count(Submission.id))

    if cohort_id:
        query = query.where(Submission.cohort_id == cohort_id)
        count_query = count_query.where(Submission.cohort_id == cohort_id)
    if start:
        query = query.where(Submission.created_at >= start)
        count_query = count_query.where(Submission.created_at >= start)
    if end:
        query = query.where(Submission.created_at <= end)
        count_query = count_query.where(Submission.created_at <= end)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Submission.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    submissions = result.scalars().all()

    items = []
    for sub in submissions:
        answers_result = await db.execute(
            select(Answer).where(Answer.submission_id == sub.id)
        )
        answers = answers_result.scalars().all()

        extraction = await db.get(Extraction, sub.id)

        items.append(
            SubmissionSummary(
                id=sub.id,
                cohort_id=sub.cohort_id,
                created_at=sub.created_at,
                completed_at=sub.completed_at,
                status=sub.status,
                language=sub.language,
                time_to_complete_sec=sub.time_to_complete_sec,
                answers=[
                    {
                        "question_id": a.question_id,
                        "question_type": a.question_type,
                        "answer_raw": a.answer_raw,
                        "input_mode": a.input_mode,
                        "is_vague": a.is_vague,
                        "followup_1": a.followup_1,
                        "followup_1_answer": a.followup_1_answer,
                        "followup_2": a.followup_2,
                        "followup_2_answer": a.followup_2_answer,
                    }
                    for a in answers
                ],
                extraction=(
                    {
                        "what_was_tried": extraction.what_was_tried,
                        "planned_task_or_workflow": extraction.planned_task_or_workflow,
                        "outcome_or_expected_outcome": extraction.outcome_or_expected_outcome,
                        "barriers": extraction.barriers,
                        "enablers": extraction.enablers,
                        "public_benefit": extraction.public_benefit,
                        "top_themes": extraction.top_themes,
                        "success_story_candidate": extraction.success_story_candidate,
                    }
                    if extraction
                    else None
                ),
            )
        )

    return PaginatedResponses(items=items, total=total, page=page, page_size=page_size)


@router.get("/export/raw.csv", dependencies=[Depends(require_admin)])
async def export_raw_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    csv_data = await generate_raw_csv(db, cohort_id, start, end)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=raw_export.csv"},
    )


@router.get("/export/structured.csv", dependencies=[Depends(require_admin)])
async def export_structured_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    csv_data = await generate_structured_csv(db, cohort_id, start, end)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=structured_export.csv"},
    )


@router.get("/export/summary.pdf", dependencies=[Depends(require_admin)])
async def export_summary_pdf(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    pdf_bytes = await generate_summary_pdf(db, cohort_id, start, end)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=summary_report.pdf"},
    )


@router.get("/export/summary.pptx", dependencies=[Depends(require_admin)])
async def export_summary_pptx(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    pptx_bytes = await generate_summary_pptx(db, cohort_id, start, end)
    return StreamingResponse(
        iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": "attachment; filename=summary_report.pptx"},
    )
