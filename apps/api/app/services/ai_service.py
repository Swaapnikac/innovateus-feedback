import json
import logging
from pathlib import Path
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[4] / "docs" / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


def _has_api_key() -> bool:
    key = get_settings().openai_api_key
    return bool(key) and key != "sk-your-key-here" and len(key) > 10


async def detect_vagueness(question_text: str, answer_text: str) -> dict:
    if not _has_api_key():
        return {"is_vague": False, "reason": "AI analysis unavailable", "missing_info_types": []}

    try:
        client = _get_client()
        system_prompt = _load_prompt("vagueness")

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": question_text,
                        "answer": answer_text,
                    }),
                },
            ],
            temperature=0.1,
        )

        result = json.loads(response.choices[0].message.content)
        return {
            "is_vague": result.get("is_vague", False),
            "reason": result.get("reason", ""),
            "missing_info_types": result.get("missing_info_types", []),
        }
    except Exception as e:
        logger.warning(f"Vagueness detection failed: {e}")
        return {"is_vague": False, "reason": "Analysis unavailable", "missing_info_types": []}


async def generate_followups(
    question_text: str,
    answer_text: str,
    missing_info_types: list[str],
) -> list[str]:
    if not _has_api_key():
        return []

    try:
        client = _get_client()
        system_prompt = _load_prompt("followup")

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": question_text,
                        "answer": answer_text,
                        "missing_info_types": missing_info_types,
                    }),
                },
            ],
            temperature=0.3,
        )

        result = json.loads(response.choices[0].message.content)
        followups = result.get("followups", [])
        return followups[:2]
    except Exception as e:
        logger.warning(f"Follow-up generation failed: {e}")
        return []


async def extract_structured(answers: list[dict]) -> dict:
    empty_result = {
        "what_was_tried": None,
        "planned_task_or_workflow": None,
        "outcome_or_expected_outcome": None,
        "barriers": [],
        "enablers": [],
        "public_benefit": None,
        "top_themes": [],
        "success_story_candidate": None,
    }

    if not _has_api_key():
        return empty_result

    try:
        client = _get_client()
        system_prompt = _load_prompt("extraction")

        response = await client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "answers": answers,
                    }),
                },
            ],
            temperature=0.1,
        )

        result = json.loads(response.choices[0].message.content)
        return {
            "what_was_tried": result.get("what_was_tried"),
            "planned_task_or_workflow": result.get("planned_task_or_workflow"),
            "outcome_or_expected_outcome": result.get("outcome_or_expected_outcome"),
            "barriers": result.get("barriers", []),
            "enablers": result.get("enablers", []),
            "public_benefit": result.get("public_benefit"),
            "top_themes": result.get("top_themes", []),
            "success_story_candidate": result.get("success_story_candidate"),
        }
    except Exception as e:
        logger.warning(f"Structured extraction failed: {e}")
        return empty_result
