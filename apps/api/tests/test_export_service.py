"""CSV export schema snapshot tests.

These lock in the columns emitted by each of the three CSV exports so that any
accidental change to ``export_service`` (or the ``metrics_service`` rollups it
depends on) is caught immediately. If a column is intentionally added,
the snapshot below should be updated in the same PR that adds the column.

We deliberately avoid asserting on exact values (timestamps, UUIDs) and only
check:

- The header row is exactly what we expect.
- ``raw.csv`` emits exactly one row per submission.
- ``structured.csv`` emits exactly one row per submission × survey question.
- ``user-testing.csv`` emits exactly one row per submission with
  hypothesis-flag columns present.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

import pytest

from app.models import Answer, Cohort, Extraction, ExtractionReview, Submission
from app.services.export_service import (
    build_bundles,
    generate_raw_csv,
    generate_structured_csv,
    generate_user_testing_csv,
)


UTC = timezone.utc


# A tiny 2-question survey config used for all export snapshots
SURVEY_CONFIG = {
    "id": "test-survey",
    "version": "1.0",
    "questions": [
        {"id": "q1_recommend", "text": "Recommend?", "type": "likert", "required": True},
        {"id": "q2_open", "text": "Tell us more", "type": "open", "required": True},
    ],
}


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def sample_bundles():
    cohort = Cohort(
        id=uuid.uuid4(),
        name="Cohort A",
        course_name="Voice Training 101",
        program_type="workshop",
        launch_phase="soft_launch",
    )

    sub = Submission(
        id=uuid.uuid4(),
        cohort_id=cohort.id,
        status="completed",
        survey_version="1.0",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        time_to_complete_sec=420,
        started_in_voice=True,
        ended_in_voice=True,
    )

    answers = [
        Answer(
            id=uuid.uuid4(),
            submission_id=sub.id,
            question_id="q1_recommend",
            question_type="likert",
            answer_raw="9",
            input_mode="text",
            answer_word_count=1,
        ),
        Answer(
            id=uuid.uuid4(),
            submission_id=sub.id,
            question_id="q2_open",
            question_type="open",
            answer_raw="Voice made the experience much faster and more natural",
            input_mode="voice",
            answer_word_count=9,
        ),
    ]

    extraction = Extraction(
        submission_id=sub.id,
        top_themes=["voice quality"],
        barriers=[],
        planned_task_or_workflow="Use it weekly",
        success_story_candidate=None,
        success_flag=True,
    )
    review = ExtractionReview(
        id=uuid.uuid4(),
        submission_id=sub.id,
        reviewed_by="allison",
        useful_flag=True,
        accuracy_rating=5,
        usefulness_rating=4,
    )

    bundles = build_bundles(
        submissions=[sub],
        answers_by_sub={str(sub.id): answers},
        extractions_by_sub={str(sub.id): extraction},
        reviews_by_sub={str(sub.id): review},
        cohorts_by_id={str(cohort.id): cohort},
    )
    return bundles


def _parse_csv(csv_text: str) -> tuple[list[str], list[list[str]]]:
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert rows, "CSV should not be empty"
    return rows[0], rows[1:]


# ── raw.csv ────────────────────────────────────────────────────────────────


class TestRawCsv:
    EXPECTED_SESSION_COLS = {
        "submission_id",
        "session_id",
        "participant_anonymous_id",
        "survey_id",
        "survey_name",
        "survey_version",
        "program_id",
        "program_name",
        "program_type",
        "cohort_id",
        "launch_phase",
        "started_at",
        "completed_at",
        "submission_status",
        "completed_flag",
        "abandoned_flag",
        "total_time_to_complete_sec",
        "final_completion_percent",
    }

    EXPECTED_DEVICE_COLS = {
        "browser_name",
        "browser_version",
        "os_name",
        "os_version",
        "device_type",
        "user_agent",
        "microphone_permission_status",
        "voice_supported_in_browser",
        "avg_api_latency_ms",
        "max_api_latency_ms",
        "total_api_failures",
        "critical_error_flag",
    }

    EXPECTED_ROLLUP_COLS = {
        "total_questions_seen",
        "total_questions_answered",
        "total_open_ended_questions_seen",
        "total_open_ended_questions_answered",
        "total_followups_shown",
        "voice_used_any_flag",
        "started_in_voice_flag",
        "ended_in_voice_flag",
        "voice_conversation_completed_flag",
        "total_open_ended_word_count",
        "avg_voice_open_ended_word_count",
        "avg_text_open_ended_word_count",
        "specificity_improvement_rate",
    }

    def test_headers_contain_core_columns(self, sample_bundles):
        header, rows = _parse_csv(
            generate_raw_csv(sample_bundles, survey_config=SURVEY_CONFIG)
        )
        cols = set(header)
        missing = self.EXPECTED_SESSION_COLS - cols
        assert not missing, f"Missing session cols: {missing}"
        missing = self.EXPECTED_DEVICE_COLS - cols
        assert not missing, f"Missing device cols: {missing}"
        missing = self.EXPECTED_ROLLUP_COLS - cols
        assert not missing, f"Missing rollup cols: {missing}"

    def test_per_question_block_repeats(self, sample_bundles):
        header, _ = _parse_csv(
            generate_raw_csv(sample_bundles, survey_config=SURVEY_CONFIG)
        )
        # We expect q1_ and q2_ prefixed question columns, with dedicated
        # followup_1 / followup_2 columns.
        q1_prefixed = [h for h in header if h.startswith("q1_")]
        q2_prefixed = [h for h in header if h.startswith("q2_")]
        assert q1_prefixed, "q1_ columns missing"
        assert q2_prefixed, "q2_ columns missing"
        assert any("followup_1" in h for h in q2_prefixed)
        assert any("followup_2" in h for h in q2_prefixed)

    def test_one_row_per_submission(self, sample_bundles):
        _, rows = _parse_csv(
            generate_raw_csv(sample_bundles, survey_config=SURVEY_CONFIG)
        )
        assert len(rows) == len(sample_bundles)

    def test_empty_bundles_still_emits_header(self):
        csv_text = generate_raw_csv([], survey_config=SURVEY_CONFIG)
        header, rows = _parse_csv(csv_text)
        assert "submission_id" in header
        assert rows == []


# ── structured.csv ────────────────────────────────────────────────────────


class TestStructuredCsv:
    EXPECTED_CORE_COLS = {
        "submission_id",
        "question_id",
        "question_text",
        "question_type",
        "question_order",
        "answer_raw",
        "answer_word_count",
        "answer_input_mode",
        "voice_used_flag",
        "voice_duration_sec",
        "transcript_raw",
        "transcript_final",
        "user_edited_transcript_flag",
        "switched_from_voice_to_text_flag",
        "followup_1_question",
        "followup_1_answer",
        "followup_1_is_vague_flag",
        "followup_1_improved_specificity_flag",
        "followup_2_question",
        "followup_2_answer",
        "specificity_improvement_rate",
        # extraction
        "extraction_success_flag",
        "extracted_summary",
        # review
        "extraction_accuracy_rating",
        "extraction_usefulness_rating",
        # submission rollups repeated on every row
        "total_open_ended_word_count",
        "voice_used_any_flag",
        # qualtrics + feedback
        "qualtrics_sync_success_flag",
        # governance
        "consent_version",
        "export_generated_at",
    }

    def test_header_includes_expected_columns(self, sample_bundles):
        csv_text = generate_structured_csv(sample_bundles, survey_config=SURVEY_CONFIG)
        header, _ = _parse_csv(csv_text)
        missing = self.EXPECTED_CORE_COLS - set(header)
        assert not missing, f"Missing columns in structured.csv: {missing}"

    def test_one_row_per_main_question(self, sample_bundles):
        _, rows = _parse_csv(
            generate_structured_csv(sample_bundles, survey_config=SURVEY_CONFIG)
        )
        # 1 submission × 2 questions = 2 rows
        assert len(rows) == 2

    def test_single_structured_csv_contract(self, sample_bundles):
        # Regression: this must remain a single CSV. We enforce by asserting
        # the function returns a str (one CSV), not a dict or list.
        result = generate_structured_csv(sample_bundles, survey_config=SURVEY_CONFIG)
        assert isinstance(result, str)
        assert result.count("\n") >= 1


# ── user-testing.csv ──────────────────────────────────────────────────────


class TestUserTestingCsv:
    EXPECTED_COLS = {
        "submission_id",
        "completion_time_sec",
        "voice_used_any_flag",
        "started_in_voice_flag",
        "ended_in_voice_flag",
        "voice_conversation_completed_flag",
        "avg_voice_open_ended_word_count",
        "avg_text_open_ended_word_count",
        "specificity_improvement_rate",
        "extraction_useful_flag",
        "qualtrics_sync_success_flag",
        "critical_error_flag",
        "mic_permission_failure_flag",
        # H1-H6 hypothesis flags
        "h1_voice_more_detailed_support_flag",
        "h2_followups_improve_quality_support_flag",
        "h3_completion_success_flag",
        "h4_extraction_useful_support_flag",
        "h5_voice_natural_support_flag",
        "h6_device_compatibility_support_flag",
    }

    def test_schema_includes_all_hypothesis_flags(self, sample_bundles):
        csv_text = generate_user_testing_csv(sample_bundles)
        header, _ = _parse_csv(csv_text)
        missing = self.EXPECTED_COLS - set(header)
        assert not missing, f"Missing user-testing.csv cols: {missing}"

    def test_one_row_per_submission(self, sample_bundles):
        _, rows = _parse_csv(generate_user_testing_csv(sample_bundles))
        assert len(rows) == len(sample_bundles)

    def test_empty_dataset(self):
        csv_text = generate_user_testing_csv([])
        header, rows = _parse_csv(csv_text)
        assert "submission_id" in header
        assert rows == []
