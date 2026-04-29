import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from openai import AsyncOpenAI
from app.config import get_settings
from app.services.pii_service import REDACTED_TOKEN, strip_pii, strip_pii_with_meta

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[4] / "docs" / "prompts"

# Cached prompt hashes so we can stamp extraction rows with a reproducible
# prompt_version without re-reading the file on every call.
_PROMPT_HASH_CACHE: dict[str, str] = {}


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _clean_for_ai(text: str | None) -> str:
    """Strip PII from ``text`` before handing it to OpenAI.

    This is the single chokepoint every AI call must use. Regex-based for
    speed and determinism; the AI-based detector in
    :func:`detect_and_redact_pii_with_ai` is layered on top for free-form
    names/addresses that regex cannot catch.

    Never raises — always returns a safe string.
    """
    if not text:
        return text or ""
    try:
        return strip_pii(text) or ""
    except Exception as e:  # pragma: no cover — regex should not fail
        logger.warning(f"strip_pii failed, falling back to original text: {e}")
        return text


# ──────────────────────────────────────────────────────────────────────────────
# F3 — AI-based PII detector (layered on top of the regex stripper)
# ──────────────────────────────────────────────────────────────────────────────
# GPT-5-mini reads free-form text and flags context-dependent PII (names,
# ambiguous addresses) that regex alone cannot catch reliably. Results are
# cached by sha256 so repeated identical inputs (same question re-asked, same
# typed answer saved twice) don't re-hit the API.
_PII_CACHE: dict[str, tuple[str, int, list[str]]] = {}
_PII_CACHE_MAX = 500


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _apply_ai_redactions(text: str, redactions: list[dict]) -> tuple[str, int, set[str]]:
    count = 0
    cats: set[str] = set()
    for r in redactions or []:
        if not isinstance(r, dict):
            continue
        span = r.get("span")
        category = r.get("category", "other")
        if not isinstance(span, str) or not span.strip():
            continue
        # Avoid redacting the neutral placeholder itself (``***`` would match
        # aggressively otherwise) or any legacy ``[REDACTED_*]`` tokens left
        # over from older cached data.
        if span == REDACTED_TOKEN or span.startswith("[REDACTED_"):
            continue
        new_text = text.replace(span, REDACTED_TOKEN)
        if new_text != text:
            count += 1
            cats.add(_normalise_category(category))
            text = new_text
    return text, count, cats


def _normalise_category(category: str) -> str:
    c = (category or "other").strip().lower()
    mapping = {
        "person_name": "name",
        "name": "name",
        "address": "address",
        "organization_pii": "name",
        "contact": "email",
        "email": "email",
        "phone": "phone",
        "id_number": "id",
        "ssn": "ssn",
        "dob": "dob",
        "other_sensitive": "sensitive",
        "other": "sensitive",
    }
    return mapping.get(c, "sensitive")


async def detect_and_redact_pii_with_ai(text: str | None) -> tuple[str, int, list[str]]:
    """Redact free-form PII (names, contextual addresses) using GPT-5-mini.

    Always runs regex ``strip_pii`` first so the AI only sees pre-cleaned
    input. Falls back to the regex-only output on any failure so we never
    echo raw PII to callers. Results are memoised by sha256 of the
    (already regex-stripped) text.

    Returns: ``(redacted_text, added_redaction_count, category_list)``
    where ``added_redaction_count`` is the number of redactions the AI
    layer added on top of regex. The category list includes both.
    """
    if not text:
        return "", 0, []

    regex_result = strip_pii_with_meta(text)
    pre = regex_result.text
    regex_cats = set(regex_result.categories)

    cache_key = _cache_key(pre)
    if cache_key in _PII_CACHE:
        return _PII_CACHE[cache_key]

    if not _has_api_key():
        final = (pre, regex_result.count, sorted(regex_cats))
        _cache_put(cache_key, final)
        return final

    # Short-circuit: for very short, already-clean inputs ("yes", "no",
    # "none", "not sure", single-word answers) the AI layer has nothing to
    # contribute — it cannot contain a free-form name or address. Skip the
    # round-trip so transcription + save feel instant on tiny answers.
    if len(pre.strip()) < 40 and regex_result.count == 0:
        final = (pre, 0, [])
        _cache_put(cache_key, final)
        return final

    try:
        client = _get_client()
        system_prompt = _load_prompt("pii_redaction")
        response = await client.chat.completions.create(
            model=get_settings().openai_model_pii,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": pre},
            ],
            # PII detection doesn't benefit from deep reasoning — span matching
            # is near-deterministic. Cap the thinking budget so the call returns
            # in <1s instead of 3-5s.
            extra_body={"reasoning_effort": "minimal"},
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        redactions = parsed.get("redactions", [])
        if not isinstance(redactions, list):
            redactions = []
        redacted, ai_count, ai_cats = _apply_ai_redactions(pre, redactions)
        total_count = regex_result.count + ai_count
        all_cats = sorted(regex_cats.union(ai_cats))
        final = (redacted, total_count, all_cats)
        _cache_put(cache_key, final)
        return final
    except Exception as e:
        logger.warning(f"AI PII detection failed: {e}")
        # Fall back to regex-only result. Never echo raw PII to caller.
        final = (pre, regex_result.count, sorted(regex_cats))
        _cache_put(cache_key, final)
        return final


def _cache_put(key: str, value: tuple[str, int, list[str]]) -> None:
    if len(_PII_CACHE) >= _PII_CACHE_MAX:
        # Simple FIFO eviction: drop the oldest ~10% of entries.
        for stale_key in list(_PII_CACHE.keys())[: _PII_CACHE_MAX // 10]:
            _PII_CACHE.pop(stale_key, None)
    _PII_CACHE[key] = value


def prompt_version(name: str) -> str:
    """Return a short hash of the given prompt file contents.

    Used to stamp extractions with ``prompt_version`` so we can tell which
    prompt produced a given extraction, even after the prompt is edited.
    """
    if name in _PROMPT_HASH_CACHE:
        return _PROMPT_HASH_CACHE[name]
    try:
        contents = _load_prompt(name)
    except Exception:
        _PROMPT_HASH_CACHE[name] = "unknown"
        return "unknown"
    digest = hashlib.sha256(contents.encode("utf-8")).hexdigest()[:12]
    _PROMPT_HASH_CACHE[name] = digest
    return digest


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


def _has_api_key() -> bool:
    key = get_settings().openai_api_key
    return bool(key) and key != "sk-your-key-here" and len(key) > 10


def _coerce_score(value, is_vague: bool) -> float | None:
    try:
        score = float(value)
        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return score
    except (TypeError, ValueError):
        return 0.7 if is_vague else 0.1


def _coerce_followups(value, limit: int = 1) -> list[str]:
    """Normalise the ``followups`` field from a model response.

    GPT-5 is told to return ``followups: [...]`` but sometimes wraps the
    question in a string, returns ``null``, or returns an object. Defend
    against every garbage shape so we never 500 on the router.
    """
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple)):
        clean: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                clean.append(item.strip())
            elif isinstance(item, dict):
                for key in ("question", "text", "followup"):
                    if isinstance(item.get(key), str) and item[key].strip():
                        clean.append(item[key].strip())
                        break
        return clean[:limit]
    if isinstance(value, dict):
        for key in ("question", "text", "followup"):
            if isinstance(value.get(key), str) and value[key].strip():
                return [value[key].strip()][:limit]
    return []


async def detect_vagueness(question_text: str, answer_text: str) -> dict:
    if not _has_api_key():
        return {
            "is_vague": False,
            "is_irrelevant": False,
            "reason": "AI analysis unavailable",
            "missing_info_types": [],
            "vagueness_score": None,
        }

    try:
        client = _get_client()
        system_prompt = _load_prompt("vagueness")
        safe_question = _clean_for_ai(question_text)
        safe_answer = _clean_for_ai(answer_text)

        response = await client.chat.completions.create(
            model=get_settings().openai_model_vagueness,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": safe_question,
                        "answer": safe_answer,
                    }),
                },
            ],
            extra_body={"reasoning_effort": "minimal"},
        )

        result = json.loads(response.choices[0].message.content)
        is_vague = bool(result.get("is_vague", False))
        return {
            "is_vague": is_vague,
            "is_irrelevant": bool(result.get("is_irrelevant", False)),
            "reason": result.get("reason", ""),
            "missing_info_types": result.get("missing_info_types", []),
            "vagueness_score": _coerce_score(result.get("vagueness_score"), is_vague),
        }
    except Exception as e:
        logger.warning(f"Vagueness detection failed: {e}")
        return {
            "is_vague": False,
            "is_irrelevant": False,
            "reason": "Analysis unavailable",
            "missing_info_types": [],
            "vagueness_score": None,
            "error": True,
        }


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
        safe_question = _clean_for_ai(question_text)
        safe_answer = _clean_for_ai(answer_text)

        response = await client.chat.completions.create(
            model=get_settings().openai_model_followups,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": safe_question,
                        "answer": safe_answer,
                        "missing_info_types": missing_info_types,
                    }),
                },
            ],
            extra_body={"reasoning_effort": "minimal"},
        )

        result = json.loads(response.choices[0].message.content)
        followups = result.get("followups", [])
        return _coerce_followups(followups, limit=2)
    except Exception as e:
        logger.warning(f"Follow-up generation failed: {e}")
        return []


async def detect_followup_needs_clarification(
    original_question: str,
    original_answer: str,
    followup_question: str,
    followup_answer: str,
) -> dict:
    """Decide whether a FOLLOW-UP answer needs one more clarifying question.

    Uses the ``followup_vagueness`` prompt which is explicitly context-aware:
    it receives the original main question + answer alongside the follow-up
    Q+A, so the model can apply a stricter bar than the initial vagueness
    check (the participant has already had one clarification chance).

    Returns the same shape as ``detect_vagueness_with_followups``.
    """
    if not _has_api_key():
        return {
            "is_vague": False,
            "is_irrelevant": False,
            "reason": "AI analysis unavailable",
            "missing_info_types": [],
            "followups": [],
            "vagueness_score": None,
        }

    try:
        client = _get_client()
        system_prompt = _load_prompt("followup_vagueness")

        response = await client.chat.completions.create(
            model=get_settings().openai_model_followups,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "original_question": _clean_for_ai(original_question),
                        "original_answer": _clean_for_ai(original_answer),
                        "followup_question": _clean_for_ai(followup_question),
                        "followup_answer": _clean_for_ai(followup_answer),
                    }),
                },
            ],
            extra_body={"reasoning_effort": "minimal"},
        )

        result = json.loads(response.choices[0].message.content)
        followups = _coerce_followups(result.get("followups"), limit=1)
        is_vague = bool(result.get("is_vague", False))
        declined = bool(result.get("declined", False))
        # If the participant declined (e.g. "nothing"/"not sure"), never escalate.
        if declined:
            followups = []
        return {
            "is_vague": is_vague,
            "is_irrelevant": bool(result.get("is_irrelevant", False)),
            "reason": result.get("reason", ""),
            "missing_info_types": result.get("missing_info_types", []),
            "followups": followups,
            "declined": declined,
            "vagueness_score": _coerce_score(result.get("vagueness_score"), is_vague),
        }
    except Exception as e:
        logger.warning(f"Follow-up clarification check failed: {e}")
        return {
            "is_vague": False,
            "is_irrelevant": False,
            "reason": "Analysis unavailable",
            "missing_info_types": [],
            "followups": [],
            "declined": False,
            "vagueness_score": None,
            "error": True,
        }


async def detect_vagueness_with_followups(question_text: str, answer_text: str) -> dict:
    """Single LLM call: classify vagueness AND generate follow-ups together.
    Cuts latency from ~3s (two sequential calls) to ~1.5s (one call)."""
    if not _has_api_key():
        return {
            "is_vague": False,
            "is_irrelevant": False,
            "reason": "AI analysis unavailable",
            "missing_info_types": [],
            "followups": [],
            "vagueness_score": None,
        }

    try:
        client = _get_client()
        system_prompt = _load_prompt("vagueness_with_followups")

        response = await client.chat.completions.create(
            model=get_settings().openai_model_followups,  # mini for quality follow-ups
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": _clean_for_ai(question_text),
                        "answer": _clean_for_ai(answer_text),
                    }),
                },
            ],
            extra_body={"reasoning_effort": "minimal"},
        )

        result = json.loads(response.choices[0].message.content)
        followups = _coerce_followups(result.get("followups"), limit=1)
        is_vague = bool(result.get("is_vague", False))
        declined = bool(result.get("declined", False))
        # Participant said "nothing" / "not sure": accept as-is, no follow-up.
        if declined:
            followups = []
        return {
            "is_vague": is_vague,
            "is_irrelevant": bool(result.get("is_irrelevant", False)),
            "reason": result.get("reason", ""),
            "missing_info_types": result.get("missing_info_types", []),
            "followups": followups,
            "declined": declined,
            "vagueness_score": _coerce_score(result.get("vagueness_score"), is_vague),
        }
    except Exception as e:
        logger.warning(f"Combined vagueness+followup detection failed: {e}")
        return {
            "is_vague": False,
            "is_irrelevant": False,
            "reason": "Analysis unavailable",
            "missing_info_types": [],
            "followups": [],
            "declined": False,
            "vagueness_score": None,
            "error": True,
        }


async def cleanup_transcript(raw_text: str) -> dict:
    if not _has_api_key():
        return {"cleaned": raw_text, "changed": False}

    try:
        client = _get_client()
        system_prompt = _load_prompt("cleanup")
        safe_raw = _clean_for_ai(raw_text)

        response = await client.chat.completions.create(
            model=get_settings().openai_model_cleanup,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": safe_raw},
            ],
            # Cleanup is a mechanical rewrite (punctuation, fillers) — no
            # reasoning budget needed. Drops latency from ~3-5s to <1s.
            extra_body={"reasoning_effort": "minimal"},
        )

        result = json.loads(response.choices[0].message.content)
        cleaned = result.get("cleaned", safe_raw)
        # Belt-and-suspenders: re-run PII strip on the model's output in case
        # it echoed anything sensitive back (it should not, but we never trust).
        cleaned = _clean_for_ai(cleaned)
        return {
            "cleaned": cleaned,
            "changed": bool(result.get("changed", False)) or (cleaned != (raw_text or "")),
        }
    except Exception as e:
        logger.warning(f"Transcript cleanup failed: {e}")
        # On failure, still return a PII-safe version of the input.
        return {"cleaned": _clean_for_ai(raw_text), "changed": False}


def _empty_extraction_result() -> dict:
    return {
        "what_was_tried": None,
        "planned_task_or_workflow": None,
        "outcome_or_expected_outcome": None,
        "barriers": [],
        "enablers": [],
        "public_benefit": None,
        "top_themes": [],
        "success_story_candidate": None,
    }


async def extract_structured(answers: list[dict]) -> dict:
    """Run structured extraction. Returns a dict of extracted fields plus a
    ``_meta`` block with model_name, prompt_version, run_at, success_flag, and
    error_message so callers can stamp the Extraction row for the dashboard.
    """
    settings = get_settings()
    model_name = settings.openai_model_extraction
    meta = {
        "model_name": model_name,
        "model_version": None,
        "prompt_version": prompt_version("extraction"),
        "run_at": datetime.now(timezone.utc),
        "success_flag": False,
        "error_message": None,
    }

    if not _has_api_key():
        result = _empty_extraction_result()
        meta["error_message"] = "AI analysis unavailable"
        result["_meta"] = meta
        return result

    try:
        client = _get_client()
        system_prompt = _load_prompt("extraction")

        # PII-strip every string field in the answers payload before it
        # reaches OpenAI.
        safe_answers: list[dict] = []
        for a in answers:
            safe_answers.append({
                k: (_clean_for_ai(v) if isinstance(v, str) else v)
                for k, v in a.items()
            })

        response = await client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "answers": safe_answers,
                    }),
                },
            ],
            # Extraction is a direct JSON-fill task, not a multi-step reasoning
            # task — same as our vagueness/followup/cleanup calls. Skipping the
            # default "medium" reasoning phase cuts latency from ~15-25s to
            # ~4-7s with no measurable quality drop on the 8-field summary.
            extra_body={"reasoning_effort": "minimal"},
        )

        result_dict = json.loads(response.choices[0].message.content)
        meta["model_version"] = getattr(response, "model", None) or model_name
        meta["success_flag"] = True
        meta["run_at"] = datetime.now(timezone.utc)
        out = {
            "what_was_tried": result_dict.get("what_was_tried"),
            "planned_task_or_workflow": result_dict.get("planned_task_or_workflow"),
            "outcome_or_expected_outcome": result_dict.get("outcome_or_expected_outcome"),
            "barriers": result_dict.get("barriers", []),
            "enablers": result_dict.get("enablers", []),
            "public_benefit": result_dict.get("public_benefit"),
            "top_themes": result_dict.get("top_themes", []),
            "success_story_candidate": result_dict.get("success_story_candidate"),
        }
        out["_meta"] = meta
        return out
    except Exception as e:
        logger.warning(f"Structured extraction failed: {e}")
        meta["error_message"] = str(e)[:500]
        meta["run_at"] = datetime.now(timezone.utc)
        result = _empty_extraction_result()
        result["_meta"] = meta
        return result


def _clip_text(text: str, limit: int = 900) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _heuristic_sentiment(text: str) -> str:
    lowered = (text or "").lower()
    positive = [
        "helpful", "useful", "great", "good", "excellent", "love", "valuable",
        "clear", "confident", "improved", "better", "saved", "easy", "effective",
    ]
    negative = [
        "confusing", "hard", "difficult", "unclear", "bad", "poor", "issue",
        "problem", "frustrating", "not useful", "didn't", "couldn't", "barrier",
    ]
    pos = sum(1 for word in positive if word in lowered)
    neg = sum(1 for word in negative if word in lowered)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _quality_score(text: str) -> int:
    words = [w for w in (text or "").split() if w.strip()]
    length_score = min(len(words) / 35, 1.0)
    specificity_markers = sum(
        1
        for marker in ["because", "when", "after", "used", "tried", "example", "workflow", "team", "resident", "process"]
        if marker in (text or "").lower()
    )
    detail_score = min(specificity_markers / 3, 1.0)
    return max(1, min(5, round(1 + (length_score * 2.2) + (detail_score * 1.8))))


def _fallback_ai_insights(open_responses: list[dict]) -> dict:
    answer_insights = []
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0, "mixed": 0}
    quality_scores = []
    keyword_counts: dict[str, int] = {}
    stop_words = {
        "about", "after", "also", "because", "been", "could", "from", "have",
        "into", "more", "that", "their", "there", "this", "with", "would",
        "your", "were", "what", "when", "where", "which", "will", "using",
        "the", "and", "for", "was", "are", "but", "not", "our", "they",
    }

    for item in open_responses:
        text = item.get("answer_text", "")
        sentiment = _heuristic_sentiment(text)
        quality = _quality_score(text)
        sentiment_counts[sentiment] += 1
        quality_scores.append(quality)
        answer_insights.append({
            "submission_id": item.get("submission_id"),
            "question_id": item.get("question_id"),
            "question_text": item.get("question_text", ""),
            "answer_text": _clip_text(text, 320),
            "sentiment": sentiment,
            "quality_score": quality,
            "quality_reason": "Estimated from answer length and specificity.",
        })
        for raw in text.lower().replace(".", " ").replace(",", " ").split():
            word = raw.strip("!?;:()[]{}\"'")
            if len(word) >= 5 and word not in stop_words:
                keyword_counts[word] = keyword_counts.get(word, 0) + 1

    topics = [
        {
            "label": word.title(),
            "count": count,
            "summary": f"Responses frequently mention {word}.",
        }
        for word, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:6]
    ]

    return {
        "ai_available": False,
        "total_open_responses": len(open_responses),
        "sentiment_distribution": sentiment_counts,
        "average_quality_score": round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else None,
        "topics": topics,
        "answer_insights": answer_insights[:40],
        "summary": "AI is not configured, so these insights use lightweight local heuristics.",
        "recommendations": [
            "Configure an OpenAI API key for deeper sentiment, clustering, and recommendations.",
            "Review low-detail answers and consider adding more targeted follow-up prompts.",
        ],
    }


async def analyze_open_responses(open_responses: list[dict]) -> dict:
    if not open_responses:
        return {
            "ai_available": _has_api_key(),
            "total_open_responses": 0,
            "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0, "mixed": 0},
            "average_quality_score": None,
            "topics": [],
            "answer_insights": [],
            "summary": "No open-ended responses are available for this filter.",
            "recommendations": [],
        }

    if not _has_api_key():
        return _fallback_ai_insights(open_responses)

    try:
        client = _get_client()
        payload = [
            {
                "submission_id": r.get("submission_id"),
                "question_id": r.get("question_id"),
                "question_text": _clean_for_ai(_clip_text(r.get("question_text", ""), 220)),
                "answer_text": _clean_for_ai(_clip_text(r.get("answer_text", ""), 900)),
            }
            for r in open_responses[:80]
        ]
        response = await client.chat.completions.create(
            model=get_settings().openai_model_extraction,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You analyze open-ended survey responses for public-sector training feedback. "
                        "Return JSON with: sentiment_distribution {positive,neutral,negative,mixed}; "
                        "average_quality_score from 1-5; topics array of {label,count,summary}; "
                        "answer_insights array preserving submission_id and question_id with sentiment, "
                        "quality_score 1-5, quality_reason, and a short answer_text excerpt; "
                        "summary; recommendations array. Be conservative and evidence-based."
                    ),
                },
                {"role": "user", "content": json.dumps({"responses": payload})},
            ],
        )
        result = json.loads(response.choices[0].message.content)
        return {
            "ai_available": True,
            "total_open_responses": len(open_responses),
            "sentiment_distribution": result.get("sentiment_distribution", {}),
            "average_quality_score": result.get("average_quality_score"),
            "topics": result.get("topics", []),
            "answer_insights": result.get("answer_insights", [])[:80],
            "summary": result.get("summary", ""),
            "recommendations": result.get("recommendations", []),
        }
    except Exception as e:
        logger.warning(f"AI open-response analysis failed: {e}")
        return _fallback_ai_insights(open_responses)


def _fallback_generated_survey() -> dict:
    return {
        "version": "1.0",
        "title": "Generated Feedback Survey",
        "question_groups": [
            {"id": "intro", "label": "Overall Experience", "randomize": False},
            {"id": "open", "label": "Detailed Feedback", "randomize": False},
        ],
        "questions": [
            {
                "id": "q1_recommend",
                "type": "nps",
                "text": "How likely are you to recommend this experience to a colleague?",
                "required": True,
                "voice_eligible": False,
                "group": "intro",
                "labels": {"low": "Not at all likely", "high": "Extremely likely"},
            },
            {
                "id": "q2_value",
                "type": "mcq",
                "text": "How valuable was this experience for your work?",
                "options": ["Not valuable", "Somewhat valuable", "Very valuable", "Extremely valuable"],
                "required": True,
                "voice_eligible": False,
                "group": "intro",
            },
            {
                "id": "q3_tried",
                "type": "open",
                "text": "What did you try, apply, or plan to apply after this experience?",
                "required": True,
                "voice_eligible": True,
                "group": "open",
            },
        ],
    }


async def generate_survey_from_goal(goal_description: str, program_type: str | None = None, question_count: int = 8) -> dict:
    question_count = max(3, min(question_count or 8, 14))
    if not _has_api_key():
        return _fallback_generated_survey()

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=get_settings().openai_model_followups,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a survey_config JSON object for this feedback tool. "
                        "Use only these question types: rating, mcq, multi, open, nps, slider, "
                        "matrix, ranking, yesno, dropdown, short_text, date. "
                        "Every question needs id, type, text, required, voice_eligible, and optional group. "
                        "Open-ended questions should be voice_eligible when useful. "
                        "Use question_groups. Avoid file upload. Return only JSON with version, title, "
                        "question_groups, questions."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "goal_description": goal_description,
                        "program_type": program_type,
                        "question_count": question_count,
                    }),
                },
            ],
        )
        result = json.loads(response.choices[0].message.content)
        questions = result.get("questions", [])
        for idx, q in enumerate(questions, start=1):
            q.setdefault("id", f"q{idx}")
            q.setdefault("type", "open")
            q.setdefault("text", "Feedback question")
            q.setdefault("required", True)
            q.setdefault("voice_eligible", q.get("type") == "open")
        return {
            "version": result.get("version", "1.0"),
            "title": result.get("title") or "Generated Feedback Survey",
            "question_groups": result.get("question_groups", []),
            "questions": questions[:question_count],
        }
    except Exception as e:
        logger.warning(f"AI survey generation failed: {e}")
        return _fallback_generated_survey()


async def compare_survey_responses(primary: dict, comparison: dict) -> dict:
    if not _has_api_key():
        return {
            "ai_available": False,
            "summary": "AI is not configured. Comparison is based on simple response counts.",
            "wins": [],
            "risks": [],
            "recommendations": [
                f"{primary.get('name')} has {primary.get('completed_count', 0)} completed responses.",
                f"{comparison.get('name')} has {comparison.get('completed_count', 0)} completed responses.",
            ],
        }

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=get_settings().openai_model_extraction,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Compare two survey result snapshots. Return JSON with summary, wins array, "
                        "risks array, recommendations array. Keep it concrete and avoid overstating "
                        "claims when response counts are low."
                    ),
                },
                {"role": "user", "content": json.dumps({"primary": primary, "comparison": comparison})},
            ],
        )
        result = json.loads(response.choices[0].message.content)
        return {
            "ai_available": True,
            "summary": result.get("summary", ""),
            "wins": result.get("wins", []),
            "risks": result.get("risks", []),
            "recommendations": result.get("recommendations", []),
        }
    except Exception as e:
        logger.warning(f"AI survey comparison failed: {e}")
        return {
            "ai_available": False,
            "summary": "AI comparison failed. Try again later.",
            "wins": [],
            "risks": [],
            "recommendations": [],
        }
