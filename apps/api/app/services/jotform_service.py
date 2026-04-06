"""JotForm integration — push completed submissions via JotForm API.

Rewritten for DynamoDB: reads submission data from DynamoDB instead of SQLAlchemy.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from boto3.dynamodb.conditions import Attr

from app.config import get_settings
from app.dynamo import get_submissions_table, get_surveys_table

logger = logging.getLogger(__name__)

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


def _build_submission_data(submission: dict, cohort: dict | None) -> dict[str, str]:
    """Build a flat dict for the JotForm API from a DynamoDB submission item."""
    field_map = _get_field_map()
    data: dict[str, str] = {}
    answers = {a["question_id"]: a for a in submission.get("answers", [])}

    followups: dict[str, dict] = {}

    for q_id, jf_qid in field_map.items():
        answer = answers.get(q_id)
        if answer:
            value = _format_answer_value(answer.get("answer_raw"), answer.get("question_type"))

            parts = [value] if value else []
            if answer.get("followup_1_answer"):
                parts.append(answer["followup_1_answer"])
            if answer.get("followup_2_answer"):
                parts.append(answer["followup_2_answer"])

            combined = "\n".join(parts) if parts else ""
            if combined:
                data[f"submission[{jf_qid}]"] = combined

            if answer.get("followup_1") or answer.get("followup_1_answer"):
                followups[q_id] = followups.get(q_id, {})
                if answer.get("followup_1"):
                    followups[q_id]["followup_1_question"] = answer["followup_1"]
                if answer.get("followup_1_answer"):
                    followups[q_id]["followup_1_answer"] = answer["followup_1_answer"]
            if answer.get("followup_2") or answer.get("followup_2_answer"):
                followups[q_id] = followups.get(q_id, {})
                if answer.get("followup_2"):
                    followups[q_id]["followup_2_question"] = answer["followup_2"]
                if answer.get("followup_2_answer"):
                    followups[q_id]["followup_2_answer"] = answer["followup_2_answer"]

    metadata = {
        "submission_id": submission.get("submission_id", ""),
        "cohort_name": cohort.get("name", "") if cohort else "",
        "course_name": cohort.get("course_name", "") if cohort else "",
        "survey_version": submission.get("survey_version") or "",
        "completed_at": submission.get("completed_at") or "",
        "time_to_complete_sec": str(submission.get("time_to_complete_sec") or ""),
    }

    if followups:
        metadata["followups"] = followups

    extraction = submission.get("extraction")
    if extraction:
        metadata["ext_what_was_tried"] = extraction.get("what_was_tried") or ""
        metadata["ext_planned_workflow"] = extraction.get("planned_task_or_workflow") or ""
        metadata["ext_outcome"] = extraction.get("outcome_or_expected_outcome") or ""
        metadata["ext_barriers"] = " | ".join(extraction.get("barriers", []))
        metadata["ext_enablers"] = " | ".join(extraction.get("enablers", []))
        metadata["ext_public_benefit"] = extraction.get("public_benefit") or ""
        metadata["ext_top_themes"] = " | ".join(extraction.get("top_themes", []))
        metadata["ext_success_story"] = extraction.get("success_story_candidate") or ""

    data["submission[13]"] = json.dumps(metadata, ensure_ascii=False)

    return data


async def push_to_jotform(submission_data: dict[str, str], submission_id: uuid.UUID) -> dict:
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
        logger.info("JotForm sync successful for %s (ID: %s)", submission_id, jf_submission_id)
        return {"success": True, "error": None, "response": result}
    else:
        error_msg = f"JotForm API returned {response.status_code}: {response.text}"
        logger.warning("JotForm sync failed for %s: %s", submission_id, error_msg)
        return {"success": False, "error": error_msg, "response": None}


async def sync_submission(submission_id: uuid.UUID) -> dict:
    """Load a completed submission from DynamoDB and push it to JotForm."""
    if not _is_configured():
        return {"success": False, "error": "JotForm not configured"}

    try:
        subs_table = get_submissions_table()
        surveys_table = get_surveys_table()

        from app.dynamo import scan_all_items
        items = scan_all_items(
            subs_table,
            FilterExpression=Attr("submission_id").eq(str(submission_id)),
        )
        if not items:
            return {"success": False, "error": "Submission not found"}

        submission = items[0]

        if submission.get("status") != "completed":
            return {"success": False, "error": "Submission not completed"}

        if submission.get("jotform_synced_at"):
            return {"success": True, "error": None}

        cohort_id = submission.get("cohort_id")
        cohort_result = surveys_table.get_item(
            Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"}
        )
        cohort = cohort_result.get("Item")

        submission_data = _build_submission_data(submission, cohort)
        push_result = await push_to_jotform(submission_data, submission_id)

        if push_result["success"]:
            subs_table.update_item(
                Key={"pk": submission["pk"], "sk": submission["sk"]},
                UpdateExpression="SET jotform_synced_at = :now",
                ExpressionAttributeValues={":now": datetime.now(timezone.utc).isoformat()},
            )

        return push_result

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.warning("JotForm sync error for %s: %s", submission_id, error_msg)
        return {"success": False, "error": error_msg}
