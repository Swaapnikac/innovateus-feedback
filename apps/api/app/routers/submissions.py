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
    ClientEnvRequest,
)
from app.services.ai_service import extract_structured, detect_vagueness
from app.services.pii_service import strip_pii
from app.services.user_agent_service import parse_user_agent
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

_OPEN_TYPES = {"open", "short_text"}


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


def _word_count(text: str | None) -> int:
    if not text:
        return 0
    return len([w for w in text.split() if w.strip()])


def _char_count(text: str | None) -> int:
    if not text:
        return 0
    return len(text)


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein for small strings — used for transcript edit distance.

    Not optimised — we only run this on a single transcript per answer save,
    capped at a reasonable length by the model.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Cap to avoid pathological costs
    if len(a) > 2000 or len(b) > 2000:
        return abs(len(a) - len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            )
        prev = curr
    return prev[-1]


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

    now = datetime.now(timezone.utc)
    submission = Submission(
        id=uuid.uuid4(),
        cohort_id=req.cohort_id,
        status="started",
        consent_version=req.consent_version,
        survey_version=cohort.active_version,
        ip_hash=ip_hash,
        client_metadata=req.client_metadata,
        created_at=now,
        last_activity_at=now,
    )
    db.add(submission)
    await db.flush()

    return StartSubmissionResponse(submission_id=submission.id)


@router.post("/submissions/{submission_id}/client-env")
async def save_client_env(
    submission_id: uuid.UUID,
    req: ClientEnvRequest,
    db: AsyncSession = Depends(get_db),
):
    """Capture the participant's browser/OS/device/network characteristics.

    Called once at the start of the survey. Writes parsed UA components so the
    dashboard doesn't have to re-parse on every query. H6 signal source.
    """
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    sub.user_agent = req.user_agent
    sub.screen_size = req.screen_size
    sub.connection_type = req.connection_type
    sub.page_load_time_ms = req.page_load_time_ms
    sub.voice_supported_in_browser = req.voice_supported
    if req.mic_permission_status:
        sub.mic_permission_status = req.mic_permission_status

    if req.user_agent:
        ua_parsed = parse_user_agent(req.user_agent)
        sub.browser_name = ua_parsed.get("browser_name") or sub.browser_name
        sub.browser_version = ua_parsed.get("browser_version") or sub.browser_version
        sub.os_name = ua_parsed.get("os_name") or sub.os_name
        sub.os_version = ua_parsed.get("os_version") or sub.os_version
        sub.device_type = ua_parsed.get("device_type") or sub.device_type

    sub.last_activity_at = datetime.now(timezone.utc)
    return {"status": "saved"}


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

    now = datetime.now(timezone.utc)
    is_open = (req.question_type or "").lower() in _OPEN_TYPES
    word_count = _word_count(answer_raw) if is_open else None
    char_count = _char_count(answer_raw) if is_open else None
    fu1_word_count = _word_count(followup_1_answer) if followup_1_answer else 0
    fu2_word_count = _word_count(followup_2_answer) if followup_2_answer else 0

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
        previous_answer = existing.answer_raw or ""
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
        existing.answer_word_count = word_count
        existing.answer_char_count = char_count
        existing.followup_1_word_count = fu1_word_count
        existing.followup_2_word_count = fu2_word_count
        if req.followup_1_input_mode:
            existing.followup_1_input_mode = req.followup_1_input_mode
        if req.followup_2_input_mode:
            existing.followup_2_input_mode = req.followup_2_input_mode
        existing.answer_completed_at = now
        existing.answer_skipped = bool(req.answer_skipped)
        if previous_answer and previous_answer != (answer_raw or ""):
            existing.changed_answer_flag = True
        if req.transcript_raw is not None:
            existing.transcript_raw = strip_pii(req.transcript_raw)
            existing.transcript_final = answer_raw
            if req.transcript_raw and answer_raw and req.transcript_raw != answer_raw:
                existing.transcript_edit_distance = _levenshtein(
                    strip_pii(req.transcript_raw) or "", answer_raw or ""
                )
                existing.user_edited_transcript_flag = True
                existing.edited_after_transcription_flag = True
        if req.voice_duration_sec is not None:
            existing.voice_duration_sec = req.voice_duration_sec
        if existing.answer_started_at:
            try:
                started = existing.answer_started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                existing.answer_duration_sec = max(0, int((now - started).total_seconds()))
            except Exception:
                pass
        if is_open:
            existing.vagueness_score_initial = (
                existing.vagueness_score_initial
                if existing.vagueness_score_initial is not None
                else None
            )
        answer = existing
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
            answer_word_count=word_count,
            answer_char_count=char_count,
            answer_started_at=now,
            answer_completed_at=now,
            answer_duration_sec=0,
            followup_1_input_mode=req.followup_1_input_mode,
            followup_2_input_mode=req.followup_2_input_mode,
            followup_1_word_count=fu1_word_count,
            followup_2_word_count=fu2_word_count,
            answer_skipped=bool(req.answer_skipped),
            transcript_raw=strip_pii(req.transcript_raw) if req.transcript_raw else None,
            transcript_final=answer_raw if req.transcript_raw else None,
            voice_duration_sec=req.voice_duration_sec,
        )
        if req.transcript_raw and answer_raw and req.transcript_raw != answer_raw:
            answer.transcript_edit_distance = _levenshtein(
                strip_pii(req.transcript_raw) or "", answer_raw or ""
            )
            answer.user_edited_transcript_flag = True
            answer.edited_after_transcription_flag = True
        db.add(answer)

    # ── Vagueness tracking on the follow-up answers (H2 / S3) ──
    # We only re-classify a follow-up answer when it changes and is non-empty.
    try:
        if followup_1_answer:
            fu1_result = await detect_vagueness(req.followup_1 or "", followup_1_answer)
            answer.followup_1_is_vague = fu1_result.get("is_vague")
            answer.followup_1_vagueness_score = fu1_result.get("vagueness_score")
        if followup_2_answer:
            fu2_result = await detect_vagueness(req.followup_2 or "", followup_2_answer)
            answer.followup_2_is_vague = fu2_result.get("is_vague")
            answer.followup_2_vagueness_score = fu2_result.get("vagueness_score")
    except Exception as e:
        logger.debug(f"Follow-up vagueness re-classification failed: {e}")

    # Derived specificity fields
    initial_vague = bool(answer.is_vague)
    if answer.followup_2_answer is not None:
        last_vague = answer.followup_2_is_vague
    elif answer.followup_1_answer is not None:
        last_vague = answer.followup_1_is_vague
    else:
        last_vague = answer.is_vague
    if last_vague is not None:
        answer.final_response_specific_flag = not bool(last_vague)
    if initial_vague and last_vague is not None:
        answer.specificity_improved_after_followups_flag = bool(
            initial_vague and not last_vague
        )
    else:
        answer.specificity_improved_after_followups_flag = False

    # Skipped flags on follow-ups (shown but not answered)
    if req.followup_1 and not followup_1_answer:
        answer.followup_1_skipped_flag = True
    else:
        answer.followup_1_skipped_flag = False
    if req.followup_2 and not followup_2_answer:
        answer.followup_2_skipped_flag = True
    else:
        answer.followup_2_skipped_flag = False

    # ── Submission-level voice rollups ──
    if sub.started_in_voice is None and req.input_mode in {"voice", "text"}:
        sub.started_in_voice = req.input_mode == "voice"
    sub.ended_in_voice = req.input_mode == "voice"
    sub.last_activity_at = now

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


def _split_extraction(extraction_with_meta: dict) -> tuple[dict, dict]:
    meta = extraction_with_meta.get("_meta") or {}
    cleaned = {k: v for k, v in extraction_with_meta.items() if k != "_meta"}
    return cleaned, meta


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
        raw = await extract_structured(answers_for_extraction)
        extraction_data, _ = _split_extraction(raw)
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
    extraction_meta: dict = {}
    try:
        raw = await extract_structured(answers_for_extraction)
        extraction_data, extraction_meta = _split_extraction(raw)
    except Exception as e:
        logger.warning(f"Extraction failed for submission {submission_id}: {e}")
        extraction_data = dict(_EMPTY_EXTRACTION)
        extraction_meta = {
            "model_name": None,
            "prompt_version": None,
            "run_at": datetime.now(timezone.utc),
            "success_flag": False,
            "error_message": str(e)[:500],
        }

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
    sub.last_activity_at = now
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
        ext_row.model_name = extraction_meta.get("model_name")
        ext_row.model_version = extraction_meta.get("model_version")
        ext_row.prompt_version = extraction_meta.get("prompt_version")
        ext_row.run_at = extraction_meta.get("run_at")
        ext_row.success_flag = extraction_meta.get("success_flag")
        ext_row.error_message = extraction_meta.get("error_message")
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
            model_name=extraction_meta.get("model_name"),
            model_version=extraction_meta.get("model_version"),
            prompt_version=extraction_meta.get("prompt_version"),
            run_at=extraction_meta.get("run_at"),
            success_flag=extraction_meta.get("success_flag"),
            error_message=extraction_meta.get("error_message"),
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
    if req.voice_experience_rating is not None:
        sub.voice_experience_rating = req.voice_experience_rating
    if req.voice_experience_text is not None:
        sub.voice_experience_text = strip_pii(req.voice_experience_text)
    if req.would_use_again is not None:
        sub.would_use_again_flag = req.would_use_again
    if req.preferred_mode_next_time is not None:
        sub.preferred_mode_next_time = req.preferred_mode_next_time
    if req.confusion_flag is not None:
        sub.confusion_flag = req.confusion_flag
    if req.confusion_step is not None:
        sub.confusion_step = req.confusion_step
    if req.reported_issue_flag is not None:
        sub.reported_issue_flag = req.reported_issue_flag
    if req.reported_issue_text is not None:
        sub.reported_issue_text = strip_pii(req.reported_issue_text)

    return {"status": "saved", "rating": req.rating}
