"""Unit tests for ``app.services.metrics_service``.

These tests construct real SQLAlchemy ORM objects in-memory (without flushing
them to a database) and exercise the pure-Python aggregation functions. The
goal is to lock down the definitions of:

- ``word_count``
- ``compute_submission_rollup``
- ``compute_hypothesis_flags``
- ``compute_user_testing_metrics``

so the dashboard, the three CSV exports, and any future consumer stay in sync.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Answer, Cohort, Extraction, ExtractionReview, Submission
from app.services.metrics_service import (
    S_TARGETS,
    compute_hypothesis_flags,
    compute_submission_rollup,
    compute_user_testing_metrics,
    safe_ratio,
    word_count,
)


UTC = timezone.utc


def _make_cohort(**over) -> Cohort:
    c = Cohort(
        id=uuid.uuid4(),
        name=over.get("name", "Test Cohort"),
        course_name=over.get("course_name", "Course"),
    )
    for k, v in over.items():
        setattr(c, k, v)
    return c


def _make_sub(cohort_id: uuid.UUID, **over) -> Submission:
    sub = Submission(
        id=uuid.uuid4(),
        cohort_id=cohort_id,
        status=over.get("status", "completed"),
        created_at=over.get("created_at", datetime.now(UTC)),
    )
    for k, v in over.items():
        setattr(sub, k, v)
    return sub


def _make_answer(sub: Submission, **over) -> Answer:
    a = Answer(
        id=uuid.uuid4(),
        submission_id=sub.id,
        question_id=over.get("question_id", "q1"),
        question_type=over.get("question_type", "open"),
    )
    for k, v in over.items():
        setattr(a, k, v)
    if a.answer_word_count is None and a.answer_raw:
        a.answer_word_count = word_count(a.answer_raw)
    return a


# ── word_count ─────────────────────────────────────────────────────────────


class TestWordCount:
    def test_empty(self):
        assert word_count(None) == 0
        assert word_count("") == 0
        assert word_count("   ") == 0

    def test_simple(self):
        assert word_count("hello world") == 2
        assert word_count("one  two   three") == 3
        assert word_count("a b c d e") == 5


# ── compute_submission_rollup ──────────────────────────────────────────────


class TestSubmissionRollup:
    def test_counts_open_vs_closed(self):
        cohort = _make_cohort()
        sub = _make_sub(cohort.id)
        answers = [
            _make_answer(sub, question_id="q1", question_type="open",
                         answer_raw="voice answer here with six words now",
                         input_mode="voice"),
            _make_answer(sub, question_id="q2", question_type="open",
                         answer_raw="text reply two words",
                         input_mode="text"),
            _make_answer(sub, question_id="q3", question_type="mcq",
                         answer_raw="option_a", input_mode="none"),
        ]
        rollup = compute_submission_rollup(sub, answers)
        assert rollup.total_questions_seen == 3
        assert rollup.total_questions_answered == 3
        assert rollup.total_open_ended_questions_seen == 2
        assert rollup.total_open_ended_questions_answered == 2
        assert rollup.voice_used_any_flag is True
        assert rollup.avg_voice_open_ended_word_count == 7
        assert rollup.avg_text_open_ended_word_count == 4

    def test_voice_conversation_completion(self):
        cohort = _make_cohort()
        sub = _make_sub(
            cohort.id,
            started_in_voice=True,
            ended_in_voice=True,
            switched_voice_to_text_any=False,
        )
        answers = [
            _make_answer(sub, question_id="q1", question_type="open",
                         answer_raw="hi there", input_mode="voice"),
        ]
        rollup = compute_submission_rollup(sub, answers)
        assert rollup.voice_conversation_completed_flag is True
        assert rollup.started_in_voice_flag is True
        assert rollup.ended_in_voice_flag is True

    def test_followup_counting_and_improvement(self):
        cohort = _make_cohort()
        sub = _make_sub(cohort.id)
        answers = [
            _make_answer(
                sub,
                question_id="q1",
                question_type="open",
                answer_raw="short",
                input_mode="voice",
                is_vague=True,
                followup_1="Can you give an example?",
                followup_1_answer="Yes, a specific example with details",
                followup_1_is_vague=False,
                followup_2=None,
                followup_2_answer=None,
                specificity_improved_after_followups_flag=True,
                final_response_specific_flag=True,
            ),
        ]
        rollup = compute_submission_rollup(sub, answers)
        assert rollup.total_followups_shown == 1
        assert rollup.total_followups_answered == 1
        assert rollup.total_followups_skipped == 0
        assert rollup.initial_vague_answer_count == 1
        assert rollup.specificity_improvement_rate == 1.0


# ── compute_hypothesis_flags ───────────────────────────────────────────────


class TestHypothesisFlags:
    def _setup_rollup(self, **over) -> Submission:
        cohort = _make_cohort()
        sub = _make_sub(cohort.id, **over)
        answers: list[Answer] = over.get("answers", [])
        return sub, compute_submission_rollup(sub, answers)

    def test_h1_requires_both_modes(self):
        sub, rollup = self._setup_rollup()
        # Only voice answers → H1 is None (insufficient comparison data)
        flags = compute_hypothesis_flags(sub, rollup, None)
        assert flags["h1_voice_more_detailed_support_flag"] is None

    def test_h1_true_when_voice_longer(self):
        cohort = _make_cohort()
        sub = _make_sub(cohort.id)
        answers = [
            _make_answer(sub, question_id="q1", question_type="open",
                         answer_raw="voice reply with many words included here easily",
                         input_mode="voice"),
            _make_answer(sub, question_id="q2", question_type="open",
                         answer_raw="short text",
                         input_mode="text"),
        ]
        rollup = compute_submission_rollup(sub, answers)
        flags = compute_hypothesis_flags(sub, rollup, None)
        assert flags["h1_voice_more_detailed_support_flag"] is True

    def test_h3_abandonment_fails_completion(self):
        cohort = _make_cohort()
        sub = _make_sub(cohort.id, status="abandoned")
        rollup = compute_submission_rollup(sub, [])
        flags = compute_hypothesis_flags(sub, rollup, None)
        assert flags["h3_completion_success_flag"] is False

    def test_h4_requires_review(self):
        cohort = _make_cohort()
        sub = _make_sub(cohort.id)
        rollup = compute_submission_rollup(sub, [])
        assert compute_hypothesis_flags(sub, rollup, None)["h4_extraction_useful_support_flag"] is None
        review = ExtractionReview(
            id=uuid.uuid4(),
            submission_id=sub.id,
            reviewed_by="allison",
            useful_flag=True,
        )
        flags = compute_hypothesis_flags(sub, rollup, review)
        assert flags["h4_extraction_useful_support_flag"] is True

    def test_h6_false_on_critical_error(self):
        cohort = _make_cohort()
        sub = _make_sub(cohort.id, critical_error_flag=True)
        rollup = compute_submission_rollup(sub, [])
        flags = compute_hypothesis_flags(sub, rollup, None)
        assert flags["h6_device_compatibility_support_flag"] is False


# ── compute_user_testing_metrics ───────────────────────────────────────────


class TestUserTestingMetrics:
    def _make_dataset(self) -> tuple[list[Submission], dict[str, list[Answer]]]:
        cohort = _make_cohort()
        now = datetime.now(UTC)

        # S1: 4 completed + 1 abandoned → 80% exactly
        completed_voice = _make_sub(cohort.id, status="completed",
                                    time_to_complete_sec=300,
                                    started_in_voice=True,
                                    ended_in_voice=True,
                                    created_at=now - timedelta(minutes=10))
        completed_voice_abandoned_vox = _make_sub(
            cohort.id, status="completed",
            time_to_complete_sec=420,
            started_in_voice=True,
            ended_in_voice=False,
            switched_voice_to_text_any=True,
        )
        completed_text_only = _make_sub(
            cohort.id, status="completed",
            time_to_complete_sec=240,
            started_in_voice=False,
            ended_in_voice=False,
        )
        completed_mixed = _make_sub(
            cohort.id, status="completed",
            time_to_complete_sec=360,
            started_in_voice=True,
            ended_in_voice=True,
        )
        abandoned = _make_sub(cohort.id, status="abandoned",
                              abandonment_stage="q2_barriers")

        subs = [completed_voice, completed_voice_abandoned_vox,
                completed_text_only, completed_mixed, abandoned]

        answers_by_sub: dict[str, list[Answer]] = {}
        # Voice-only completion
        answers_by_sub[str(completed_voice.id)] = [
            _make_answer(completed_voice, question_id="q1",
                         question_type="open",
                         answer_raw="a voice answer with exactly ten words here for counting",
                         input_mode="voice"),
        ]
        # Voice start but switched to text; triggers H5 failure
        answers_by_sub[str(completed_voice_abandoned_vox.id)] = [
            _make_answer(completed_voice_abandoned_vox, question_id="q1",
                         question_type="open",
                         answer_raw="voice start",
                         input_mode="voice"),
            _make_answer(completed_voice_abandoned_vox, question_id="q2",
                         question_type="open",
                         answer_raw="text finish after switching",
                         input_mode="text"),
        ]
        # Text-only with a vague + improved followup
        answers_by_sub[str(completed_text_only.id)] = [
            _make_answer(completed_text_only, question_id="q1",
                         question_type="open",
                         answer_raw="short",
                         input_mode="text",
                         is_vague=True,
                         followup_1="Can you give an example?",
                         followup_1_answer="Yes specifically I did X at work",
                         followup_1_is_vague=False,
                         specificity_improved_after_followups_flag=True,
                         final_response_specific_flag=True),
        ]
        # Mixed: one voice, one text
        answers_by_sub[str(completed_mixed.id)] = [
            _make_answer(completed_mixed, question_id="q1",
                         question_type="open",
                         answer_raw="voice response with several extra words here",
                         input_mode="voice"),
            _make_answer(completed_mixed, question_id="q2",
                         question_type="open",
                         answer_raw="text short reply",
                         input_mode="text"),
        ]
        # Abandoned — no answers
        answers_by_sub[str(abandoned.id)] = []

        return subs, answers_by_sub

    def test_totals_and_completion_rate(self):
        subs, answers = self._make_dataset()
        m = compute_user_testing_metrics(subs, answers)
        assert m["totals"]["total_submissions"] == 5
        assert m["totals"]["completed"] == 4
        assert m["totals"]["abandoned"] == 1
        # completed / (completed+abandoned) = 4/5
        assert m["executive"]["completion_rate"] == pytest.approx(0.8, abs=1e-3)

    def test_voice_adoption_and_vt_word_counts(self):
        subs, answers = self._make_dataset()
        m = compute_user_testing_metrics(subs, answers)
        # 3 of 4 completed-with-open voice-used → 0.75
        assert m["executive"]["voice_adoption_rate"] == pytest.approx(0.75, abs=1e-3)
        avg_voice = m["voice_vs_text"]["avg_voice_word_count"]
        avg_text = m["voice_vs_text"]["avg_text_word_count"]
        assert avg_voice and avg_voice > 0
        assert avg_text and avg_text > 0
        # Voice answers in dataset are longer on average than text
        assert avg_voice > avg_text

    def test_followup_effectiveness(self):
        subs, answers = self._make_dataset()
        m = compute_user_testing_metrics(subs, answers)
        fe = m["followup_effectiveness"]
        assert fe["followups_shown_total"] == 1
        assert fe["followups_answered_total"] == 1
        assert fe["specificity_improvement_count"] == 1
        assert fe["specificity_improvement_rate"] == pytest.approx(1.0)

    def test_voice_conversation_completion_rate(self):
        subs, answers = self._make_dataset()
        m = compute_user_testing_metrics(subs, answers)
        # 3 started in voice; 2 of those completed in voice without switching
        vux = m["voice_ux"]
        assert vux["started_in_voice_count"] == 3
        assert vux["voice_conversation_completed_count"] == 2
        assert vux["voice_conversation_completion_rate"] == pytest.approx(2 / 3, abs=1e-3)

    def test_targets_are_exposed(self):
        subs, answers = self._make_dataset()
        m = compute_user_testing_metrics(subs, answers)
        assert m["targets"] == S_TARGETS

    def test_empty_inputs_do_not_crash(self):
        m = compute_user_testing_metrics([], {})
        assert m["totals"]["total_submissions"] == 0
        # With no data we intentionally return ``None`` for rates so the
        # dashboard can show "—" rather than a misleading 0%.
        assert m["executive"]["completion_rate"] is None
        assert m["executive"]["voice_adoption_rate"] is None
        assert m["voice_vs_text"]["avg_voice_word_count"] is None
        assert m["funnel"][0]["count"] == 0


# ── safe_ratio helper ──────────────────────────────────────────────────────


def test_safe_ratio_zero_denominator():
    # ``None`` (not 0.0) when there is nothing to divide by, so callers
    # can distinguish "no data yet" from "all outcomes were 0".
    assert safe_ratio(5, 0) is None
    assert safe_ratio(0, 0) is None
    assert safe_ratio(0, 10) == 0.0
    assert safe_ratio(3, 10) == 0.3
