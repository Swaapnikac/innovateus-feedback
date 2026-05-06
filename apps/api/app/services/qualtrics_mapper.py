"""Pure mapping layer between Public Voice tool data and the Qualtrics
Response Import API / Qualtrics CSV shape.

Why this lives in its own module: the API sync (qualtrics_service) and the
admin CSV export must produce identical column values. Putting both behind
the same set of functions makes drift impossible — any change to the
combined-answer logic, recode, or per-question input-mode indicator lands
on both surfaces at once.

No I/O. No SQLAlchemy session. Inputs are already-loaded ORM objects (or
plain dicts in the legacy sync path) plus the survey config.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from app.config import Settings, get_settings
from app.models import Answer, Cohort


PAYLOAD_VERSION = "v2.2026-05"
SOURCE_INTERFACE = "Public Voice tool"

# Recode fallback for the legacy test survey (QID1…QID9). Used when a
# question's survey_config has no per-target ``qualtrics`` block — keeps
# the existing test sync working while production migrates to the
# config-driven mapping.
_LEGACY_TEST_QID_MAP: dict[str, str] = {
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

_LEGACY_TEST_RECODES: dict[str, dict[str, int]] = {
    "q2_confidence": {
        "Very confident": 1, "Somewhat confident": 2, "A little confident": 3,
        "Not confident": 4, "I am not using generative AI yet": 5,
    },
    "q3_clarity": {"Yes": 1, "Somewhat": 2, "No": 3, "Still unsure": 4},
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
    "q5_impact": {"Easier": 1, "Harder": 2, "Neither": 3, "Do not know": 4},
    "q8_exercises": {
        "No, I did not have enough time to attempt the exercises": 1,
        "No, I decided not to do the exercises": 2,
        "No, I was not able to access the appropriate websites or tools": 3,
        "Yes, I attempted but did not complete any exercises": 4,
        "Yes, I completed some of the exercises": 5,
        "Yes, I completed all of the exercises": 6,
    },
}

_LEGACY_TEST_TEXT_QUESTIONS = {"q6_most_impactful", "q7_prepared_task", "q9_feedback"}


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class QualtricsConfigError(ValueError):
    """Cohort target resolves to ``none`` or required env vars are blank."""


class MissingQualtricsMappingError(ValueError):
    """A question has no QID for the active target, or a choice has no recode."""


# ─────────────────────────────────────────────────────────────────────────────
# Target resolution
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedTarget:
    name: str  # "production" | "test"
    survey_id: str
    datacenter_id: str


def resolve_target(
    cohort: Optional[Cohort],
    settings: Optional[Settings] = None,
    override: Optional[str] = None,
) -> ResolvedTarget:
    """Pick the target Qualtrics survey for a cohort.

    Precedence: ``override`` arg > ``cohort.qualtrics_target`` > settings
    default. Returns the survey_id and datacenter for the chosen target.
    Raises ``QualtricsConfigError`` if the target is "none", unrecognised,
    or the corresponding env vars are blank.
    """
    s = settings or get_settings()
    name = (override or (cohort.qualtrics_target if cohort else None) or s.qualtrics_default_target or "").strip().lower()
    if name == "none" or not name:
        raise QualtricsConfigError(f"Qualtrics target is disabled (target={name!r})")

    if name == "production":
        survey_id = s.qualtrics_production_survey_id
        datacenter = s.qualtrics_production_datacenter_id
    elif name == "test":
        survey_id = s.qualtrics_test_survey_id or s.qualtrics_survey_id
        datacenter = s.qualtrics_test_datacenter_id or s.qualtrics_datacenter_id
    else:
        raise QualtricsConfigError(f"Unknown Qualtrics target {name!r}")

    if not survey_id or not datacenter:
        raise QualtricsConfigError(
            f"Qualtrics {name} target is not fully configured "
            f"(survey_id={'set' if survey_id else 'missing'}, "
            f"datacenter_id={'set' if datacenter else 'missing'})"
        )
    return ResolvedTarget(name=name, survey_id=survey_id, datacenter_id=datacenter)


def is_token_configured(settings: Optional[Settings] = None) -> bool:
    s = settings or get_settings()
    return bool(s.qualtrics_api_token)


# ─────────────────────────────────────────────────────────────────────────────
# Per-question lookups
# ─────────────────────────────────────────────────────────────────────────────


# Cohorts cache the survey_config they were created with as JSONB. Cohorts
# created before the per-question ``qualtrics`` block existed have a stale
# snapshot that lacks the QID mapping — without this fallback, validate /
# sync / CSV export against those cohorts errors out with "no QID configured"
# even though the canonical survey-en.json has the mapping.
_DEFAULT_SURVEY_PATH = Path(__file__).resolve().parents[4] / "docs" / "survey-config" / "survey-en.json"
_default_questions_cache: Optional[dict[str, dict]] = None


def _default_questions_by_id() -> dict[str, dict]:
    global _default_questions_cache
    if _default_questions_cache is None:
        try:
            with open(_DEFAULT_SURVEY_PATH, "r", encoding="utf-8") as f:
                qs = (json.load(f) or {}).get("questions") or []
            _default_questions_cache = {q.get("id"): q for q in qs if q.get("id")}
        except (FileNotFoundError, json.JSONDecodeError):
            _default_questions_cache = {}
    return _default_questions_cache


def _qualtrics_block(question: dict, target: str) -> Optional[dict]:
    block = (question.get("qualtrics") or {}).get(target)
    if isinstance(block, dict):
        return block
    # Fallback: cohort.survey_config snapshot is older than the qualtrics
    # mapping. Resolve the same question id against the canonical default.
    q_id = question.get("id")
    if q_id:
        default_q = _default_questions_by_id().get(q_id)
        if default_q:
            default_block = (default_q.get("qualtrics") or {}).get(target)
            if isinstance(default_block, dict):
                return default_block
    return None


def question_qid(question: dict, target: str) -> Optional[str]:
    """Return the Qualtrics QID for a question under the given target.

    Falls back to the legacy hardcoded ``QID1…QID9`` map for the test
    target so existing test cohorts keep syncing during migration.
    """
    block = _qualtrics_block(question, target)
    if block and block.get("qid"):
        return block["qid"]
    if target == "test":
        return _LEGACY_TEST_QID_MAP.get(question.get("id"))
    return None


def question_export_tag(question: dict, target: str) -> str:
    """CSV column name (Qualtrics calls this ``DataExportTag``)."""
    block = _qualtrics_block(question, target)
    if block and block.get("data_export_tag"):
        return block["data_export_tag"]
    qid = question_qid(question, target) or ""
    # Fallback: a legacy test row will have QID3 → Q3 (numeric suffix).
    if qid.startswith("QID"):
        return "Q" + qid[3:]
    return question.get("id", "")


def question_recodes(question: dict, target: str) -> dict[str, int]:
    block = _qualtrics_block(question, target)
    if block and isinstance(block.get("recodes"), dict):
        return {str(k): int(v) for k, v in block["recodes"].items()}
    if target == "test":
        return _LEGACY_TEST_RECODES.get(question.get("id"), {})
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Combined open answer (main + follow-ups) — single source of truth
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_sentence_end(s: str) -> str:
    s = s.rstrip()
    if s and s[-1] not in ".!?":
        s += "."
    return s


def combine_open_answer(answer: Optional[Answer]) -> str:
    """Concatenate main answer + follow-up answers into one block.

    Follow-up *questions* are deliberately dropped — only the participant's
    own words travel to Qualtrics. Empty / declined / skipped follow-ups are
    omitted. Sentence boundaries are normalised so the result reads as one
    paragraph.
    """
    if answer is None:
        return ""
    parts: list[str] = []
    main = (answer.answer_raw or "").strip()
    if main:
        parts.append(_ensure_sentence_end(main))
    for txt, skipped in (
        ((answer.followup_1_answer or "").strip(), bool(answer.followup_1_skipped_flag)),
        ((answer.followup_2_answer or "").strip(), bool(answer.followup_2_skipped_flag)),
    ):
        if skipped or not txt:
            continue
        parts.append(_ensure_sentence_end(txt))
    return " ".join(parts).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Per-question voice / text / mixed / blank indicator
# ─────────────────────────────────────────────────────────────────────────────


_VALID_MODES = {"voice", "text"}


def is_open_question(question: dict) -> bool:
    """True for question types where input mode (voice / text) varies.

    The voice/text indicator is meaningless for rating / mcq / multi
    questions — they have no microphone path — so we don't emit a column
    for them. Only ``open`` and ``voice`` types qualify.
    """
    return (question.get("type") or "").lower() in {"open", "voice"}


def compute_question_input_mode(answer: Optional[Answer], question: dict) -> str:
    """Return ``voice`` | ``text`` | ``mixed`` | ``blank``.

    Closed questions and unanswered questions are ``blank`` — the indicator
    is meaningful only for question types where input mode varies.
    """
    if answer is None:
        return "blank"
    q_type = (question.get("type") or "").lower()
    is_open = q_type in {"open", "voice"}
    if not is_open:
        # Closed questions don't emit an input_mode column at all (callers
        # gate on ``is_open_question``); this branch only fires if a
        # caller asks anyway, in which case ``blank`` is the safest answer.
        return "blank"
    if not (answer.answer_raw or "").strip():
        return "blank"

    modes: set[str] = set()
    main_mode = (answer.input_mode or "").lower()
    if main_mode in _VALID_MODES:
        modes.add(main_mode)

    for fu_mode, fu_text, skipped in (
        (answer.followup_1_input_mode, answer.followup_1_answer, answer.followup_1_skipped_flag),
        (answer.followup_2_input_mode, answer.followup_2_answer, answer.followup_2_skipped_flag),
    ):
        if skipped or not (fu_text or "").strip():
            continue
        m = (fu_mode or "").lower()
        if m in _VALID_MODES:
            modes.add(m)

    if not modes:
        return "blank"
    if len(modes) == 1:
        return next(iter(modes))
    return "mixed"


# ─────────────────────────────────────────────────────────────────────────────
# Per-answer Qualtrics value formatting
# ─────────────────────────────────────────────────────────────────────────────


def format_answer_value(
    answer: Optional[Answer],
    question: dict,
    target: str,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Build the ``{QID: value}`` dict for a single question.

    Multi-select returns ``{QID: ["1", "4"]}`` — Qualtrics' MAVR question
    type stores multi-answer responses as an array of choice-ID strings
    under the bare QID, NOT as per-choice ``QID_<n>`` flags.
    Open-ended returns the combined main + follow-up text under
    ``{QID}_TEXT`` — text-entry questions land in the ``_TEXT`` sub-field,
    not the bare QID.
    Closed questions return the recoded integer.

    With ``strict=False`` missing recodes / QIDs degrade gracefully (used by
    the CSV export so a partial mapping doesn't blow up the whole download).
    """
    if answer is None:
        return {}
    q_id = question.get("id") or ""
    q_type = (question.get("type") or "").lower()
    qid = question_qid(question, target)
    if not qid:
        if strict:
            raise MissingQualtricsMappingError(
                f"No Qualtrics QID configured for question {q_id!r} under target {target!r}"
            )
        return {}

    if q_type == "rating":
        raw = (answer.answer_raw or "").strip()
        if not raw:
            return {}
        try:
            return {qid: int(raw)}
        except (ValueError, TypeError):
            return {qid: raw}

    if q_type in {"open", "voice"}:
        text = combine_open_answer(answer)
        if not text:
            return {}
        return {f"{qid}_TEXT": text}

    if q_type == "multi":
        raw = answer.answer_raw or ""
        try:
            items = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            items = []
        if not isinstance(items, list):
            return {}
        recodes = question_recodes(question, target)
        choice_ids: list[str] = []
        for opt in items:
            opt_str = str(opt)
            choice_id = recodes.get(opt_str)
            if choice_id is None:
                if strict:
                    raise MissingQualtricsMappingError(
                        f"No recode for choice {opt_str!r} on question {q_id!r} under target {target!r}"
                    )
                continue
            choice_ids.append(str(choice_id))
        if not choice_ids:
            return {}
        return {qid: choice_ids}

    # mcq / yesno / generic single-answer
    raw = (answer.answer_raw or "").strip()
    if not raw:
        return {}
    recodes = question_recodes(question, target)
    if recodes:
        recode = recodes.get(raw)
        if recode is None:
            if strict:
                raise MissingQualtricsMappingError(
                    f"No recode for answer {raw!r} on question {q_id!r} under target {target!r}"
                )
            return {qid: raw}
        return {qid: recode}
    # No recode table — pass through. Legacy test path also lands here for
    # text-entry sub-fields, which we keep for back-compat.
    if target == "test" and q_id in _LEGACY_TEST_TEXT_QUESTIONS:
        return {f"{qid}_TEXT": raw}
    return {qid: raw}


# ─────────────────────────────────────────────────────────────────────────────
# Submission-level metadata (shared between API payload and CSV row)
# ─────────────────────────────────────────────────────────────────────────────


def _iso(ts) -> str:
    if ts is None:
        return ""
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def _submission_metadata(
    submission,
    cohort: Optional[Cohort],
    target: ResolvedTarget,
) -> dict[str, Any]:
    """Metadata fields shared by API payload and CSV row.

    Keys here are the *logical* names. The CSV mapper renames them to
    Qualtrics-canonical column names (StartDate, EndDate, etc.) at the
    column-build stage; the API payload uses these names as embedded data.
    """
    sub = submission
    return {
        "responseId": str(sub.id),
        "submissionId": str(sub.id),
        "sessionToken": str(sub.id),  # privacy-safe — not the IP hash
        "surveyId": target.survey_id,
        "surveyName": (cohort.course_name if cohort else "") or "",
        "programName": (cohort.course_name if cohort else "") or "",
        "programType": (cohort.program_type if cohort else "") or "",
        "surveyVersion": sub.survey_version or "",
        "submittedAt": _iso(sub.completed_at),
        "startedAt": _iso(sub.created_at),
        "durationSec": str(sub.time_to_complete_sec) if sub.time_to_complete_sec is not None else "",
        "sourceInterface": SOURCE_INTERFACE,
        "qualtricsPayloadVersion": PAYLOAD_VERSION,
        "qualtricsTarget": target.name,
        "course_part": (cohort.course_name if cohort else "") or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# API payload (Response Import)
# ─────────────────────────────────────────────────────────────────────────────


def build_qualtrics_payload(
    submission,
    answers: Iterable[Answer],
    cohort: Optional[Cohort],
    questions: list[dict],
    target: ResolvedTarget,
) -> dict[str, Any]:
    """Build the ``{"values": {...}}`` body for the Qualtrics Response Import API.

    Includes:
      * One key per question (combined for open-ended) keyed by QID.
      * ``{q_id}_input_mode`` per question — voice/text/mixed/blank.
      * Submission metadata (sourceInterface, target, version, etc.).
      * Standard ``finished``/``status`` flags Qualtrics expects.
    """
    answers_by_qid: dict[str, Answer] = {a.question_id: a for a in answers}
    values: dict[str, Any] = {"finished": 1, "status": 0}

    for q in questions:
        q_id = q.get("id") or ""
        a = answers_by_qid.get(q_id)
        # Skip questions without a configured QID under this target rather
        # than fail the whole payload — the validation endpoint surfaces
        # which mappings are missing.
        if not question_qid(q, target.name):
            continue
        try:
            values.update(format_answer_value(a, q, target.name, strict=True))
        except MissingQualtricsMappingError:
            # Strict mode raises in production sync — caller catches and
            # records the message. We still emit the indicator below
            # (only for open-ended types — closed questions have no mode).
            raise
        if is_open_question(q):
            values[f"{q_id}_input_mode"] = compute_question_input_mode(a, q)

    values.update(_submission_metadata(submission, cohort, target))
    return {"values": values}


# ─────────────────────────────────────────────────────────────────────────────
# CSV mapping (3-row Qualtrics-importable header + 1 row per submission)
# ─────────────────────────────────────────────────────────────────────────────

# Standard Qualtrics CSV columns that appear before the question block.
# These mirror what Qualtrics emits when you export responses from the
# UI — keeping them stable lets the file round-trip back via Response
# Import without manual column remapping.
_STANDARD_COLUMNS: list[tuple[str, str, str]] = [
    # (column_name, human_label, ImportId)
    ("StartDate", "Start Date", "startDate"),
    ("EndDate", "End Date", "endDate"),
    ("Status", "Response Type", "status"),
    ("Progress", "Progress", "progress"),
    ("Duration (in seconds)", "Duration (in seconds)", "duration"),
    ("Finished", "Finished", "finished"),
    ("RecordedDate", "Recorded Date", "recordedDate"),
    ("ResponseId", "Response ID", "_recordId"),
    ("DistributionChannel", "Distribution Channel", "distributionChannel"),
    ("UserLanguage", "User Language", "userLanguage"),
]

# Extra Public-Voice-tool columns appended after the question block so
# they survive a Qualtrics round-trip as embedded data. Internal-only
# fields (qualtrics_target, payload_version, session_token) stay in the
# API sync payload but are deliberately left off the CSV — the CSV is
# the human-facing artifact and shouldn't be cluttered with bookkeeping.
_TRAILING_COLUMNS: list[tuple[str, str, str]] = [
    ("source_interface", "Source Interface", "sourceInterface"),
    ("survey_version", "Survey Version", "surveyVersion"),
    ("program_type", "Program Type", "programType"),
    ("program_name", "Program Name", "programName"),
    ("survey_id", "Survey ID", "surveyId"),
    ("survey_name", "Survey Name", "surveyName"),
    # submission_id is omitted — ResponseId in the standard Qualtrics
    # block already carries the same value (str(submission.id)).
]


def build_qualtrics_csv_headers(
    questions: list[dict],
    target: ResolvedTarget,
) -> list[list[str]]:
    """Return the three Qualtrics CSV header rows.

    Row 1: column names (StartDate, …, Q5, Q23, …, q1_recommend_input_mode, …).
    Row 2: human labels (Start Date, …, full question text, …).
    Row 3: ImportId JSON ({"ImportId":"startDate"}, …, {"ImportId":"QID5"}, …).
    """
    row1: list[str] = []
    row2: list[str] = []
    row3: list[str] = []

    for col, label, import_id in _STANDARD_COLUMNS:
        row1.append(col)
        row2.append(label)
        row3.append(json.dumps({"ImportId": import_id}))

    # One block per question. The answer column always appears; the
    # voice/text indicator only appears for open-ended questions (it's
    # meaningless for rating / mcq / multi). Each label gets a [OPEN] or
    # [CLOSE] marker so analysts opening the CSV can tell at a glance
    # which questions are free-text vs. constrained.
    for q in questions:
        q_id = q.get("id") or ""
        q_text = q.get("text") or q_id
        q_type = (q.get("type") or "").lower()
        is_open = is_open_question(q)
        type_marker = "[OPEN]" if is_open else "[CLOSE]"
        tag = question_export_tag(q, target.name) or q_id
        qid = question_qid(q, target.name) or q_id

        row1.append(tag)
        row2.append(f"{q_text} {type_marker}")
        row3.append(json.dumps({"ImportId": qid}))

        if is_open:
            mode_col = f"{q_id}_input_mode"
            row1.append(mode_col)
            row2.append(f"{q_text} — input mode {type_marker}")
            row3.append(json.dumps({"ImportId": mode_col}))

    for col, label, import_id in _TRAILING_COLUMNS:
        row1.append(col)
        row2.append(label)
        row3.append(json.dumps({"ImportId": import_id}))

    return [row1, row2, row3]


def _multi_text(answer: Optional[Answer]) -> str:
    if answer is None or not (answer.answer_raw or "").strip():
        return ""
    try:
        items = json.loads(answer.answer_raw)
    except (json.JSONDecodeError, TypeError):
        return answer.answer_raw or ""
    if isinstance(items, list):
        return " | ".join(str(i) for i in items)
    return str(items)


def _format_multi_value_for_csv(answer: Optional[Answer], question: dict, target: str) -> str:
    """Pipe-joined choice text for multi-select main column.

    The CSV is the analyst-facing artifact, so it carries human-readable
    labels like ``"Create content | Summarize text"`` instead of the
    coded form Qualtrics uses internally (``1,5``). The API sync payload
    still uses the per-choice flag form because Qualtrics' Response
    Import API requires it — the two paths intentionally differ.
    """
    return _multi_text(answer)


def build_qualtrics_csv_row(
    submission,
    answers: Iterable[Answer],
    cohort: Optional[Cohort],
    questions: list[dict],
    target: ResolvedTarget,
) -> list[str]:
    """One CSV row per submission, columns in the same order as the headers."""
    sub = submission
    answers_by_qid: dict[str, Answer] = {a.question_id: a for a in answers}
    meta = _submission_metadata(sub, cohort, target)

    standard_values = {
        "startDate": _iso(sub.created_at),
        "endDate": _iso(sub.completed_at),
        # Match Qualtrics' native CSV — "Status" is the human-readable
        # response-type label, not a numeric code.
        "status": "IP Address",
        "progress": "100" if sub.status == "completed" else "0",
        "duration": str(sub.time_to_complete_sec or 0),
        # Qualtrics' Finished column emits TRUE / FALSE in its own exports;
        # match that exactly so Response Import doesn't need a mapping rule.
        "finished": "TRUE" if sub.status == "completed" else "FALSE",
        "recordedDate": _iso(sub.completed_at or sub.created_at),
        "_recordId": str(sub.id),
        "distributionChannel": "anonymous",
        "userLanguage": "EN",
    }

    row: list[str] = [str(standard_values.get(import_id, "")) for _, _, import_id in _STANDARD_COLUMNS]

    for q in questions:
        q_id = q.get("id") or ""
        q_type = (q.get("type") or "").lower()
        a = answers_by_qid.get(q_id)

        if q_type in {"open", "voice"}:
            row.append(combine_open_answer(a))
        elif q_type == "multi":
            row.append(_format_multi_value_for_csv(a, q, target.name))
        else:
            # Closed single-choice (mcq / rating / yesno / …) — emit the
            # raw choice text the participant selected. For rating that's
            # already the integer; for mcq it's the choice label
            # ("Very confident", "Yes", etc.) — far more useful for an
            # analyst than the numeric recode (1 / 4 / 5).
            row.append((a.answer_raw if (a and a.answer_raw) else ""))

        # Input-mode column is open-only — must mirror header gating.
        if is_open_question(q):
            row.append(compute_question_input_mode(a, q))

    for _, _, import_id in _TRAILING_COLUMNS:
        row.append(str(meta.get(import_id, "")))

    return row


# ─────────────────────────────────────────────────────────────────────────────
# Validation — used by the /qualtrics/validate admin endpoint
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidationReport:
    ok: bool
    target: Optional[str]
    survey_id: Optional[str]
    datacenter_id: Optional[str]
    errors: list[str]
    warnings: list[str]


def validate_for_cohort(
    cohort: Optional[Cohort],
    questions: list[dict],
    settings: Optional[Settings] = None,
    override: Optional[str] = None,
) -> ValidationReport:
    s = settings or get_settings()
    errors: list[str] = []
    warnings: list[str] = []
    target_name: Optional[str] = None
    survey_id: Optional[str] = None
    datacenter_id: Optional[str] = None

    if not s.qualtrics_api_token:
        errors.append("QUALTRICS_API_TOKEN is not set")

    try:
        target = resolve_target(cohort, settings=s, override=override)
        target_name = target.name
        survey_id = target.survey_id
        datacenter_id = target.datacenter_id
    except QualtricsConfigError as exc:
        errors.append(str(exc))
        return ValidationReport(False, target_name, survey_id, datacenter_id, errors, warnings)

    for q in questions:
        q_id = q.get("id") or "<unknown>"
        if not question_qid(q, target.name):
            errors.append(f"Question {q_id!r} has no QID configured for target {target.name!r}")
            continue
        q_type = (q.get("type") or "").lower()
        if q_type in {"mcq", "multi"}:
            recodes = question_recodes(q, target.name)
            options = q.get("options") or []
            if not recodes:
                warnings.append(f"Question {q_id!r} has no recode table — choice values will be sent as text")
                continue
            for opt in options:
                if str(opt) not in recodes:
                    warnings.append(
                        f"Question {q_id!r} option {str(opt)!r} has no recode under target {target.name!r}"
                    )

    return ValidationReport(
        ok=not errors,
        target=target_name,
        survey_id=survey_id,
        datacenter_id=datacenter_id,
        errors=errors,
        warnings=warnings,
    )
