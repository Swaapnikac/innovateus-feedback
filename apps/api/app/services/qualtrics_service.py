"""Qualtrics integration — push completed submissions via CSV import API.

Follows the same graceful-degradation pattern as ai_service.py:
skip silently when not configured, log errors but never break the main flow.
"""
import csv
import io
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

# Mapping from InnovateUS question IDs to Qualtrics QID column names.
# Derived from Qualtrics CSV export (March 30, 2026).
DEFAULT_FIELD_MAP: dict[str, str] = {
    "q1_recommend": "QID1",
    "q2_confidence": "QID2",
    "q3_clarity": "QID3",
    "q4_likely_uses": "QID4",
    "q5_impact": "QID5",
    "q8_exercises": "QID6",
    "q6_most_impactful": "QID7_TEXT",
    "q7_prepared_task": "QID8_TEXT",
    "q9_feedback": "QID9_TEXT",
}


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.qualtrics_api_token and s.qualtrics_data_center and s.qualtrics_survey_id)


def _get_field_map() -> dict[str, str]:
    return DEFAULT_FIELD_MAP


def _format_answer_value(answer_raw: str | None, question_type: str | None) -> str:
    """Format an answer value for Qualtrics CSV. Mirrors export_service._format_answer."""
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


def _build_csv_row(
    submission: Submission,
    answers: dict[str, Answer],
    extraction: Extraction | None,
    cohort: Cohort | None,
) -> dict[str, str]:
    """Assemble a single dict mapping Qualtrics column names to values."""
    field_map = _get_field_map()
    row: dict[str, str] = {}

    # --- Metadata as embedded data ---
    row["ExternalDataReference"] = str(submission.id)
    row["cohort_name"] = cohort.name if cohort else ""
    row["course_name"] = cohort.course_name if cohort else ""
    row["survey_version"] = submission.survey_version or ""
    row["completed_at"] = submission.completed_at.isoformat() if submission.completed_at else ""
    row["time_to_complete_sec"] = str(submission.time_to_complete_sec or "")

    # --- Survey answers ---
    voice_questions: list[str] = []

    for q_id, qid_col in field_map.items():
        answer = answers.get(q_id)
        if answer:
            row[qid_col] = _format_answer_value(answer.answer_raw, answer.question_type)

            if answer.input_mode == "voice":
                voice_questions.append(q_id)

            # Follow-up questions and answers as embedded data
            if answer.followup_1:
                row[f"{q_id}_followup1_question"] = answer.followup_1
                row[f"{q_id}_followup1_answer"] = answer.followup_1_answer or ""
            if answer.followup_2:
                row[f"{q_id}_followup2_question"] = answer.followup_2
                row[f"{q_id}_followup2_answer"] = answer.followup_2_answer or ""
        else:
            row[qid_col] = ""

    row["voice_questions"] = ",".join(voice_questions)

    # --- AI extraction as embedded data ---
    if extraction:
        row["ext_what_was_tried"] = extraction.what_was_tried or ""
        row["ext_planned_workflow"] = extraction.planned_task_or_workflow or ""
        row["ext_outcome"] = extraction.outcome_or_expected_outcome or ""
        row["ext_barriers"] = " | ".join(extraction.barriers) if extraction.barriers else ""
        row["ext_enablers"] = " | ".join(extraction.enablers) if extraction.enablers else ""
        row["ext_public_benefit"] = extraction.public_benefit or ""
        row["ext_top_themes"] = " | ".join(extraction.top_themes) if extraction.top_themes else ""
        row["ext_success_story"] = extraction.success_story_candidate or ""

    return row


def _format_csv(row: dict[str, str]) -> str:
    """Produce a 2-line CSV string (header + data row)."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(row.keys()))
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue()


async def push_to_qualtrics(csv_content: str, submission_id: uuid.UUID) -> dict:
    """Upload a single-row CSV to the Qualtrics import-responses endpoint."""
    settings = get_settings()
    url = (
        f"https://{settings.qualtrics_data_center}.qualtrics.com"
        f"/API/v3/surveys/{settings.qualtrics_survey_id}/import-responses"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={"X-API-TOKEN": settings.qualtrics_api_token},
            files={"file": ("import.csv", csv_content.encode("utf-8"), "text/csv")},
        )

    if response.status_code in (200, 201):
        result = response.json()
        logger.info(f"Qualtrics sync successful for submission {submission_id}")
        return {"success": True, "error": None, "response": result}
    else:
        error_msg = f"Qualtrics API returned {response.status_code}: {response.text}"
        logger.warning(f"Qualtrics sync failed for submission {submission_id}: {error_msg}")
        return {"success": False, "error": error_msg, "response": None}


async def sync_submission(submission_id: uuid.UUID, db: AsyncSession) -> dict:
    """Load a completed submission and push it to Qualtrics.

    Returns a status dict. Raises nothing — all errors are caught and logged.
    """
    if not _is_configured():
        return {"success": False, "error": "Qualtrics not configured"}

    submission = await db.get(Submission, submission_id)
    if not submission:
        return {"success": False, "error": "Submission not found"}

    if submission.status != "completed":
        return {"success": False, "error": "Submission not completed"}

    if submission.qualtrics_synced_at is not None:
        logger.debug(f"Submission {submission_id} already synced to Qualtrics, skipping")
        return {"success": True, "error": None}

    # Load related data
    result = await db.execute(
        select(Answer).where(Answer.submission_id == submission_id)
    )
    answers = {a.question_id: a for a in result.scalars().all()}

    extraction = await db.get(Extraction, submission_id)
    cohort = await db.get(Cohort, submission.cohort_id)

    # Build and push
    row = _build_csv_row(submission, answers, extraction, cohort)
    csv_content = _format_csv(row)
    push_result = await push_to_qualtrics(csv_content, submission_id)

    if push_result["success"]:
        submission.qualtrics_synced_at = datetime.utcnow()
        await db.commit()

    return push_result
