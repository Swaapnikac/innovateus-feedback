import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db import get_db
from app.models import Cohort, Submission, Answer, Extraction, Event
from app.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    MetricsResponse,
    PaginatedResponses,
    SubmissionSummary,
    CohortResponse,
    CohortSettingsRequest,
    CreateCohortRequest,
)
from app.auth import verify_password, create_access_token, require_admin
from app.config import get_settings
from app.services.export_service import (
    generate_raw_csv,
    generate_structured_csv,
    generate_summary_pdf,
    generate_summary_pptx,
    generate_user_testing_csv,
)

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

    # Filter out empty in-progress submissions
    filtered = []
    for sub in subs:
        answers_q = await db.execute(select(Answer).where(Answer.submission_id == sub.id))
        answers = answers_q.scalars().all()
        if sub.status == "started" and not answers:
            continue
        ext_q = await db.execute(select(Extraction).where(Extraction.submission_id == sub.id))
        extraction = ext_q.scalar_one_or_none()
        filtered.append(_sub_to_dict(sub, answers, extraction))

    return filtered


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
            name=c.name,
            course_name=c.course_name,
            max_submissions_per_ip=c.max_submissions_per_ip or 1,
            created_at=c.created_at,
        )
        for c in cohorts
    ]


@router.post("/cohorts", response_model=CohortResponse, dependencies=[Depends(require_admin)])
async def create_cohort(req: CreateCohortRequest, db: AsyncSession = Depends(get_db)):
    cohort_id = uuid.uuid4()
    empty_config = {
        "version": "1.0",
        "title": "Untitled Survey",
        "questions": [],
        "question_groups": [],
    }

    cohort = Cohort(
        id=cohort_id,
        name=req.name,
        course_name=req.course_name,
        survey_config=empty_config,
        active_version="v1",
        max_submissions_per_ip=1,
        created_at=datetime.utcnow(),
    )
    db.add(cohort)
    await db.commit()

    return CohortResponse(
        id=cohort_id,
        name=req.name,
        course_name=req.course_name,
        max_submissions_per_ip=1,
        created_at=cohort.created_at,
    )


@router.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(require_admin)])
async def get_metrics(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end, survey_version)

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
            if a.get("question_type") == "open" and a.get("answer_raw", "").strip():
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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end, survey_version)
    submissions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    total = len(submissions)
    start_idx = (page - 1) * page_size
    page_items = submissions[start_idx:start_idx + page_size]

    items = []
    for sub in page_items:
        ext = sub.get("extraction")
        # Only return answers that have actual content — skip blank/skipped ones
        answered = [a for a in sub.get("answers", []) if a.get("answer_raw", "").strip()]
        items.append(
            SubmissionSummary(
                id=uuid.UUID(sub["submission_id"]),
                cohort_id=uuid.UUID(sub["cohort_id"]),
                created_at=datetime.fromisoformat(sub["created_at"]) if sub.get("created_at") else datetime.now(),
                completed_at=datetime.fromisoformat(sub["completed_at"]) if sub.get("completed_at") else None,
                status=sub["status"],
                time_to_complete_sec=sub.get("time_to_complete_sec"),
                survey_version=sub.get("survey_version"),
                ip_hash=sub.get("ip_hash"),
                answers=answered,
                extraction=ext,
            )
        )

    return PaginatedResponses(items=items, total=total, page=page, page_size=page_size)


async def _get_cohort_meta(db: AsyncSession, cohort_id: Optional[uuid.UUID]) -> tuple[str, str]:
    """Return (cohort_name, course_name) for export headers."""
    if not cohort_id:
        return ("", "")
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        return ("", "")
    return (cohort.name or "", cohort.course_name or "")


@router.get("/export/raw.csv", dependencies=[Depends(require_admin)])
async def export_raw_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    completed.sort(key=lambda x: x.get("created_at", ""))
    cohort_name, course_name = await _get_cohort_meta(db, cohort_id)
    csv_data = generate_raw_csv(completed, cohort_name, course_name)
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
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    completed.sort(key=lambda x: x.get("created_at", ""))
    cohort_name, course_name = await _get_cohort_meta(db, cohort_id)
    csv_data = generate_structured_csv(completed, cohort_name, course_name)
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
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    cohort_name, course_name = await _get_cohort_meta(db, cohort_id)
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
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    cohort_name, course_name = await _get_cohort_meta(db, cohort_id)
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
    if cohort_id:
        await db.execute(delete(Event).where(Event.cohort_id == str(cohort_id)))
    else:
        await db.execute(delete(Event))

    await db.commit()
    return {"status": "ok", "deleted": len(subs)}


@router.post("/cohorts/{cohort_id}/settings", dependencies=[Depends(require_admin)])
async def update_cohort_settings(cohort_id: uuid.UUID, req: CohortSettingsRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = result.scalar_one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    cohort.max_submissions_per_ip = req.max_submissions_per_ip
    await db.commit()
    return {"status": "updated", "max_submissions_per_ip": req.max_submissions_per_ip}


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


async def _get_events_for_cohort(
    db: AsyncSession,
    cohort_id: Optional[uuid.UUID],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[dict]:
    q = select(Event)
    if cohort_id:
        q = q.where(Event.cohort_id == str(cohort_id))
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


@router.get("/analytics", dependencies=[Depends(require_admin)])
async def get_analytics(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    events = await _get_events_for_cohort(db, cohort_id, start, end)
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end)

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
            if not a.get("answer_raw", "").strip():
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
            if a.get("question_type") == "open" and a.get("answer_raw", "").strip():
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

    voice_lengths = [len(a.get("answer_raw", "")) for a in open_answers if a.get("input_mode") == "voice" and a.get("answer_raw")]
    text_lengths = [len(a.get("answer_raw", "")) for a in open_answers if a.get("input_mode") != "voice" and a.get("answer_raw")]

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
    }


@router.get("/export/user-testing.csv", dependencies=[Depends(require_admin)])
async def export_user_testing_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    submissions = await _get_submissions_for_filters(db, cohort_id, start, end)
    events = await _get_events_for_cohort(db, cohort_id, start, end)
    csv_data = generate_user_testing_csv(submissions, events, cohort_id)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=user_testing_export.csv"},
    )
