"""Unit tests for app.services.qualtrics_mapper.

These cover the formatting decisions that both the API sync and the
admin Qualtrics CSV download depend on:

- combined open answer (main + 0/1/2 follow-ups, declined / skipped paths)
- voice / text / mixed / blank indicator
- per-question recoded value formatting
- multi-select per-choice flags
- target resolution (cohort override > env default > error on disabled)
- validation report errors / warnings
- 3-row CSV header shape

We deliberately avoid hitting the database — the mapper is pure functions
operating on already-loaded ORM objects.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models import Answer, Cohort, Submission
from app.services import qualtrics_mapper
from app.services.qualtrics_mapper import (
    MissingQualtricsMappingError,
    QualtricsConfigError,
    ResolvedTarget,
    build_qualtrics_csv_headers,
    build_qualtrics_csv_row,
    build_qualtrics_payload,
    combine_open_answer,
    compute_question_input_mode,
    format_answer_value,
    resolve_target,
    validate_for_cohort,
)


UTC = timezone.utc


def _settings(**overrides):
    base = {
        "qualtrics_api_token": "tok",
        "qualtrics_production_survey_id": "SV_prod",
        "qualtrics_production_datacenter_id": "co1",
        "qualtrics_test_survey_id": "SV_test",
        "qualtrics_test_datacenter_id": "co1",
        "qualtrics_default_target": "production",
        "qualtrics_survey_id": "",
        "qualtrics_datacenter_id": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ─── question fixtures ─────────────────────────────────────────────────────

Q_RATING = {
    "id": "q1_recommend",
    "type": "rating",
    "qualtrics": {
        "production": {"qid": "QID5", "data_export_tag": "Q5"},
        "test": {"qid": "QID1", "data_export_tag": "Q1"},
    },
}

Q_MCQ = {
    "id": "q2_confidence",
    "type": "mcq",
    "qualtrics": {
        "production": {
            "qid": "QID23",
            "data_export_tag": "Q23",
            "recodes": {"Very confident": 1, "Not confident": 6},
        },
        "test": {
            "qid": "QID2",
            "data_export_tag": "Q2",
            "recodes": {"Very confident": 1, "Not confident": 4},
        },
    },
}

Q_MULTI = {
    "id": "q4_likely_uses",
    "type": "multi",
    "qualtrics": {
        "production": {
            "qid": "QID25",
            "data_export_tag": "Q25",
            "recodes": {"Create content": 1, "Edit content": 4, "Summarize text": 5},
        },
    },
}

Q_OPEN = {
    "id": "q6_most_impactful",
    "type": "open",
    "text": "Most impactful use?",
    "qualtrics": {
        "production": {"qid": "QID3", "data_export_tag": "Q8"},
    },
}


# ─── combine_open_answer ───────────────────────────────────────────────────


class TestCombineOpenAnswer:
    def test_main_only(self):
        a = Answer(answer_raw="I use it for emails")
        assert combine_open_answer(a) == "I use it for emails."

    def test_main_with_punctuation_preserved(self):
        a = Answer(answer_raw="I use it for emails!")
        assert combine_open_answer(a) == "I use it for emails!"

    def test_main_plus_one_followup(self):
        a = Answer(
            answer_raw="I use it to draft emails",
            followup_1_answer="Mainly for outreach to residents",
        )
        assert combine_open_answer(a) == (
            "I use it to draft emails. Mainly for outreach to residents."
        )

    def test_main_plus_two_followups(self):
        a = Answer(
            answer_raw="I use it to draft emails.",
            followup_1_answer="Mainly outreach.",
            followup_2_answer="Saves about 30 minutes a week.",
        )
        assert combine_open_answer(a) == (
            "I use it to draft emails. Mainly outreach. Saves about 30 minutes a week."
        )

    def test_skipped_followup_excluded(self):
        a = Answer(
            answer_raw="Main answer",
            followup_1_answer="should not appear",
            followup_1_skipped_flag=True,
            followup_2_answer="real second follow-up",
        )
        out = combine_open_answer(a)
        assert "should not appear" not in out
        assert "real second follow-up" in out

    def test_empty_followup_excluded(self):
        a = Answer(answer_raw="Main answer", followup_1_answer="   ")
        assert combine_open_answer(a) == "Main answer."

    def test_no_main_with_followup_returns_followup(self):
        # Edge case — main blank but follow-up present (unlikely but defensible)
        a = Answer(answer_raw="", followup_1_answer="Something")
        assert combine_open_answer(a) == "Something."

    def test_none_returns_empty(self):
        assert combine_open_answer(None) == ""


# ─── compute_question_input_mode ───────────────────────────────────────────


class TestQuestionInputMode:
    def test_closed_question_returns_blank(self):
        a = Answer(answer_raw="Very confident", input_mode="text")
        assert compute_question_input_mode(a, Q_MCQ) == "blank"

    def test_unanswered_returns_blank(self):
        assert compute_question_input_mode(None, Q_OPEN) == "blank"

    def test_empty_answer_returns_blank(self):
        a = Answer(answer_raw="   ", input_mode="voice")
        assert compute_question_input_mode(a, Q_OPEN) == "blank"

    def test_voice_only(self):
        a = Answer(
            answer_raw="My answer",
            input_mode="voice",
            followup_1_answer="follow-up 1",
            followup_1_input_mode="voice",
            followup_2_answer="follow-up 2",
            followup_2_input_mode="voice",
        )
        assert compute_question_input_mode(a, Q_OPEN) == "voice"

    def test_text_only(self):
        a = Answer(answer_raw="My answer", input_mode="text")
        assert compute_question_input_mode(a, Q_OPEN) == "text"

    def test_mixed_main_voice_followup_text(self):
        a = Answer(
            answer_raw="Spoken main answer",
            input_mode="voice",
            followup_1_answer="Typed clarification",
            followup_1_input_mode="text",
        )
        assert compute_question_input_mode(a, Q_OPEN) == "mixed"

    def test_skipped_followup_does_not_pollute_mode(self):
        a = Answer(
            answer_raw="Spoken main answer",
            input_mode="voice",
            followup_1_answer="ignored",
            followup_1_input_mode="text",
            followup_1_skipped_flag=True,
        )
        # follow-up skipped → its mode contributes nothing → "voice", not "mixed"
        assert compute_question_input_mode(a, Q_OPEN) == "voice"

    def test_unknown_input_mode_treated_as_blank(self):
        a = Answer(answer_raw="x", input_mode="garbage")
        assert compute_question_input_mode(a, Q_OPEN) == "blank"


# ─── format_answer_value ───────────────────────────────────────────────────


class TestFormatAnswerValue:
    def test_rating_returns_int(self):
        a = Answer(answer_raw="9")
        assert format_answer_value(a, Q_RATING, "production") == {"QID5": 9}

    def test_rating_non_numeric_passthrough(self):
        a = Answer(answer_raw="N/A")
        assert format_answer_value(a, Q_RATING, "production") == {"QID5": "N/A"}

    def test_mcq_recoded(self):
        a = Answer(answer_raw="Very confident")
        assert format_answer_value(a, Q_MCQ, "production") == {"QID23": 1}

    def test_mcq_unknown_choice_strict_raises(self):
        a = Answer(answer_raw="Wibble")
        with pytest.raises(MissingQualtricsMappingError):
            format_answer_value(a, Q_MCQ, "production", strict=True)

    def test_mcq_unknown_choice_lenient_passes_through(self):
        a = Answer(answer_raw="Wibble")
        assert format_answer_value(a, Q_MCQ, "production", strict=False) == {"QID23": "Wibble"}

    def test_multi_emits_per_choice_flags(self):
        a = Answer(answer_raw=json.dumps(["Create content", "Summarize text"]))
        out = format_answer_value(a, Q_MULTI, "production")
        assert out == {"QID25_1": 1, "QID25_5": 1}

    def test_multi_empty_returns_empty(self):
        a = Answer(answer_raw="")
        assert format_answer_value(a, Q_MULTI, "production") == {}

    def test_multi_unknown_choice_strict_raises(self):
        a = Answer(answer_raw=json.dumps(["Create content", "Made-up"]))
        with pytest.raises(MissingQualtricsMappingError):
            format_answer_value(a, Q_MULTI, "production", strict=True)

    def test_open_returns_combined_text(self):
        a = Answer(
            answer_raw="Drafting emails",
            followup_1_answer="Mainly outreach",
        )
        assert format_answer_value(a, Q_OPEN, "production") == {
            "QID3": "Drafting emails. Mainly outreach."
        }

    def test_open_empty_returns_empty(self):
        a = Answer(answer_raw="")
        assert format_answer_value(a, Q_OPEN, "production") == {}

    def test_missing_qid_strict_raises(self):
        q_bad = {"id": "q9_unmapped", "type": "rating", "qualtrics": {"production": {}}}
        with pytest.raises(MissingQualtricsMappingError):
            format_answer_value(Answer(answer_raw="3"), q_bad, "production", strict=True)


# ─── resolve_target ────────────────────────────────────────────────────────


class TestResolveTarget:
    def test_cohort_target_overrides_default(self):
        cohort = Cohort(qualtrics_target="test")
        s = _settings()  # default = production
        target = resolve_target(cohort, settings=s)
        assert target.name == "test"
        assert target.survey_id == "SV_test"

    def test_falls_through_to_default_when_cohort_unset(self):
        cohort = Cohort()
        target = resolve_target(cohort, settings=_settings())
        assert target.name == "production"
        assert target.survey_id == "SV_prod"
        assert target.datacenter_id == "co1"

    def test_explicit_override_wins(self):
        cohort = Cohort(qualtrics_target="production")
        target = resolve_target(cohort, settings=_settings(), override="test")
        assert target.name == "test"

    def test_target_none_disables(self):
        cohort = Cohort(qualtrics_target="none")
        with pytest.raises(QualtricsConfigError):
            resolve_target(cohort, settings=_settings())

    def test_unconfigured_target_errors(self):
        s = _settings(qualtrics_production_survey_id="")
        with pytest.raises(QualtricsConfigError):
            resolve_target(Cohort(), settings=s)

    def test_legacy_aliases_populate_test_slot(self):
        s = _settings(
            qualtrics_test_survey_id="",
            qualtrics_test_datacenter_id="",
            qualtrics_survey_id="legacy_id",
            qualtrics_datacenter_id="co1",
            qualtrics_default_target="test",
        )
        target = resolve_target(Cohort(), settings=s)
        assert target.name == "test"
        assert target.survey_id == "legacy_id"


# ─── validate_for_cohort ──────────────────────────────────────────────────


class TestValidate:
    def test_missing_token_is_error(self):
        s = _settings(qualtrics_api_token="")
        report = validate_for_cohort(Cohort(), [Q_RATING], settings=s)
        assert not report.ok
        assert any("token" in e.lower() for e in report.errors)

    def test_disabled_target_is_error(self):
        cohort = Cohort(qualtrics_target="none")
        report = validate_for_cohort(cohort, [Q_RATING], settings=_settings())
        assert not report.ok

    def test_missing_qid_for_question_is_error(self):
        q_no_qid = {"id": "qX", "type": "open", "qualtrics": {"production": {}}}
        report = validate_for_cohort(Cohort(), [Q_RATING, q_no_qid], settings=_settings())
        assert not report.ok
        assert any("qX" in e for e in report.errors)

    def test_missing_recode_is_warning_not_error(self):
        # Production has recodes for "Very confident" and "Not confident"
        # only — option present in survey but not in recodes → warning.
        q = dict(Q_MCQ)
        q["options"] = ["Very confident", "Not confident", "Somewhat confident"]
        report = validate_for_cohort(Cohort(), [q], settings=_settings())
        assert report.ok  # warnings don't break validation
        assert any("Somewhat confident" in w for w in report.warnings)

    def test_clean_config_passes(self):
        report = validate_for_cohort(Cohort(), [Q_RATING, Q_OPEN], settings=_settings())
        assert report.ok
        assert report.errors == []
        assert report.target == "production"


# ─── build_qualtrics_payload ──────────────────────────────────────────────


def _resolved_prod():
    return ResolvedTarget(name="production", survey_id="SV_prod", datacenter_id="co1")


class TestBuildPayload:
    def test_full_payload_shape(self):
        cohort = Cohort(course_name="GenAI 101", program_type="Course")
        sub = Submission(
            id=uuid.uuid4(),
            cohort_id=cohort.id,
            status="completed",
            survey_version="2026-04",
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            time_to_complete_sec=420,
        )
        answers = [
            Answer(submission_id=sub.id, question_id="q1_recommend", question_type="rating", answer_raw="9"),
            Answer(
                submission_id=sub.id,
                question_id="q6_most_impactful",
                question_type="open",
                answer_raw="Drafting emails",
                input_mode="voice",
                followup_1_answer="Mainly outreach",
                followup_1_input_mode="text",
            ),
        ]
        payload = build_qualtrics_payload(
            submission=sub,
            answers=answers,
            cohort=cohort,
            questions=[Q_RATING, Q_OPEN],
            target=_resolved_prod(),
        )
        values = payload["values"]
        # Question values
        assert values["QID5"] == 9
        assert values["QID3"] == "Drafting emails. Mainly outreach."
        # Per-question input mode indicator — only for open-ended questions
        assert "q1_recommend_input_mode" not in values  # closed → no field
        assert values["q6_most_impactful_input_mode"] == "mixed"
        # Submission metadata
        assert values["sourceInterface"] == "Public Voice tool"
        assert values["surveyId"] == "SV_prod"
        assert values["qualtricsTarget"] == "production"
        assert values["finished"] == 1

    def test_followup_questions_are_not_separate_keys(self):
        sub = Submission(id=uuid.uuid4(), cohort_id=uuid.uuid4(), status="completed")
        answers = [
            Answer(
                submission_id=sub.id,
                question_id="q6_most_impactful",
                question_type="open",
                answer_raw="A",
                followup_1="What specifically?",
                followup_1_answer="B",
                followup_2="And then?",
                followup_2_answer="C",
            ),
        ]
        payload = build_qualtrics_payload(
            submission=sub,
            answers=answers,
            cohort=None,
            questions=[Q_OPEN],
            target=_resolved_prod(),
        )
        keys = list(payload["values"].keys())
        # The combined text lives under QID3
        assert payload["values"]["QID3"] == "A. B. C."
        # And nothing leaks the follow-up *questions* or per-followup answers
        for k in keys:
            assert "_followup_1_q" not in k
            assert "_followup_2_q" not in k
            assert "_followup_1_a" not in k


# ─── CSV headers / row ────────────────────────────────────────────────────


class TestCsvShape:
    def test_three_header_rows(self):
        rows = build_qualtrics_csv_headers([Q_RATING, Q_OPEN], _resolved_prod())
        assert len(rows) == 3
        # First row holds column names
        assert "StartDate" in rows[0]
        assert "ResponseId" in rows[0]
        assert "Q5" in rows[0]
        assert "Q8" in rows[0]
        # Input-mode columns appear only for open questions
        assert "q1_recommend_input_mode" not in rows[0]
        assert "q6_most_impactful_input_mode" in rows[0]
        assert "source_interface" in rows[0]
        # submission_id is dropped — ResponseId already covers it
        assert "submission_id" not in rows[0]
        # Row 2 carries OPEN / CLOSE markers next to the human label
        joined_row2 = " | ".join(rows[2 - 1])
        assert "[CLOSE]" in joined_row2
        assert "[OPEN]" in joined_row2
        # Third row is JSON ImportId
        for cell in rows[2]:
            parsed = json.loads(cell)
            assert "ImportId" in parsed

    def test_no_followup_columns_in_header(self):
        rows = build_qualtrics_csv_headers([Q_OPEN], _resolved_prod())
        for row in rows:
            for cell in row:
                assert "followup_1" not in cell
                assert "followup_2" not in cell

    def test_csv_row_combines_followups(self):
        cohort = Cohort(course_name="GenAI 101", program_type="Course")
        sub = Submission(
            id=uuid.uuid4(),
            cohort_id=cohort.id,
            status="completed",
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            time_to_complete_sec=300,
        )
        answer = Answer(
            submission_id=sub.id,
            question_id="q6_most_impactful",
            question_type="open",
            answer_raw="Main",
            input_mode="voice",
            followup_1_answer="Detail",
            followup_1_input_mode="voice",
        )
        headers = build_qualtrics_csv_headers([Q_OPEN], _resolved_prod())[0]
        row = build_qualtrics_csv_row(
            submission=sub,
            answers=[answer],
            cohort=cohort,
            questions=[Q_OPEN],
            target=_resolved_prod(),
        )
        # Map header → value for readability
        cells = dict(zip(headers, row))
        assert cells["Q8"] == "Main. Detail."
        assert cells["q6_most_impactful_input_mode"] == "voice"
        assert cells["source_interface"] == "Public Voice tool"
        # Status / Finished use Qualtrics' native human-readable values
        assert cells["Status"] == "IP Address"
        assert cells["Finished"] == "TRUE"
        # Internal bookkeeping columns are intentionally excluded from CSV
        assert "qualtrics_target" not in cells
        assert "qualtrics_payload_version" not in cells
        assert "session_token" not in cells
        # submission_id is omitted — ResponseId already carries the same value
        assert "submission_id" not in cells

    def test_csv_row_multi_outputs_choice_text(self):
        sub = Submission(
            id=uuid.uuid4(),
            cohort_id=uuid.uuid4(),
            status="completed",
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        answer = Answer(
            submission_id=sub.id,
            question_id="q4_likely_uses",
            question_type="multi",
            answer_raw=json.dumps(["Create content", "Summarize text"]),
        )
        headers = build_qualtrics_csv_headers([Q_MULTI], _resolved_prod())[0]
        row = build_qualtrics_csv_row(
            submission=sub,
            answers=[answer],
            cohort=None,
            questions=[Q_MULTI],
            target=_resolved_prod(),
        )
        cells = dict(zip(headers, row))
        # Main column carries human-readable choice text, not codes.
        assert cells["Q25"] == "Create content | Summarize text"
        # The redundant ``_text`` companion column is gone.
        assert "Q25_text" not in cells

    def test_csv_row_mcq_outputs_choice_text(self):
        """Closed single-choice columns show the choice label, not the recode int."""
        sub = Submission(
            id=uuid.uuid4(),
            cohort_id=uuid.uuid4(),
            status="completed",
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        answer = Answer(
            submission_id=sub.id,
            question_id="q2_confidence",
            question_type="mcq",
            answer_raw="Very confident",
        )
        headers = build_qualtrics_csv_headers([Q_MCQ], _resolved_prod())[0]
        row = build_qualtrics_csv_row(
            submission=sub,
            answers=[answer],
            cohort=None,
            questions=[Q_MCQ],
            target=_resolved_prod(),
        )
        cells = dict(zip(headers, row))
        assert cells["Q23"] == "Very confident"  # NOT "1"
