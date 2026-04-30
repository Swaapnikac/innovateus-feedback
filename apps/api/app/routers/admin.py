import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_, any_
from app.db import get_db
from app.models import (
    Answer,
    Cohort,
    Event,
    Extraction,
    ExtractionReview,
    Submission,
    SurveyConfigVersion,
)
from app.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    MetricsResponse,
    PaginatedResponses,
    SubmissionSummary,
    CohortResponse,
    CohortSettingsRequest,
    CreateCohortRequest,
    ReviewRequest,
    ReviewResponse,
    FacilitatorFeedbackRequest,
)
from app.auth import verify_password, create_access_token, require_admin, require_editor
from app.config import get_settings
from app.services.export_service import (
    SubmissionBundle,
    build_bundles,
    generate_raw_csv,
    generate_structured_csv,
    generate_summary_pdf,
    generate_summary_pptx,
    generate_user_testing_csv,
)
from app.services.ai_service import analyze_open_responses, compare_survey_responses
from app.services.cohort_resolver import is_valid_slug, slugify
from app.services.metrics_service import compute_user_testing_metrics

router = APIRouter()

DEFAULT_SURVEY_PATH = Path(__file__).resolve().parents[4] / "docs" / "survey-config" / "survey-en.json"


def _sub_to_dict(sub: Submission, answers: list[Answer], extraction: Optional[Extraction]) -> dict:
    """Convert ORM objects to the dict shape that export_service / analytics expect."""
    answers_list = [
        {
            "question_id": a.question_id,
            "question_type": a.question_type,
            "answer_raw": a.answer_raw,
            "input_mode": a.input_mode,
            "is_vague": a.is_vague,
            "followups_asked": a.followups_asked,
            "followup_1": a.followup_1,
            "followup_1_answer": a.followup_1_answer,
            "followup_2": a.followup_2,
            "followup_2_answer": a.followup_2_answer,
        }
        for a in answers
    ]

    ext_dict = None
    if extraction:
        ext_dict = {
            "what_was_tried": extraction.what_was_tried,
            "planned_task_or_workflow": extraction.planned_task_or_workflow,
            "outcome_or_expected_outcome": extraction.outcome_or_expected_outcome,
            "barriers": extraction.barriers,
            "enablers": extraction.enablers,
            "public_benefit": extraction.public_benefit,
            "top_themes": extraction.top_themes,
            "success_story_candidate": extraction.success_story_candidate,
        }

    return {
        "submission_id": str(sub.id),
        "cohort_id": str(sub.cohort_id),
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "completed_at": sub.completed_at.isoformat() if sub.completed_at else None,
        "status": sub.status,
        "time_to_complete_sec": sub.time_to_complete_sec,
        "survey_version": sub.survey_version,
        "ip_hash": sub.ip_hash,
        "experience_rating": sub.experience_rating,
        "experience_feedback": sub.experience_feedback,
        "answers": answers_list,
        "extraction": ext_dict,
    }


async def _get_bundles_for_filters(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
    include_started: bool = True,
) -> list[SubmissionBundle]:
    """Load submissions + their answers/extractions/reviews/cohort as ORM bundles.

    Preferred loader for the user-testing exports and the user-testing
    analytics endpoint. Falls back to the legacy dict loader below only where
    existing endpoints still rely on it.
    """
    q = select(Submission)
    if cohort_id:
        q = q.where(Submission.cohort_id == cohort_id)
    if start:
        q = q.where(Submission.created_at >= start)
    if end:
        q = q.where(Submission.created_at <= end)
    if survey_version:
        q = q.where(Submission.survey_version == survey_version)

    result = await db.execute(q)
    subs = list(result.scalars().all())
    if not subs:
        return []

    sub_ids = [s.id for s in subs]
    answers_result = await db.execute(select(Answer).where(Answer.submission_id.in_(sub_ids)))
    answers_by_sub: dict[str, list[Answer]] = {}
    for a in answers_result.scalars().all():
        answers_by_sub.setdefault(str(a.submission_id), []).append(a)

    ext_result = await db.execute(select(Extraction).where(Extraction.submission_id.in_(sub_ids)))
    extractions_by_sub = {str(e.submission_id): e for e in ext_result.scalars().all()}

    rev_result = await db.execute(select(ExtractionReview).where(ExtractionReview.submission_id.in_(sub_ids)))
    reviews_by_sub = {str(r.submission_id): r for r in rev_result.scalars().all()}

    cohort_ids = list({s.cohort_id for s in subs})
    cohorts_result = await db.execute(select(Cohort).where(Cohort.id.in_(cohort_ids)))
    cohorts_by_id = {str(c.id): c for c in cohorts_result.scalars().all()}

    # Drop started-but-empty submissions unless asked to keep them
    filtered = []
    for s in subs:
        has_answers = bool(answers_by_sub.get(str(s.id)))
        if not include_started and s.status == "started" and not has_answers:
            continue
        filtered.append(s)

    return build_bundles(
        filtered,
        answers_by_sub=answers_by_sub,
        extractions_by_sub=extractions_by_sub,
        reviews_by_sub=reviews_by_sub,
        cohorts_by_id=cohorts_by_id,
    )


async def _get_submissions_for_filters(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
) -> list[dict]:
    q = select(Submission)
    if cohort_id:
        q = q.where(Submission.cohort_id == cohort_id)
    if start:
        q = q.where(Submission.created_at >= start)
    if end:
        q = q.where(Submission.created_at <= end)
    if survey_version:
        q = q.where(Submission.survey_version == survey_version)

    result = await db.execute(q)
    subs = result.scalars().all()

    if not subs:
        return []

    sub_ids = [s.id for s in subs]

    answers_result = await db.execute(select(Answer).where(Answer.submission_id.in_(sub_ids)))
    all_answers = answers_result.scalars().all()
    answers_by_sub: dict[uuid.UUID, list[Answer]] = {}
    for a in all_answers:
        answers_by_sub.setdefault(a.submission_id, []).append(a)

    ext_result = await db.execute(select(Extraction).where(Extraction.submission_id.in_(sub_ids)))
    all_extractions = ext_result.scalars().all()
    ext_by_sub: dict[uuid.UUID, Extraction] = {e.submission_id: e for e in all_extractions}

    filtered = []
    for sub in subs:
        answers = answers_by_sub.get(sub.id, [])
        if sub.status == "started" and not answers:
            continue
        extraction = ext_by_sub.get(sub.id)
        filtered.append(_sub_to_dict(sub, answers, extraction))

    return filtered


def _apply_segment_filter(
    submissions: list[dict],
    segment_q: Optional[str],
    segment_v: Optional[str],
) -> list[dict]:
    """Keep only submissions where the named question was answered with the given value."""
    if not segment_q or not segment_v:
        return submissions
    out = []
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_id") == segment_q and a.get("answer_raw") == segment_v:
                out.append(sub)
                break
    return out


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(req: AdminLoginRequest, response: Response):
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
        samesite="none" if settings.environment != "development" else "lax",
        max_age=86400,
    )
    return AdminLoginResponse(token=token)


@router.get("/cohorts", dependencies=[Depends(require_admin)])
async def list_cohorts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cohort).order_by(Cohort.created_at.desc()))
    cohorts = result.scalars().all()
    return [
        CohortResponse(
            id=c.id,
            slug=c.slug,
            name=c.name,
            course_name=c.course_name,
            program_type=c.program_type,
            max_submissions_per_ip=(
                c.max_submissions_per_ip if c.max_submissions_per_ip is not None else 1
            ),
            created_at=c.created_at,
        )
        for c in cohorts
    ]


async def _resolve_unique_slug(
    db: AsyncSession, candidate: Optional[str], fallback_name: str
) -> Optional[str]:
    """Validate a user-supplied slug, or auto-generate one.

    Returns ``None`` when neither a slug nor a slugifiable name is provided
    (cohort then resolves by UUID only). Raises 400 on collision so the admin
    can pick a different value rather than silently overwriting somebody
    else's URL.
    """
    raw = (candidate or "").strip().lower() or slugify(fallback_name or "")
    if not raw:
        return None
    if not is_valid_slug(raw):
        raise HTTPException(
            status_code=400,
            detail="Slug must be 2-60 chars, lowercase letters/digits/hyphen only",
        )
    existing = await db.execute(select(Cohort.id).where(Cohort.slug == raw))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Slug '{raw}' is already in use; pick a different one",
        )
    return raw


@router.post("/cohorts", response_model=CohortResponse, dependencies=[Depends(require_editor)])
async def create_cohort(req: CreateCohortRequest, db: AsyncSession = Depends(get_db)):
    cohort_id = uuid.uuid4()
    empty_config = {
        "version": "1.0",
        "title": "Untitled Survey",
        "questions": [],
        "question_groups": [],
    }

    course_name = req.course_name or req.name
    slug = await _resolve_unique_slug(db, req.slug, req.name)

    cohort = Cohort(
        id=cohort_id,
        slug=slug,
        name=req.name,
        course_name=course_name,
        program_type=req.program_type,
        survey_config=empty_config,
        active_version="v1",
        max_submissions_per_ip=1,
        created_at=datetime.now(timezone.utc),
    )
    db.add(cohort)

    return CohortResponse(
        id=cohort_id,
        slug=slug,
        name=req.name,
        course_name=course_name,
        program_type=req.program_type,
        max_submissions_per_ip=1,
        created_at=cohort.created_at,
    )


@router.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(require_admin)])
async def get_metrics(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
    segment_q: Optional[str] = None,
    segment_v: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end, survey_version)
    submissions = _apply_segment_filter(submissions, segment_q, segment_v)

    total = len(submissions)
    completed = [s for s in submissions if s.get("status") == "completed"]
    completion_rate = len(completed) / total if total > 0 else 0

    times = [int(s["time_to_complete_sec"]) for s in completed if s.get("time_to_complete_sec")]
    avg_time = sum(times) / len(times) if times else None

    scores = []
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_id") == "q1_recommend":
                try:
                    scores.append(int(a["answer_raw"]))
                except (ValueError, TypeError, KeyError):
                    pass
    avg_score = sum(scores) / len(scores) if scores else None

    conf_dist: dict[str, int] = {}
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_id") == "q2_confidence":
                val = a.get("answer_raw") or "Unknown"
                conf_dist[val] = conf_dist.get(val, 0) + 1

    open_answers = []
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_type") == "open" and (a.get("answer_raw") or "").strip():
                open_answers.append(a)
    vague_count = sum(1 for a in open_answers if a.get("is_vague") is True)
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
    survey_version: Optional[str] = None,
    segment_q: Optional[str] = None,
    segment_v: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    all_subs = await _get_submissions_for_filters(db, cohort_id, start, end, survey_version)
    all_subs = _apply_segment_filter(all_subs, segment_q, segment_v)
    all_subs.sort(key=lambda s: s.get("created_at") or "", reverse=True)

    total = len(all_subs)
    offset = (page - 1) * page_size
    page_items = all_subs[offset:offset + page_size]

    items = []
    for sub_dict in page_items:
        answered = [a for a in sub_dict.get("answers", []) if (a.get("answer_raw") or "").strip()]
        created_at_str = sub_dict.get("created_at")
        completed_at_str = sub_dict.get("completed_at")
        items.append(
            SubmissionSummary(
                id=sub_dict["submission_id"],
                cohort_id=sub_dict["cohort_id"],
                created_at=datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(),
                completed_at=datetime.fromisoformat(completed_at_str) if completed_at_str else None,
                status=sub_dict.get("status", ""),
                time_to_complete_sec=sub_dict.get("time_to_complete_sec"),
                survey_version=sub_dict.get("survey_version"),
                ip_hash=sub_dict.get("ip_hash"),
                answers=answered,
                extraction=sub_dict.get("extraction"),
            )
        )

    return PaginatedResponses(items=items, total=total, page=page, page_size=page_size)


async def _get_cohort_meta(db: AsyncSession, cohort_id: Optional[uuid.UUID]) -> tuple[str, str, Optional[dict]]:
    """Return (cohort_name, course_name, survey_config) for export headers."""
    if not cohort_id:
        return ("", "", None)
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        return ("", "", None)
    return (cohort.name or "", cohort.course_name or "", cohort.survey_config)


@router.get("/export/raw.csv", dependencies=[Depends(require_admin)])
async def export_raw_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    bundles = await _get_bundles_for_filters(db, cohort_id, start, end, include_started=False)
    bundles.sort(key=lambda b: b.submission.created_at or datetime.min.replace(tzinfo=timezone.utc))
    _, _, survey_config = await _get_cohort_meta(db, cohort_id)
    csv_data = generate_raw_csv(bundles, survey_config=survey_config)
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
    bundles = await _get_bundles_for_filters(db, cohort_id, start, end, include_started=False)
    bundles.sort(key=lambda b: b.submission.created_at or datetime.min.replace(tzinfo=timezone.utc))
    _, _, survey_config = await _get_cohort_meta(db, cohort_id)
    csv_data = generate_structured_csv(bundles, survey_config=survey_config)
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
    bundles = await _get_bundles_for_filters(db, cohort_id, start, end, include_started=False)
    completed = [b for b in bundles if b.submission.status == "completed"]
    cohort_name, course_name, _survey_config = await _get_cohort_meta(db, cohort_id)
    pdf_bytes = generate_summary_pdf(completed, cohort_name, course_name)
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
    bundles = await _get_bundles_for_filters(db, cohort_id, start, end, include_started=False)
    completed = [b for b in bundles if b.submission.status == "completed"]
    cohort_name, course_name, _survey_config = await _get_cohort_meta(db, cohort_id)
    pptx_bytes = generate_summary_pptx(completed, cohort_name, course_name)
    return StreamingResponse(
        iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": "attachment; filename=summary_report.pptx"},
    )


@router.delete("/responses", dependencies=[Depends(require_admin)])
async def delete_all_responses(cohort_id: Optional[uuid.UUID] = None, db: AsyncSession = Depends(get_db)):
    if cohort_id:
        subs_q = await db.execute(select(Submission).where(Submission.cohort_id == cohort_id))
    else:
        subs_q = await db.execute(select(Submission))

    subs = subs_q.scalars().all()
    sub_ids = [s.id for s in subs]

    if sub_ids:
        await db.execute(delete(Extraction).where(Extraction.submission_id.in_(sub_ids)))
        await db.execute(delete(Answer).where(Answer.submission_id.in_(sub_ids)))
        for sub in subs:
            await db.delete(sub)

    # Also delete all events for this cohort (landing, consent, survey_start, etc.)
    # Match every identifier the cohort has ever been tagged with so we don't
    # leave orphan events behind when participants arrived via slug URLs.
    if cohort_id:
        identifiers = await _cohort_event_identifiers(db, cohort_id)
        await db.execute(delete(Event).where(Event.cohort_id.in_(identifiers)))
    else:
        await db.execute(delete(Event))

    return {"status": "ok", "deleted": len(subs)}


@router.delete("/cohorts/{cohort_id}", dependencies=[Depends(require_admin)])
async def delete_cohort(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    # Delete all related data in dependency order
    subs_q = await db.execute(select(Submission).where(Submission.cohort_id == cohort_id))
    subs = subs_q.scalars().all()
    sub_ids = [s.id for s in subs]

    if sub_ids:
        await db.execute(delete(Extraction).where(Extraction.submission_id.in_(sub_ids)))
        await db.execute(delete(Answer).where(Answer.submission_id.in_(sub_ids)))
        await db.execute(delete(Submission).where(Submission.cohort_id == cohort_id))

    # Match every identifier the cohort has ever been tagged with — UUID,
    # current slug, and any historical alias — so deleting the cohort
    # doesn't leave orphan events behind for participants who arrived via
    # slug URLs.
    identifiers = await _cohort_event_identifiers(db, cohort_id)
    await db.execute(delete(Event).where(Event.cohort_id.in_(identifiers)))
    await db.execute(delete(SurveyConfigVersion).where(SurveyConfigVersion.cohort_id == cohort_id))
    await db.delete(cohort)

    return {"status": "deleted", "cohort_id": str(cohort_id)}


@router.post("/cohorts/{cohort_id}/duplicate", response_model=CohortResponse, dependencies=[Depends(require_editor)])
async def duplicate_cohort(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Create a new cohort as a copy of an existing one (config only, no responses)."""
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Cohort not found")

    new_id = uuid.uuid4()
    new_name = f"{source.name} (Copy)"
    now = datetime.now(timezone.utc)
    config = json.loads(json.dumps(source.survey_config)) if source.survey_config else {
        "version": "1.0",
        "title": "Untitled Survey",
        "questions": [],
        "question_groups": [],
    }

    # Auto-derive a slug for the copy when the source had one. Append an
    # incrementing ``-copy``/``-copy-2``/``-copy-3`` suffix until we find
    # something free so duplicating never collides with an existing slug.
    new_slug: Optional[str] = None
    if source.slug:
        base = f"{source.slug}-copy"
        candidate = base
        n = 2
        while True:
            existing = await db.execute(select(Cohort.id).where(Cohort.slug == candidate))
            if existing.scalar_one_or_none() is None:
                new_slug = candidate
                break
            candidate = f"{base}-{n}"
            n += 1
            if n > 100:
                # Pathological — fall back to no slug rather than spin forever.
                new_slug = None
                break

    new_cohort = Cohort(
        id=new_id,
        slug=new_slug,
        name=new_name,
        course_name=source.course_name,
        program_type=source.program_type,
        survey_config=config,
        active_version="v1",
        # Preserve the source's cap exactly; ``0`` means "unlimited" and
        # must not be coerced to 1 by a truthiness fallback.
        max_submissions_per_ip=(
            source.max_submissions_per_ip if source.max_submissions_per_ip is not None else 1
        ),
        created_at=now,
    )
    db.add(new_cohort)

    # Seed version v1 from the source's current config
    version = SurveyConfigVersion(
        id=uuid.uuid4(),
        cohort_id=new_id,
        version_label="v1",
        config=config,
        change_summary=f"Duplicated from {source.name}",
        created_by="editor",
        created_at=now,
    )
    db.add(version)

    return CohortResponse(
        id=new_id,
        slug=new_slug,
        name=new_name,
        course_name=source.course_name,
        program_type=source.program_type,
        max_submissions_per_ip=(
            source.max_submissions_per_ip if source.max_submissions_per_ip is not None else 1
        ),
        created_at=now,
    )


@router.post("/cohorts/{cohort_id}/settings", dependencies=[Depends(require_admin)])
async def update_cohort_settings(cohort_id: uuid.UUID, req: CohortSettingsRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    cohort.max_submissions_per_ip = req.max_submissions_per_ip

    slug_changed = False
    if req.slug is not None:
        raw = req.slug.strip().lower()
        if not raw:
            raise HTTPException(
                status_code=400,
                detail="Slug cannot be empty. Leave the field unchanged to keep the current URL.",
            )
        if raw != (cohort.slug or ""):
            if not is_valid_slug(raw):
                raise HTTPException(
                    status_code=400,
                    detail="Slug must be 2-60 chars, lowercase letters/digits/hyphen only",
                )
            # Union uniqueness: reject if another cohort uses this value as
            # its current slug OR has it stored as a historical alias.
            collision = await db.execute(
                select(Cohort.id).where(
                    Cohort.id != cohort.id,
                    or_(
                        Cohort.slug == raw,
                        raw == any_(Cohort.previous_slugs),
                    ),
                )
            )
            if collision.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"URL '/c/{raw}' is already in use or was previously used by another survey",
                )
            # Preserve the old slug as an alias so legacy QR codes / shared
            # links keep resolving to this same cohort.
            if cohort.slug and cohort.slug not in (cohort.previous_slugs or []):
                cohort.previous_slugs = [*(cohort.previous_slugs or []), cohort.slug]
            cohort.slug = raw
            slug_changed = True

    return {
        "status": "updated",
        "max_submissions_per_ip": cohort.max_submissions_per_ip,
        "slug": cohort.slug,
        "slug_changed": slug_changed,
        "previous_slugs": list(cohort.previous_slugs or []),
    }


@router.get("/qualtrics/status", dependencies=[Depends(require_admin)])
def qualtrics_status():
    s = get_settings()
    configured = bool(s.qualtrics_api_token and s.qualtrics_survey_id and s.qualtrics_datacenter_id)
    return {
        "configured": configured,
        "survey_id": s.qualtrics_survey_id or None,
        "datacenter_id": s.qualtrics_datacenter_id or None,
    }


@router.post("/qualtrics/sync/{submission_id}", dependencies=[Depends(require_admin)])
async def qualtrics_sync_one(submission_id: uuid.UUID):
    from app.services.qualtrics_service import sync_submission
    result = await sync_submission(submission_id, force=True)
    status_code = "ok" if result["success"] else "error"
    return {"status": status_code, "submission_id": str(submission_id), "error": result.get("error")}


@router.post("/qualtrics/sync-all", dependencies=[Depends(require_admin)])
async def qualtrics_sync_all(
    cohort_id: Optional[uuid.UUID] = None,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    from app.services.qualtrics_service import sync_submission

    q = select(Submission).where(Submission.status == "completed")
    if cohort_id:
        q = q.where(Submission.cohort_id == cohort_id)
    result = await db.execute(q)
    subs = result.scalars().all()

    if not force:
        subs = [s for s in subs if not s.qualtrics_synced_at]

    total = len(subs)
    synced = 0
    failed = 0
    errors: list[dict] = []

    for sub in subs:
        sync_result = await sync_submission(sub.id, force=True)
        if sync_result["success"]:
            synced += 1
        else:
            failed += 1
            errors.append({"submission_id": str(sub.id), "error": sync_result.get("error")})

    return {"total": total, "synced": synced, "failed": failed, "errors": errors}


async def _cohort_event_identifiers(
    db: AsyncSession, cohort_id: uuid.UUID
) -> list[str]:
    """Return every string a participant might have tagged events with for
    this cohort: the UUID, the current slug, and every historical alias.

    Events store ``cohort_id`` as a string of whatever the URL carried at
    event time, so the same cohort can show up under multiple identifiers
    (UUID + slug + old aliases). Analytics, response deletion, and cohort
    deletion all need to operate across the full set, otherwise events
    tagged via slug URLs get silently dropped (undercounted analytics) or
    leaked as orphans (after cohort delete). Union uniqueness on slug
    renames guarantees no two cohorts ever share an identifier here, so
    this is safe.
    """
    cohort_row = await db.scalar(select(Cohort).where(Cohort.id == cohort_id))
    identifiers: list[str] = [str(cohort_id)]
    if cohort_row is not None:
        if cohort_row.slug:
            identifiers.append(cohort_row.slug)
        for alias in cohort_row.previous_slugs or []:
            if alias and alias not in identifiers:
                identifiers.append(alias)
    return identifiers


async def _get_events_for_cohort(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[dict]:
    q = select(Event)
    if cohort_id:
        identifiers = await _cohort_event_identifiers(db, cohort_id)
        q = q.where(Event.cohort_id.in_(identifiers))
    if start:
        q = q.where(Event.timestamp >= start)
    if end:
        q = q.where(Event.timestamp <= end)

    result = await db.execute(q)
    events = result.scalars().all()

    return [
        {
            "session_token": e.session_token,
            "cohort_id": e.cohort_id,
            "submission_id": e.submission_id,
            "event_type": e.event_type,
            "event_data": e.event_data or {},
            "ip_hash": e.ip_hash,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]


def _compute_submissions_by_date(submissions: list[dict]) -> list[dict]:
    """Return sorted [{date: 'YYYY-MM-DD', count: N}] for completed submissions."""
    by_date: dict[str, int] = {}
    for sub in submissions:
        if sub.get("status") != "completed":
            continue
        date_str = (sub.get("completed_at") or sub.get("created_at") or "")[:10]
        if date_str:
            by_date[date_str] = by_date.get(date_str, 0) + 1
    return [{"date": d, "count": c} for d, c in sorted(by_date.items())]


def _compute_question_stats(submissions: list[dict], survey_config: Optional[dict]) -> list[dict]:
    """Return type-appropriate analytics for each question in the survey config."""
    if not survey_config:
        return []
    questions = survey_config.get("questions", []) or []
    result = []

    for q in questions:
        qid = q.get("id")
        qtype = q.get("type")
        if not qid or not qtype:
            continue

        answers_raw: list[str] = []
        for sub in submissions:
            for a in sub.get("answers", []):
                if a.get("question_id") == qid:
                    raw = (a.get("answer_raw") or "").strip()
                    if raw:
                        answers_raw.append(raw)

        total = len(answers_raw)
        stats: dict = {"type": qtype}

        if qtype in ("rating", "nps"):
            nums: list[int] = []
            for raw in answers_raw:
                try:
                    nums.append(int(float(raw)))
                except (ValueError, TypeError):
                    pass
            if nums:
                stats["avg"] = round(sum(nums) / len(nums), 2)
                stats["median"] = sorted(nums)[len(nums) // 2]
                dist: dict[str, int] = {}
                for n in nums:
                    dist[str(n)] = dist.get(str(n), 0) + 1
                stats["distribution"] = dist
                if qtype == "nps":
                    promoters = sum(1 for n in nums if n >= 9)
                    detractors = sum(1 for n in nums if n <= 6)
                    passives = len(nums) - promoters - detractors
                    stats["nps_score"] = round(((promoters - detractors) / len(nums)) * 100)
                    stats["promoters"] = promoters
                    stats["passives"] = passives
                    stats["detractors"] = detractors

        elif qtype == "slider":
            nums_f: list[float] = []
            for raw in answers_raw:
                try:
                    nums_f.append(float(raw))
                except (ValueError, TypeError):
                    pass
            if nums_f:
                stats["avg"] = round(sum(nums_f) / len(nums_f), 2)
                stats["min"] = min(nums_f)
                stats["max"] = max(nums_f)
                stats["median"] = sorted(nums_f)[len(nums_f) // 2]

        elif qtype in ("mcq", "dropdown", "yesno"):
            dist_s: dict[str, int] = {}
            for raw in answers_raw:
                dist_s[raw] = dist_s.get(raw, 0) + 1
            stats["distribution"] = dist_s

        elif qtype == "multi":
            dist_m: dict[str, int] = {}
            for raw in answers_raw:
                try:
                    items = json.loads(raw)
                    if isinstance(items, list):
                        for item in items:
                            key = str(item)
                            dist_m[key] = dist_m.get(key, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass
            stats["distribution"] = dist_m

        elif qtype == "matrix":
            row_stats: dict[str, dict[str, int]] = {}
            for raw in answers_raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        for row, col in parsed.items():
                            row_stats.setdefault(row, {})
                            col_key = str(col)
                            row_stats[row][col_key] = row_stats[row].get(col_key, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass
            stats["row_distributions"] = row_stats
            stats["rows"] = q.get("rows") or list(row_stats.keys())
            stats["columns"] = [str(c) for c in (q.get("options") or [])]

        elif qtype == "ranking":
            rank_sums: dict[str, float] = {}
            rank_counts: dict[str, int] = {}
            for raw in answers_raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        for i, item in enumerate(parsed):
                            key = str(item)
                            rank_sums[key] = rank_sums.get(key, 0) + (i + 1)
                            rank_counts[key] = rank_counts.get(key, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass
            stats["average_ranks"] = {
                item: round(rank_sums[item] / rank_counts[item], 2)
                for item in rank_sums
                if rank_counts[item] > 0
            }

        elif qtype == "date":
            dates = [raw for raw in answers_raw if raw]
            stats["earliest"] = min(dates) if dates else None
            stats["latest"] = max(dates) if dates else None
            stats["count"] = len(dates)

        elif qtype in ("open", "short_text"):
            lengths = [len(raw) for raw in answers_raw]
            stats["count"] = len(answers_raw)
            stats["avg_length"] = round(sum(lengths) / len(lengths), 1) if lengths else 0

        result.append({
            "question_id": qid,
            "question_type": qtype,
            "question_text": q.get("text", ""),
            "total_responses": total,
            "stats": stats,
        })

    return result


def _collect_open_responses(submissions: list[dict], survey_config: Optional[dict]) -> list[dict]:
    questions = (survey_config or {}).get("questions", []) or []
    q_meta = {
        q.get("id"): {
            "text": q.get("text", ""),
            "type": q.get("type", ""),
        }
        for q in questions
        if q.get("id")
    }
    open_ids = {
        qid
        for qid, meta in q_meta.items()
        if meta.get("type") in {"open", "short_text"}
    }
    responses: list[dict] = []
    for sub in submissions:
        for answer in sub.get("answers", []):
            qid = answer.get("question_id")
            qtype = answer.get("question_type")
            if qid not in open_ids and qtype not in {"open", "short_text"}:
                continue
            raw = (answer.get("answer_raw") or "").strip()
            if not raw:
                continue
            responses.append({
                "submission_id": sub.get("submission_id"),
                "question_id": qid,
                "question_text": q_meta.get(qid, {}).get("text", qid or ""),
                "answer_text": raw,
                "input_mode": answer.get("input_mode"),
                "created_at": sub.get("created_at"),
            })
    return responses


def _survey_snapshot(name: str, submissions: list[dict], survey_config: Optional[dict]) -> dict:
    completed = [s for s in submissions if s.get("status") == "completed"]
    themes: dict[str, int] = {}
    barriers: dict[str, int] = {}
    for sub in completed:
        extraction = sub.get("extraction") or {}
        for theme in extraction.get("top_themes") or []:
            themes[str(theme)] = themes.get(str(theme), 0) + 1
        for barrier in extraction.get("barriers") or []:
            barriers[str(barrier)] = barriers.get(str(barrier), 0) + 1
    return {
        "name": name,
        "completed_count": len(completed),
        "total_count": len(submissions),
        "top_themes": sorted(themes.items(), key=lambda x: x[1], reverse=True)[:8],
        "top_barriers": sorted(barriers.items(), key=lambda x: x[1], reverse=True)[:8],
        "question_stats": _compute_question_stats(completed, survey_config)[:12],
        "open_response_sample": _collect_open_responses(completed, survey_config)[:20],
    }


@router.get("/analytics", dependencies=[Depends(require_admin)])
async def get_analytics(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    segment_q: Optional[str] = None,
    segment_v: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    events = await _get_events_for_cohort(db, cohort_id, start, end)
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end)
    submissions = _apply_segment_filter(submissions, segment_q, segment_v)
    _, _, survey_config = await _get_cohort_meta(db, cohort_id)

    by_type: dict[str, list[dict]] = {}
    for evt in events:
        t = evt.get("event_type", "")
        by_type.setdefault(t, []).append(evt)

    def count_unique_page_views(page: str) -> int:
        # Count unique session tokens per page.  Sessions are reset on every new
        # form visit (frontend clears sessionStorage on the consent page), so
        # each visit produces a distinct token — making this count accurate.
        sessions: set[str] = set()
        for evt in by_type.get("page_view", []):
            if evt.get("event_data", {}).get("page") == page:
                token = evt.get("session_token", "")
                if token:
                    sessions.add(token)
        return len(sessions)

    funnel = {
        "page_views_landing": count_unique_page_views("landing"),
        "page_views_consent": count_unique_page_views("consent"),
        "survey_starts": len(set(e.get("session_token", "") for e in by_type.get("survey_start", []) if e.get("session_token"))),
        "survey_in_progress": len([s for s in submissions if s.get("status") == "started" and len(s.get("answers", [])) > 0]),
        "survey_completed": len([s for s in submissions if s.get("status") == "completed"]),
    }
    funnel["dropout_rate"] = round(
        1 - (funnel["survey_completed"] / funnel["survey_starts"]) if funnel["survey_starts"] > 0 else 0, 3
    )

    # Deduplicate question_view events by (session_token, question_id) so that
    # navigating back-and-forth or editing doesn't inflate the reached count.
    question_reached: dict[str, int] = {}
    question_answered: dict[str, int] = {}
    seen_question_views: set[tuple[str, str]] = set()
    for evt in by_type.get("question_view", []):
        qid = evt.get("event_data", {}).get("question_id", "")
        session = evt.get("session_token", "")
        key = (session, qid)
        if key not in seen_question_views:
            seen_question_views.add(key)
            question_reached[qid] = question_reached.get(qid, 0) + 1
    seen_question_answers: set[tuple[str, str]] = set()
    for evt in by_type.get("question_answer", []):
        qid = evt.get("event_data", {}).get("question_id", "")
        session = evt.get("session_token", "")
        key = (session, qid)
        if key not in seen_question_answers:
            seen_question_answers.add(key)
            question_answered[qid] = question_answered.get(qid, 0) + 1

    all_qids = sorted(set(list(question_reached.keys()) + list(question_answered.keys())))
    per_question_dropout = []
    for qid in all_qids:
        reached = question_reached.get(qid, 0)
        answered = question_answered.get(qid, 0)
        per_question_dropout.append({
            "question_id": qid,
            "reached": reached,
            "answered": answered,
            "dropout_count": max(0, reached - answered),
        })

    voice_count = 0
    text_count = 0
    voice_per_q: dict[str, int] = {}
    text_per_q: dict[str, int] = {}
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_type") != "open":
                continue
            # Only count answers that actually have content — skipped questions
            # have no answer_raw but may still have input_mode="voice" (the
            # default), which would incorrectly inflate the voice count.
            if not (a.get("answer_raw") or "").strip():
                continue
            qid = a.get("question_id", "")
            if a.get("input_mode") == "voice":
                voice_count += 1
                voice_per_q[qid] = voice_per_q.get(qid, 0) + 1
            else:
                text_count += 1
                text_per_q[qid] = text_per_q.get(qid, 0) + 1

    total_open = voice_count + text_count
    voice_vs_text = {
        "total_open_answers": total_open,
        "voice_count": voice_count,
        "text_count": text_count,
        "voice_percentage": round(voice_count / total_open, 3) if total_open > 0 else 0,
        "per_question": [
            {"question_id": qid, "voice": voice_per_q.get(qid, 0), "text": text_per_q.get(qid, 0)}
            for qid in sorted(set(list(voice_per_q.keys()) + list(text_per_q.keys())))
        ],
    }

    followup_triggered = len(by_type.get("followup_triggered", []))
    followup_answered_evts = by_type.get("followup_answered", [])
    followup_answered_count = len([e for e in followup_answered_evts if e.get("event_data", {}).get("followup_1_answered")])
    followup_skipped = len(followup_answered_evts) - followup_answered_count

    open_answers = []
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_type") == "open" and (a.get("answer_raw") or "").strip():
                open_answers.append(a)
    vague_count = sum(1 for a in open_answers if a.get("is_vague") is True)

    followup_effectiveness = {
        "total_vague_detected": vague_count,
        "followups_shown": followup_triggered,
        "followups_answered": followup_answered_count,
        "followups_skipped": followup_skipped,
        "answer_rate": round(followup_answered_count / followup_triggered, 3) if followup_triggered > 0 else 0,
    }

    voice_vague = sum(1 for a in open_answers if a.get("input_mode") == "voice" and a.get("is_vague"))
    voice_total = sum(1 for a in open_answers if a.get("input_mode") == "voice")
    text_vague = sum(1 for a in open_answers if a.get("input_mode") != "voice" and a.get("is_vague"))
    text_total = sum(1 for a in open_answers if a.get("input_mode") != "voice")

    voice_lengths = [len(a["answer_raw"]) for a in open_answers if a.get("input_mode") == "voice" and a.get("answer_raw")]
    text_lengths = [len(a["answer_raw"]) for a in open_answers if a.get("input_mode") != "voice" and a.get("answer_raw")]

    voice_vs_text_quality = {
        "voice_vague_rate": round(voice_vague / voice_total, 3) if voice_total > 0 else 0,
        "text_vague_rate": round(text_vague / text_total, 3) if text_total > 0 else 0,
        "voice_avg_length": round(sum(voice_lengths) / len(voice_lengths), 1) if voice_lengths else 0,
        "text_avg_length": round(sum(text_lengths) / len(text_lengths), 1) if text_lengths else 0,
    }

    review_edit_evts = by_type.get("review_edit", [])
    review_sessions_with_edits = len(set(e.get("session_token", "") for e in review_edit_evts))
    total_reviews = count_unique_page_views("review")
    edits_per_q: dict[str, int] = {}
    for evt in review_edit_evts:
        qid = evt.get("event_data", {}).get("question_id", "")
        edits_per_q[qid] = edits_per_q.get(qid, 0) + 1

    review_edits = {
        "total_reviews": total_reviews,
        "reviews_with_edits": review_sessions_with_edits,
        "edit_rate": round(review_sessions_with_edits / total_reviews, 3) if total_reviews > 0 else 0,
        "edits_per_question": [{"question_id": qid, "edit_count": c} for qid, c in sorted(edits_per_q.items(), key=lambda x: x[1], reverse=True)],
    }

    completed_subs = [s for s in submissions if s.get("status") == "completed"]
    ratings = [int(s["experience_rating"]) for s in completed_subs if s.get("experience_rating") is not None and 1 <= int(s["experience_rating"]) <= 5]
    rating_dist = {str(i): 0 for i in range(1, 6)}
    for r in ratings:
        rating_dist[str(r)] += 1

    experience_rating = {
        "total_ratings": len(ratings),
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "distribution": rating_dist,
        "response_rate": round(len(ratings) / len(completed_subs), 3) if completed_subs else 0,
    }

    times = [int(s["time_to_complete_sec"]) for s in completed_subs if s.get("time_to_complete_sec")]
    q_answer_events = by_type.get("question_answer", [])

    time_metrics = {
        "avg_total_sec": round(sum(times) / len(times), 1) if times else None,
        "median_total_sec": round(sorted(times)[len(times) // 2], 1) if times else None,
        "total_question_answers": len(q_answer_events),
    }

    # Aggregate themes/barriers/success stories from ALL submissions (not just current page)
    theme_counts: dict[str, int] = {}
    barrier_counts: dict[str, int] = {}
    success_stories: list[str] = []
    for sub in submissions:
        ext = sub.get("extraction")
        if ext:
            for t in (ext.get("top_themes") or []):
                theme_counts[t] = theme_counts.get(t, 0) + 1
            for b in (ext.get("barriers") or []):
                barrier_counts[b] = barrier_counts.get(b, 0) + 1
            if ext.get("success_story_candidate"):
                success_stories.append(ext["success_story_candidate"])

    top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    top_barriers = sorted(barrier_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    per_question_stats = _compute_question_stats(submissions, survey_config)
    submissions_by_date = _compute_submissions_by_date(submissions)

    return {
        "funnel": funnel,
        "per_question_dropout": per_question_dropout,
        "voice_vs_text": voice_vs_text,
        "followup_effectiveness": followup_effectiveness,
        "voice_vs_text_quality": voice_vs_text_quality,
        "review_edits": review_edits,
        "experience_rating": experience_rating,
        "time_metrics": time_metrics,
        "top_themes": [{"theme": t, "count": c} for t, c in top_themes],
        "top_barriers": [{"barrier": b, "count": c} for b, c in top_barriers],
        "success_stories": success_stories[:6],
        "per_question_stats": per_question_stats,
        "submissions_by_date": submissions_by_date,
    }


@router.get("/crosstab", dependencies=[Depends(require_admin)])
async def get_crosstab(
    cohort_id: uuid.UUID,
    q1: str,
    q2: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return a frequency matrix of Q1 values × Q2 values across all submissions."""
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end, survey_version)

    matrix: dict[str, dict[str, int]] = {}
    q1_values: set[str] = set()
    q2_values: set[str] = set()

    for sub in submissions:
        q1_answer = None
        q2_answer = None
        for a in sub.get("answers", []):
            if a.get("question_id") == q1:
                q1_answer = a.get("answer_raw")
            elif a.get("question_id") == q2:
                q2_answer = a.get("answer_raw")
        if q1_answer and q2_answer:
            q1_values.add(q1_answer)
            q2_values.add(q2_answer)
            matrix.setdefault(q1_answer, {})
            matrix[q1_answer][q2_answer] = matrix[q1_answer].get(q2_answer, 0) + 1

    return {
        "q1_values": sorted(q1_values),
        "q2_values": sorted(q2_values),
        "matrix": matrix,
        "total": sum(sum(row.values()) for row in matrix.values()),
    }


@router.get("/ai-insights", dependencies=[Depends(require_admin)])
async def get_ai_insights(
    cohort_id: uuid.UUID,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
    segment_q: Optional[str] = None,
    segment_v: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end, survey_version)
    submissions = _apply_segment_filter(submissions, segment_q, segment_v)
    _, _, survey_config = await _get_cohort_meta(db, cohort_id)
    open_responses = _collect_open_responses(submissions, survey_config)
    return await analyze_open_responses(open_responses)


@router.get("/compare-insights", dependencies=[Depends(require_admin)])
async def get_compare_insights(
    cohort_id: uuid.UUID,
    compare_cohort_id: uuid.UUID,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    primary_name, _, primary_config = await _get_cohort_meta(db, cohort_id)
    comparison_name, _, comparison_config = await _get_cohort_meta(db, compare_cohort_id)
    if not primary_config or not comparison_config:
        raise HTTPException(status_code=404, detail="One or both surveys were not found")

    primary_subs = await _get_submissions_for_filters(db, cohort_id, start, end)
    comparison_subs = await _get_submissions_for_filters(db, compare_cohort_id, start, end)
    primary_snapshot = _survey_snapshot(primary_name, primary_subs, primary_config)
    comparison_snapshot = _survey_snapshot(comparison_name, comparison_subs, comparison_config)
    result = await compare_survey_responses(primary_snapshot, comparison_snapshot)
    return {
        **result,
        "primary": {
            "id": str(cohort_id),
            "name": primary_name,
            "completed_count": primary_snapshot["completed_count"],
        },
        "comparison": {
            "id": str(compare_cohort_id),
            "name": comparison_name,
            "completed_count": comparison_snapshot["completed_count"],
        },
    }


@router.get("/export/user-testing.csv", dependencies=[Depends(require_admin)])
async def export_user_testing_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    bundles = await _get_bundles_for_filters(db, cohort_id, start, end, include_started=True)
    bundles.sort(key=lambda b: b.submission.created_at or datetime.min.replace(tzinfo=timezone.utc))
    csv_data = generate_user_testing_csv(bundles)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=user_testing_export.csv"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# User-testing analytics — single payload powering the dashboard tab
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/user-testing-analytics", dependencies=[Depends(require_admin)])
async def user_testing_analytics(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    bundles = await _get_bundles_for_filters(db, cohort_id, start, end, include_started=True)
    submissions = [b.submission for b in bundles]
    answers_by_sub = {str(b.submission.id): b.answers for b in bundles}
    reviews_by_sub = {
        str(b.submission.id): b.review for b in bundles if b.review is not None
    }
    cohorts_by_id = {
        str(b.cohort.id): b.cohort for b in bundles if b.cohort is not None
    }
    extractions_by_sub = {
        str(b.submission.id): b.extraction for b in bundles if b.extraction is not None
    }
    payload = compute_user_testing_metrics(
        submissions=submissions,
        answers_by_sub=answers_by_sub,
        reviews_by_sub=reviews_by_sub,
        cohorts_by_id=cohorts_by_id,
        extractions_by_sub=extractions_by_sub,
    )
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Extraction review (H4 usefulness ratings)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/reviews", dependencies=[Depends(require_admin)])
async def list_reviews(
    cohort_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(ExtractionReview, Submission).join(Submission, Submission.id == ExtractionReview.submission_id)
    if cohort_id:
        q = q.where(Submission.cohort_id == cohort_id)
    q = q.order_by(ExtractionReview.reviewed_at.desc())
    result = await db.execute(q)
    out = []
    for review, sub in result.all():
        out.append(
            {
                "submission_id": str(review.submission_id),
                "cohort_id": str(sub.cohort_id),
                "reviewed_by": review.reviewed_by,
                "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
                "useful_flag": review.useful_flag,
                "accuracy_rating": review.accuracy_rating,
                "usefulness_rating": review.usefulness_rating,
                "accuracy_notes": review.accuracy_notes,
                "usefulness_notes": review.usefulness_notes,
            }
        )
    return {"items": out, "total": len(out)}


@router.post("/reviews/{submission_id}", response_model=ReviewResponse, dependencies=[Depends(require_admin)])
async def upsert_review(
    submission_id: uuid.UUID,
    req: ReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    sub_q = await db.execute(select(Submission).where(Submission.id == submission_id))
    if sub_q.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    existing_q = await db.execute(
        select(ExtractionReview).where(ExtractionReview.submission_id == submission_id)
    )
    review = existing_q.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if review is None:
        review = ExtractionReview(
            id=uuid.uuid4(),
            submission_id=submission_id,
            reviewed_by=req.reviewed_by,
            reviewed_at=now,
        )
        db.add(review)

    review.reviewed_by = req.reviewed_by
    review.reviewed_at = now
    review.useful_flag = req.useful_flag
    review.accuracy_rating = req.accuracy_rating
    review.usefulness_rating = req.usefulness_rating
    review.accuracy_notes = req.accuracy_notes
    review.usefulness_notes = req.usefulness_notes

    await db.flush()

    return ReviewResponse(
        submission_id=submission_id,
        reviewed_by=review.reviewed_by,
        reviewed_at=review.reviewed_at,
        useful_flag=review.useful_flag,
        accuracy_rating=review.accuracy_rating,
        usefulness_rating=review.usefulness_rating,
        accuracy_notes=review.accuracy_notes,
        usefulness_notes=review.usefulness_notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Facilitator feedback (admin-entered, H6/S9)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/cohorts/{cohort_id}/facilitator-feedback", dependencies=[Depends(require_admin)])
async def upsert_facilitator_feedback(
    cohort_id: uuid.UUID,
    req: FacilitatorFeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    if req.facilitator_name is not None:
        cohort.facilitator_name = req.facilitator_name
    if req.facilitator_email is not None:
        cohort.facilitator_email = req.facilitator_email
    if req.source_channel is not None:
        cohort.source_channel = req.source_channel
    if req.launch_phase is not None:
        cohort.launch_phase = req.launch_phase
    if req.facilitator_feedback_text is not None:
        cohort.facilitator_feedback_text = req.facilitator_feedback_text
        cohort.facilitator_feedback_received_at = datetime.now(timezone.utc)
    if req.facilitator_reported_issue_flag is not None:
        cohort.facilitator_reported_issue_flag = req.facilitator_reported_issue_flag
    if req.facilitator_issue_type is not None:
        cohort.facilitator_issue_type = req.facilitator_issue_type
    if req.facilitator_issue_notes is not None:
        cohort.facilitator_issue_notes = req.facilitator_issue_notes

    return {
        "cohort_id": str(cohort_id),
        "facilitator_name": cohort.facilitator_name,
        "facilitator_email": cohort.facilitator_email,
        "source_channel": cohort.source_channel,
        "launch_phase": cohort.launch_phase,
        "facilitator_feedback_text": cohort.facilitator_feedback_text,
        "facilitator_reported_issue_flag": cohort.facilitator_reported_issue_flag,
        "facilitator_issue_type": cohort.facilitator_issue_type,
        "facilitator_issue_notes": cohort.facilitator_issue_notes,
    }


@router.get("/cohorts/{cohort_id}/facilitator-feedback", dependencies=[Depends(require_admin)])
async def get_facilitator_feedback(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    return {
        "cohort_id": str(cohort_id),
        "facilitator_name": cohort.facilitator_name,
        "facilitator_email": cohort.facilitator_email,
        "source_channel": cohort.source_channel,
        "launch_phase": cohort.launch_phase,
        "facilitator_feedback_text": cohort.facilitator_feedback_text,
        "facilitator_feedback_received_at": cohort.facilitator_feedback_received_at.isoformat() if cohort.facilitator_feedback_received_at else None,
        "facilitator_reported_issue_flag": cohort.facilitator_reported_issue_flag,
        "facilitator_issue_type": cohort.facilitator_issue_type,
        "facilitator_issue_notes": cohort.facilitator_issue_notes,
    }
