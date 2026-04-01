"""Qualtrics integration — push completed submissions via Response Import API.

Follows the same graceful-degradation pattern as jotform_service:
skip silently when not configured, log errors but never break the main flow.

Qualtrics API: POST /API/v3/surveys/{surveyId}/responses
Docs: https://api.qualtrics.com/
"""
import json
import logging
import uuid
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models import Submission, Answer, Extraction, Cohort

logger = logging.getLogger(__name__)

# InnovateUS question ID → Qualtrics QID (from SV_dg0xjTuF2wnQxSK)
DEFAULT_QID_MAP: dict[str, str] = {
    "q1_recommend": "QID1",
    "q2_confidence": "QID2",
    "q3_clarity": "QID3",
    "q4_likely_uses": "QID4",
    "q5_impact": "QID5",
    "q8_exercises": "QID6",
    "q6_most_impactful": "QID7",
    "q7_prepared_task": "QID8",
    "q9_feedback": "QID9",
}

# MCQ text → Qualtrics recode value (integer)
RECODE_MAPS: dict[str, dict[str, int]] = {
    "q2_confidence": {
        "Very confident": 1,
        "Somewhat confident": 2,
        "A little confident": 3,
        "Not confident": 4,
        "I am not using generative AI yet": 5,
    },
    "q3_clarity": {
        "Yes": 1,
        "Somewhat": 2,
        "No": 3,
        "Still unsure": 4,
    },
    "q4_likely_uses": {
        "Create content (for example, text, images, audio, video)": 1,
        "Edit content (for example, text, images, audio, video)": 2,
        "Summarize or synthesize text": 3,
        "Sort or organize multiple texts": 4,
        "Analyze, sort, label, or organize data": 5,
        "Conduct research": 6,
        "Translate into other languages or simplify into plain language": 7,
        "Simulate conversations": 8,
        "Write or analyze computer code": 9,
    },
    "q5_impact": {
        "Easier": 1,
        "Harder": 2,
        "Neither": 3,
        "Do not know": 4,
    },
    "q8_exercises": {
        "No, I did not have enough time to attempt the exercises": 1,
        "No, I decided not to do the exercises": 2,
        "No, I was not able to access the appropriate websites or tools": 3,
        "Yes, I attempted but did not complete any exercises": 4,
        "Yes, I completed some of the exercises": 5,
        "Yes, I completed all of the exercises": 6,
    },
}

# Questions that are open-ended text entry
TEXT_ENTRY_QUESTIONS = {"q6_most_impactful", "q7_prepared_task", "q9_feedback"}

ALL_QUESTION_IDS = list(DEFAULT_QID_MAP.keys())


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.qualtrics_api_token and s.qualtrics_survey_id and s.qualtrics_datacenter_id)


def _build_answer_value(question_id: str, answer_raw: str | None, question_type: str | None):
    """Convert an answer to the format Qualtrics expects for the values dict."""
    if not answer_raw:
        return None

    qid = DEFAULT_QID_MAP.get(question_id)
    if not qid:
        return None

    # NPS / rating: send integer directly
    if question_id == "q1_recommend":
        try:
            return {qid: int(answer_raw)}
        except (ValueError, TypeError):
            return {qid: answer_raw}

    # Text entry: send via QID_TEXT key
    if question_id in TEXT_ENTRY_QUESTIONS:
        return {f"{qid}_TEXT": answer_raw}

    # Multi-select: Qualtrics checkbox QIDs don't accept _TEXT.
    # Store as a pipe-separated embedded data field using the question_id as key.
    if question_type == "multi":
        try:
            items = json.loads(answer_raw)
            if isinstance(items, list):
                return {f"{question_id}_answer": " | ".join(str(i) for i in items)}
        except (json.JSONDecodeError, TypeError):
            pass
        return {f"{question_id}_answer": answer_raw}

    # MCQ: map text to recode value
    if question_id in RECODE_MAPS:
        recode_map = RECODE_MAPS[question_id]
        recode = recode_map.get(answer_raw)
        if recode is not None:
            return {qid: recode}
        return {qid: answer_raw}

    return {qid: answer_raw}


def _build_payload(
    submission: Submission,
    answers: dict[str, Answer],
    extraction: Extraction | None,
    cohort: Cohort | None,
) -> dict:
    """Build the full Qualtrics Response Import API payload."""
    values: dict = {"finished": 1, "status": 1}
    embedded: dict[str, str] = {}

    # Map each answer to Qualtrics values
    for q_id, qid in DEFAULT_QID_MAP.items():
        answer = answers.get(q_id)
        if answer and answer.answer_raw:
            result = _build_answer_value(q_id, answer.answer_raw, answer.question_type)
            if result:
                values.update(result)

    # Per-question metadata (input_mode, vagueness, followups) — sent in values
    for q_id in ALL_QUESTION_IDS:
        answer = answers.get(q_id)
        if answer:
            values[f"{q_id}_input_mode"] = answer.input_mode or "none"
            if answer.is_vague is not None:
                values[f"{q_id}_is_vague"] = str(answer.is_vague).lower()
            if answer.followup_1:
                values[f"{q_id}_followup_1_q"] = answer.followup_1
            if answer.followup_1_answer:
                values[f"{q_id}_followup_1_a"] = answer.followup_1_answer
            if answer.followup_2:
                values[f"{q_id}_followup_2_q"] = answer.followup_2
            if answer.followup_2_answer:
                values[f"{q_id}_followup_2_a"] = answer.followup_2_answer

    # Submission metadata
    values["submission_id"] = str(submission.id)
    values["cohort_name"] = cohort.name if cohort else ""
    values["course_name"] = cohort.course_name if cohort else ""
    values["survey_version"] = submission.survey_version or ""
    values["completed_at"] = submission.completed_at.isoformat() if submission.completed_at else ""
    values["time_to_complete_sec"] = str(submission.time_to_complete_sec or "")
    values["consent_version"] = submission.consent_version or ""

    # AI extraction
    if extraction:
        values["ext_what_was_tried"] = extraction.what_was_tried or ""
        values["ext_planned_task_or_workflow"] = extraction.planned_task_or_workflow or ""
        values["ext_outcome_or_expected_outcome"] = extraction.outcome_or_expected_outcome or ""
        values["ext_barriers"] = " | ".join(extraction.barriers) if extraction.barriers else ""
        values["ext_enablers"] = " | ".join(extraction.enablers) if extraction.enablers else ""
        values["ext_public_benefit"] = extraction.public_benefit or ""
        values["ext_top_themes"] = " | ".join(extraction.top_themes) if extraction.top_themes else ""
        values["ext_success_story_candidate"] = extraction.success_story_candidate or ""

    return {"values": values}


async def push_to_qualtrics(payload: dict, submission_id: uuid.UUID) -> dict:
    """POST a response to the Qualtrics Response Import API."""
    settings = get_settings()
    url = (
        f"https://{settings.qualtrics_datacenter_id}.qualtrics.com"
        f"/API/v3/surveys/{settings.qualtrics_survey_id}/responses"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={
                "X-API-TOKEN": settings.qualtrics_api_token,
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code in (200, 201):
        result = response.json()
        response_id = result.get("result", {}).get("responseId")
        logger.info(
            "Qualtrics sync successful for submission %s (Qualtrics ID: %s)",
            submission_id, response_id,
        )
        return {"success": True, "error": None, "qualtrics_response_id": response_id}
    else:
        error_msg = f"Qualtrics API returned {response.status_code}: {response.text}"
        logger.warning("Qualtrics sync failed for submission %s: %s", submission_id, error_msg)
        return {"success": False, "error": error_msg, "qualtrics_response_id": None}


async def sync_submission(
    submission_id: uuid.UUID, db: AsyncSession, force: bool = False,
) -> dict:
    """Load a completed submission and push it to Qualtrics.

    Returns a status dict. Raises nothing — all errors are caught and logged.
    """
    if not _is_configured():
        return {"success": False, "error": "Qualtrics not configured"}

    try:
        submission = await db.get(Submission, submission_id)
        if not submission:
            return {"success": False, "error": "Submission not found"}

        if submission.status != "completed":
            return {"success": False, "error": "Submission not completed"}

        if submission.qualtrics_synced_at is not None and not force:
            logger.debug("Submission %s already synced to Qualtrics, skipping", submission_id)
            return {"success": True, "error": None}

        result = await db.execute(
            select(Answer).where(Answer.submission_id == submission_id)
        )
        answers = {a.question_id: a for a in result.scalars().all()}

        extraction = await db.get(Extraction, submission_id)
        cohort = await db.get(Cohort, submission.cohort_id)

        payload = _build_payload(submission, answers, extraction, cohort)
        push_result = await push_to_qualtrics(payload, submission_id)

        if push_result["success"]:
            submission.qualtrics_synced_at = datetime.utcnow()
            await db.flush()

        return push_result

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.warning("Qualtrics sync error for submission %s: %s", submission_id, error_msg)
        return {"success": False, "error": error_msg}
