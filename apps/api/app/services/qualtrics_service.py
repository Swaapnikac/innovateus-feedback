"""Qualtrics integration — push completed submissions via Response Import API.

Also maintains submission-level sync-health fields so S8 ("Qualtrics sync
reliability >95%") can be measured directly on the submission row without
having to inspect Qualtrics itself:

- qualtrics_sync_attempt_count
- qualtrics_sync_first_attempt_at / qualtrics_sync_last_attempt_at
- qualtrics_sync_last_error
- qualtrics_sync_latency_ms
- qualtrics_response_id
- qualtrics_synced_at (existing)
"""
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx

from app.config import get_settings

PAYLOAD_VERSION = "v1.2024-04"

logger = logging.getLogger(__name__)

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

TEXT_ENTRY_QUESTIONS = {"q6_most_impactful", "q7_prepared_task", "q9_feedback"}
ALL_QUESTION_IDS = list(DEFAULT_QID_MAP.keys())


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.qualtrics_api_token and s.qualtrics_survey_id and s.qualtrics_datacenter_id)


def _build_answer_value(question_id: str, answer_raw: str | None, question_type: str | None):
    if not answer_raw:
        return None
    qid = DEFAULT_QID_MAP.get(question_id)
    if not qid:
        return None

    if question_id == "q1_recommend":
        try:
            return {qid: int(answer_raw)}
        except (ValueError, TypeError):
            return {qid: answer_raw}

    if question_id in TEXT_ENTRY_QUESTIONS:
        return {f"{qid}_TEXT": answer_raw}

    if question_type == "multi":
        try:
            items = json.loads(answer_raw)
            if isinstance(items, list):
                return {f"{question_id}_answer": " | ".join(str(i) for i in items)}
        except (json.JSONDecodeError, TypeError):
            pass
        return {f"{question_id}_answer": answer_raw}

    if question_id in RECODE_MAPS:
        recode_map = RECODE_MAPS[question_id]
        recode = recode_map.get(answer_raw)
        if recode is not None:
            return {qid: recode}
        return {qid: answer_raw}

    return {qid: answer_raw}


def _build_payload(submission: dict, cohort_name: str, course_name: str) -> dict:
    values: dict = {"finished": 1, "status": 1}
    answers = {a["question_id"]: a for a in submission.get("answers", [])}

    for q_id, qid in DEFAULT_QID_MAP.items():
        answer = answers.get(q_id)
        if answer and answer.get("answer_raw"):
            result = _build_answer_value(q_id, answer["answer_raw"], answer.get("question_type"))
            if result:
                values.update(result)

    for q_id in ALL_QUESTION_IDS:
        answer = answers.get(q_id)
        if answer:
            values[f"{q_id}_input_mode"] = answer.get("input_mode") or "none"
            if answer.get("is_vague") is not None:
                values[f"{q_id}_is_vague"] = str(answer["is_vague"]).lower()
            if answer.get("followup_1"):
                values[f"{q_id}_followup_1_q"] = answer["followup_1"]
            if answer.get("followup_1_answer"):
                values[f"{q_id}_followup_1_a"] = answer["followup_1_answer"]
            if answer.get("followup_2"):
                values[f"{q_id}_followup_2_q"] = answer["followup_2"]
            if answer.get("followup_2_answer"):
                values[f"{q_id}_followup_2_a"] = answer["followup_2_answer"]

    values["response_source"] = "Voice Feedback Tool"
    values["submission_id"] = submission.get("submission_id", "")
    values["cohort_name"] = cohort_name
    values["course_name"] = course_name
    values["survey_version"] = submission.get("survey_version") or ""
    values["completed_at"] = submission.get("completed_at") or ""
    values["time_to_complete_sec"] = str(submission.get("time_to_complete_sec") or "")
    values["consent_version"] = submission.get("consent_version") or ""

    extraction = submission.get("extraction")
    if extraction:
        values["ext_what_was_tried"] = extraction.get("what_was_tried") or ""
        values["ext_planned_task_or_workflow"] = extraction.get("planned_task_or_workflow") or ""
        values["ext_outcome_or_expected_outcome"] = extraction.get("outcome_or_expected_outcome") or ""
        values["ext_barriers"] = " | ".join(extraction.get("barriers") or [])
        values["ext_enablers"] = " | ".join(extraction.get("enablers") or [])
        values["ext_public_benefit"] = extraction.get("public_benefit") or ""
        values["ext_top_themes"] = " | ".join(extraction.get("top_themes") or [])
        values["ext_success_story_candidate"] = extraction.get("success_story_candidate") or ""

    return {"values": values}


async def push_to_qualtrics(payload: dict, submission_id: uuid.UUID) -> dict:
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
        logger.info("Qualtrics sync successful for %s (ID: %s)", submission_id, response_id)
        return {"success": True, "error": None, "qualtrics_response_id": response_id}
    else:
        error_msg = f"Qualtrics API returned {response.status_code}: {response.text}"
        logger.warning("Qualtrics sync failed for %s: %s", submission_id, error_msg)
        return {"success": False, "error": error_msg, "qualtrics_response_id": None}


async def sync_submission(submission_id: uuid.UUID, force: bool = False) -> dict:
    if not _is_configured():
        return {"success": False, "error": "Qualtrics not configured"}

    try:
        from sqlalchemy import select
        from app.db import async_session
        from app.models import Submission, Answer, Extraction, Cohort

        async with async_session() as db:
            sub_result = await db.execute(select(Submission).where(Submission.id == submission_id))
            sub = sub_result.scalar_one_or_none()

            if not sub:
                return {"success": False, "error": "Submission not found"}
            if sub.status != "completed":
                return {"success": False, "error": "Submission not completed"}
            if sub.qualtrics_synced_at and not force:
                return {"success": True, "error": None}

            cohort_result = await db.execute(select(Cohort).where(Cohort.id == sub.cohort_id))
            cohort = cohort_result.scalar_one_or_none()

            answers_result = await db.execute(select(Answer).where(Answer.submission_id == submission_id))
            answers = answers_result.scalars().all()

            ext_result = await db.execute(select(Extraction).where(Extraction.submission_id == submission_id))
            extraction = ext_result.scalar_one_or_none()

            answers_list = [
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

            submission_dict = {
                "submission_id": str(sub.id),
                "survey_version": sub.survey_version,
                "completed_at": sub.completed_at.isoformat() if sub.completed_at else None,
                "time_to_complete_sec": sub.time_to_complete_sec,
                "consent_version": sub.consent_version,
                "answers": answers_list,
                "extraction": ext_dict,
            }

            cohort_name = cohort.name if cohort else ""
            course_name = cohort.course_name if cohort else ""

            payload = _build_payload(submission_dict, cohort_name, course_name)

            # ── Track sync attempt for S8 reliability measurement ──
            attempt_started_at = datetime.now(timezone.utc)
            attempt_monotonic = time.monotonic()
            sub.qualtrics_sync_attempt_count = (sub.qualtrics_sync_attempt_count or 0) + 1
            if sub.qualtrics_sync_first_attempt_at is None:
                sub.qualtrics_sync_first_attempt_at = attempt_started_at
            sub.qualtrics_sync_last_attempt_at = attempt_started_at

            push_result = await push_to_qualtrics(payload, submission_id)

            latency_ms = int((time.monotonic() - attempt_monotonic) * 1000)
            sub.qualtrics_sync_latency_ms = latency_ms

            if push_result["success"]:
                sub.qualtrics_synced_at = datetime.now(timezone.utc)
                sub.qualtrics_sync_last_error = None
                if push_result.get("qualtrics_response_id"):
                    sub.qualtrics_response_id = push_result["qualtrics_response_id"]
            else:
                sub.qualtrics_sync_last_error = (push_result.get("error") or "")[:1000]

            await db.commit()

            return push_result

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.warning("Qualtrics sync error for %s: %s", submission_id, error_msg)
        # Try to record the failure on the submission so it shows up on the
        # dashboard, even if the main flow crashed mid-way.
        try:
            from sqlalchemy import select
            from app.db import async_session
            from app.models import Submission

            async with async_session() as db:
                sub_result = await db.execute(select(Submission).where(Submission.id == submission_id))
                sub = sub_result.scalar_one_or_none()
                if sub is not None:
                    sub.qualtrics_sync_attempt_count = (sub.qualtrics_sync_attempt_count or 0) + 1
                    now_ts = datetime.now(timezone.utc)
                    if sub.qualtrics_sync_first_attempt_at is None:
                        sub.qualtrics_sync_first_attempt_at = now_ts
                    sub.qualtrics_sync_last_attempt_at = now_ts
                    sub.qualtrics_sync_last_error = error_msg[:1000]
                    await db.commit()
        except Exception:
            pass
        return {"success": False, "error": error_msg}
