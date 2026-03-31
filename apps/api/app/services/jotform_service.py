"""JotForm integration — push completed submissions via JotForm API.

Follows the same graceful-degradation pattern as qualtrics_service.py:
skip silently when not configured, log errors but never break the main flow.

JotForm API: PUT /form/{formId}/submissions
Docs: https://api.jotform.com/docs/
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

# Mapping from InnovateUS question IDs to JotForm question IDs (numeric).
# To find your JotForm QIDs:
#   GET https://api.jotform.com/form/{formId}/questions?apiKey={key}
# Update these after creating your JotForm form.
DEFAULT_FIELD_MAP: dict[str, str] = {
    "q1_recommend": "2",
    "q2_confidence": "3",
    "q3_clarity": "4",
    "q4_likely_uses": "5",
    "q5_impact": "6",
    "q8_exercises": "7",
    "q6_most_impactful": "8",
    "q7_prepared_task": "9",
    "q9_feedback": "10",
}


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.jotform_api_key and s.jotform_form_id)


def _get_field_map() -> dict[str, str]:
    return DEFAULT_FIELD_MAP


def _format_answer_value(answer_raw: str | None, question_type: str | None) -> str:
    if not answer_raw:
        return ""
    if question_type == "multi":
        try:
            items = json.loads(answer_raw)
            if isinstance(items, list):
                return " | ".join(str(item) for item in items)
        except (json.JSONDecodeError, TypeError):
            pass
    return answer_raw


def _build_submission_data(
    submission: Submission,
    answers: dict[str, Answer],
    extraction: Extraction | None,
    cohort: Cohort | None,
) -> dict[str, str]:
    """Build a flat dict of submission[qid] -> value for the JotForm API."""
    field_map = _get_field_map()
    data: dict[str, str] = {}

    followups: dict[str, dict] = {}

    for q_id, jf_qid in field_map.items():
        answer = answers.get(q_id)
        if answer:
            value = _format_answer_value(answer.answer_raw, answer.question_type)
            if value:
                data[f"submission[{jf_qid}]"] = value

            if answer.followup_1 or answer.followup_1_answer:
                followups[q_id] = followups.get(q_id, {})
                if answer.followup_1:
                    followups[q_id]["followup_1_question"] = answer.followup_1
                if answer.followup_1_answer:
                    followups[q_id]["followup_1_answer"] = answer.followup_1_answer
            if answer.followup_2 or answer.followup_2_answer:
                followups[q_id] = followups.get(q_id, {})
                if answer.followup_2:
                    followups[q_id]["followup_2_question"] = answer.followup_2
                if answer.followup_2_answer:
                    followups[q_id]["followup_2_answer"] = answer.followup_2_answer

    metadata = {
        "submission_id": str(submission.id),
        "cohort_name": cohort.name if cohort else "",
        "course_name": cohort.course_name if cohort else "",
        "survey_version": submission.survey_version or "",
        "completed_at": submission.completed_at.isoformat() if submission.completed_at else "",
        "time_to_complete_sec": str(submission.time_to_complete_sec or ""),
    }

    if followups:
        metadata["followups"] = followups

    if extraction:
        metadata["ext_what_was_tried"] = extraction.what_was_tried or ""
        metadata["ext_planned_workflow"] = extraction.planned_task_or_workflow or ""
        metadata["ext_outcome"] = extraction.outcome_or_expected_outcome or ""
        metadata["ext_barriers"] = " | ".join(extraction.barriers) if extraction.barriers else ""
        metadata["ext_enablers"] = " | ".join(extraction.enablers) if extraction.enablers else ""
        metadata["ext_public_benefit"] = extraction.public_benefit or ""
        metadata["ext_top_themes"] = " | ".join(extraction.top_themes) if extraction.top_themes else ""
        metadata["ext_success_story"] = extraction.success_story_candidate or ""

    data["submission[13]"] = json.dumps(metadata, ensure_ascii=False)

    return data


async def push_to_jotform(submission_data: dict[str, str], submission_id: uuid.UUID) -> dict:
    """POST submission data to the JotForm API."""
    settings = get_settings()
    url = f"{settings.jotform_api_url}/form/{settings.jotform_form_id}/submissions"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={
                "APIKEY": settings.jotform_api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=submission_data,
        )

    if response.status_code in (200, 201):
        result = response.json()
        jf_submission_id = result.get("content", {}).get("submissionID")
        logger.info(
            "JotForm sync successful for submission %s (JotForm ID: %s)",
            submission_id, jf_submission_id,
        )
        return {"success": True, "error": None, "response": result}
    else:
        error_msg = f"JotForm API returned {response.status_code}: {response.text}"
        logger.warning("JotForm sync failed for submission %s: %s", submission_id, error_msg)
        return {"success": False, "error": error_msg, "response": None}


async def sync_submission(submission_id: uuid.UUID, db: AsyncSession) -> dict:
    """Load a completed submission and push it to JotForm.

    Returns a status dict. Raises nothing — all errors are caught and logged.
    """
    if not _is_configured():
        return {"success": False, "error": "JotForm not configured"}

    submission = await db.get(Submission, submission_id)
    if not submission:
        return {"success": False, "error": "Submission not found"}

    if submission.status != "completed":
        return {"success": False, "error": "Submission not completed"}

    if submission.jotform_synced_at is not None:
        logger.debug("Submission %s already synced to JotForm, skipping", submission_id)
        return {"success": True, "error": None}

    result = await db.execute(
        select(Answer).where(Answer.submission_id == submission_id)
    )
    answers = {a.question_id: a for a in result.scalars().all()}

    extraction = await db.get(Extraction, submission_id)
    cohort = await db.get(Cohort, submission.cohort_id)

    submission_data = _build_submission_data(submission, answers, extraction, cohort)
    push_result = await push_to_jotform(submission_data, submission_id)

    if push_result["success"]:
        submission.jotform_synced_at = datetime.utcnow()
        await db.commit()

    return push_result
