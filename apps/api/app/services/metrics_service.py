"""Source-of-truth user-testing metrics for dashboards and exports.

Everything user-testing / soft-launch related routes through this module. The
dashboard endpoint and all three CSV exports (raw, structured, user-testing)
call into ``compute_user_testing_metrics`` so the numbers are always identical.

Conventions
===========

- Submission status is ``started``, ``completed``, or ``abandoned``.
  ``abandoned`` is inferred from ``abandoned_at`` IS NOT NULL on a non-completed
  row, or from ``last_activity_at`` older than the session idle timeout.
- "Open-ended" means ``question_type`` in {``open``, ``short_text``}.
- A voice answer is one with ``input_mode == 'voice'``.
- Word counts use ``str.split()`` (whitespace tokenizer) — stable across dashboard
  and export.

Metric mapping (keep in sync with docs/user-testing/metrics.md):

================================= ============================================= ======================================================================
metric_name                        definition                                    calculation
================================= ============================================= ======================================================================
completion_rate                   S1                                            completed / (completed + abandoned)
voice_adoption_rate               S2 — at least one voice answer                subs with >=1 voice open answer / subs with >=1 open answer
post_followup_vagueness_rate      S3                                            vague_after_followups / total_open_answers_with_followup
avg_voice_word_count              S4                                            mean(answer_word_count) where input_mode=voice and type in open/short
avg_text_word_count               H1 comparison                                 mean(answer_word_count) where input_mode=text
extraction_usefulness_rate        S5                                            reviews.useful_flag=true / reviews.useful_flag IS NOT NULL
avg_time_to_complete_sec          S6                                            mean(time_to_complete_sec) over completed
qualtrics_sync_success_rate       S8                                            subs with qualtrics_synced_at NOT NULL / completed subs
voice_conversation_completion     S10                                           subs where started_in_voice AND ended_in_voice AND NOT switched_v2t
followup_engagement_rate          H2 participation                              fu shown with any fu answer / fu shown total
abandonment_rate_by_step          funnel diagnostic                             by question_id
transcript_edit_rate              H5 + UX diagnostic                            voice answers with user_edited_transcript_flag / voice answers
mic_permission_failure_rate       H6 reliability                                subs with mic_permission_status=denied / subs that prompted
critical_error_rate               H6                                            subs with critical_error_flag / all subs
================================= ============================================= ======================================================================

Every function accepts raw ORM lists (Submission, Answer, ExtractionReview,
Cohort) and returns plain dictionaries — no database session, easy to unit
test.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean, median
from typing import Iterable, Optional

from app.models import Answer, Cohort, Extraction, ExtractionReview, Submission

OPEN_TYPES = {"open", "short_text"}

# Success criteria targets used by the dashboard to badge exec cards
S_TARGETS = {
    "completion_rate": 0.80,
    "voice_adoption_rate": 0.50,
    "post_followup_vagueness_rate_max": 0.30,
    "avg_voice_word_count_min": 40,
    "extraction_usefulness_rate_min": 0.85,
    "avg_time_to_complete_max_sec": 480,
    "qualtrics_sync_success_rate_min": 0.95,
    "voice_conversation_completion_rate_min": 0.70,
}


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────


def word_count(text: Optional[str]) -> int:
    """Whitespace tokenizer word count — stable across dashboard and exports."""
    if not text:
        return 0
    return len([w for w in text.split() if w.strip()])


def safe_ratio(num: int | float, denom: int | float) -> Optional[float]:
    """Ratio that returns ``None`` when there is no denominator.

    This is intentional: for dashboard metrics there is a real UX
    difference between "0% because the data says 0%" and "n/a because
    nothing has happened yet". Callers that want the old behaviour can
    coalesce with ``or 0.0`` at the call site.
    """
    if not denom:
        return None
    return round(num / denom, 4)


def _as_utc(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _answer_wc(a: Answer) -> int:
    if a.answer_word_count is not None:
        return a.answer_word_count
    return word_count(a.answer_raw)


def _is_open(a: Answer) -> bool:
    return (a.question_type or "").lower() in OPEN_TYPES


def _is_voice(a: Answer) -> bool:
    return (a.input_mode or "").lower() == "voice"


def _is_text(a: Answer) -> bool:
    return (a.input_mode or "").lower() == "text"


def _total_open_wc(answers: list[Answer]) -> int:
    return sum(_answer_wc(a) for a in answers if _is_open(a))


# ─────────────────────────────────────────────────────────────────────────────
# Per-submission rollups (used by exports, dashboard, and user-testing CSV)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SubmissionRollup:
    submission_id: str
    total_questions_seen: int
    total_questions_answered: int
    total_open_ended_questions_seen: int
    total_open_ended_questions_answered: int
    total_followups_shown: int
    total_followups_answered: int
    total_followups_skipped: int
    voice_used_any_flag: bool
    started_in_voice_flag: Optional[bool]
    ended_in_voice_flag: Optional[bool]
    switched_voice_to_text_any_flag: bool
    switched_text_to_voice_any_flag: bool
    voice_conversation_completed_flag: bool
    total_open_ended_word_count: int
    avg_open_ended_word_count: Optional[float]
    avg_voice_open_ended_word_count: Optional[float]
    avg_text_open_ended_word_count: Optional[float]
    initial_vague_answer_count: int
    vague_answer_count_after_followups: int
    specificity_improvement_rate: Optional[float]


def compute_submission_rollup(sub: Submission, answers: Iterable[Answer]) -> SubmissionRollup:
    ans_list = list(answers)

    open_answers = [a for a in ans_list if _is_open(a)]
    open_answered = [a for a in open_answers if (a.answer_raw or "").strip()]
    voice_open = [a for a in open_answered if _is_voice(a)]
    text_open = [a for a in open_answered if _is_text(a)]

    followups_shown = sum(
        (1 if a.followup_1 else 0) + (1 if a.followup_2 else 0) for a in ans_list
    )
    followups_answered = sum(
        (1 if a.followup_1_answer else 0) + (1 if a.followup_2_answer else 0)
        for a in ans_list
    )
    followups_skipped = sum(
        (1 if a.followup_1 and not a.followup_1_answer else 0)
        + (1 if a.followup_2 and not a.followup_2_answer else 0)
        for a in ans_list
    )

    initial_vague = sum(1 for a in open_answers if a.is_vague)
    after_vague = sum(
        1
        for a in open_answers
        if a.final_response_specific_flag is False
    )
    improved = sum(
        1
        for a in open_answers
        if a.specificity_improved_after_followups_flag
    )
    improvement_rate = safe_ratio(improved, initial_vague) if initial_vague else None

    voice_used_any = any(_is_voice(a) for a in open_answers)

    # ended_in_voice preference order: submission column → last open answer's mode
    ended_in_voice = sub.ended_in_voice
    if ended_in_voice is None and open_answered:
        ended_in_voice = _is_voice(open_answered[-1])

    started_in_voice = sub.started_in_voice
    if started_in_voice is None and open_answered:
        started_in_voice = _is_voice(open_answered[0])

    voice_conversation_completed = bool(
        started_in_voice and ended_in_voice and not sub.switched_voice_to_text_any
    )

    avg_open_wc = mean(_answer_wc(a) for a in open_answered) if open_answered else None
    avg_voice_wc = mean(_answer_wc(a) for a in voice_open) if voice_open else None
    avg_text_wc = mean(_answer_wc(a) for a in text_open) if text_open else None

    return SubmissionRollup(
        submission_id=str(sub.id),
        total_questions_seen=len(ans_list),
        total_questions_answered=sum(1 for a in ans_list if (a.answer_raw or "").strip()),
        total_open_ended_questions_seen=len(open_answers),
        total_open_ended_questions_answered=len(open_answered),
        total_followups_shown=followups_shown,
        total_followups_answered=followups_answered,
        total_followups_skipped=followups_skipped,
        voice_used_any_flag=voice_used_any,
        started_in_voice_flag=started_in_voice,
        ended_in_voice_flag=ended_in_voice,
        switched_voice_to_text_any_flag=bool(sub.switched_voice_to_text_any),
        switched_text_to_voice_any_flag=bool(sub.switched_text_to_voice_any),
        voice_conversation_completed_flag=voice_conversation_completed,
        total_open_ended_word_count=_total_open_wc(ans_list),
        avg_open_ended_word_count=round(avg_open_wc, 2) if avg_open_wc is not None else None,
        avg_voice_open_ended_word_count=round(avg_voice_wc, 2) if avg_voice_wc is not None else None,
        avg_text_open_ended_word_count=round(avg_text_wc, 2) if avg_text_wc is not None else None,
        initial_vague_answer_count=initial_vague,
        vague_answer_count_after_followups=after_vague,
        specificity_improvement_rate=improvement_rate,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Hypothesis heuristic flags (one per submission)
# ─────────────────────────────────────────────────────────────────────────────


def compute_hypothesis_flags(
    sub: Submission,
    rollup: SubmissionRollup,
    review: Optional[ExtractionReview],
) -> dict:
    """Heuristic per-submission support flags for H1-H6.

    Each is a tri-state: True / False / None (insufficient data).
    """
    # H1: voice > text within the submission when both modes are used
    h1 = None
    if (
        rollup.avg_voice_open_ended_word_count is not None
        and rollup.avg_text_open_ended_word_count is not None
    ):
        h1 = rollup.avg_voice_open_ended_word_count > rollup.avg_text_open_ended_word_count

    # H2: follow-ups observed improve specificity on at least one answer
    h2 = None
    if rollup.initial_vague_answer_count > 0:
        h2 = (rollup.specificity_improvement_rate or 0) > 0

    # H3: completed within target time
    h3 = None
    if sub.status == "completed":
        if sub.time_to_complete_sec is not None:
            h3 = sub.time_to_complete_sec <= S_TARGETS["avg_time_to_complete_max_sec"]
        else:
            h3 = True
    elif sub.status == "abandoned":
        h3 = False

    # H4: extraction rated useful
    h4 = None
    if review and review.useful_flag is not None:
        h4 = review.useful_flag

    # H5: started voice, stayed voice, never switched
    h5 = None
    if rollup.started_in_voice_flag is True:
        h5 = rollup.voice_conversation_completed_flag

    # H6: no critical error, no mic denial, no API failures
    h6 = not (
        sub.critical_error_flag
        or (sub.mic_permission_status == "denied")
        or (sub.total_api_failures or 0) > 0
    )

    return {
        "h1_voice_more_detailed_support_flag": h1,
        "h2_followups_improve_quality_support_flag": h2,
        "h3_completion_success_flag": h3,
        "h4_extraction_useful_support_flag": h4,
        "h5_voice_natural_support_flag": h5,
        "h6_device_compatibility_support_flag": h6,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Top-level aggregation for the dashboard + user-testing CSV header rollups
# ─────────────────────────────────────────────────────────────────────────────


def compute_user_testing_metrics(
    submissions: list[Submission],
    answers_by_sub: dict[str, list[Answer]],
    reviews_by_sub: dict[str, ExtractionReview] | None = None,
    cohorts_by_id: dict[str, Cohort] | None = None,
    extractions_by_sub: dict[str, Extraction] | None = None,
) -> dict:
    """Compute the full user-testing metrics payload.

    Consumed by:
    - ``GET /v1/admin/user-testing-analytics`` (dashboard)
    - ``generate_user_testing_csv`` (soft-launch CSV rollup row)
    - Structured/Raw CSV submission-level rollups (via submission rollups)
    """
    reviews_by_sub = reviews_by_sub or {}
    cohorts_by_id = cohorts_by_id or {}
    extractions_by_sub = extractions_by_sub or {}

    total = len(submissions)
    completed = [s for s in submissions if s.status == "completed"]
    abandoned = [s for s in submissions if s.status == "abandoned"]
    started = [s for s in submissions if s.status in ("started", "completed", "abandoned")]

    # Per-submission rollups
    rollups = {
        str(s.id): compute_submission_rollup(s, answers_by_sub.get(str(s.id), []))
        for s in submissions
    }

    # ── H1 word counts ──
    all_answers: list[Answer] = []
    for s in submissions:
        all_answers.extend(answers_by_sub.get(str(s.id), []))
    open_answers = [a for a in all_answers if _is_open(a) and (a.answer_raw or "").strip()]
    voice_open = [a for a in open_answers if _is_voice(a)]
    text_open = [a for a in open_answers if _is_text(a)]

    avg_voice_wc = mean(_answer_wc(a) for a in voice_open) if voice_open else None
    avg_text_wc = mean(_answer_wc(a) for a in text_open) if text_open else None
    median_voice_wc = median(_answer_wc(a) for a in voice_open) if voice_open else None
    median_text_wc = median(_answer_wc(a) for a in text_open) if text_open else None

    # ── H2 follow-up effectiveness ──
    followups_shown_total = sum(
        (1 if a.followup_1 else 0) + (1 if a.followup_2 else 0)
        for a in all_answers
    )
    followups_answered_total = sum(
        (1 if a.followup_1_answer else 0) + (1 if a.followup_2_answer else 0)
        for a in all_answers
    )
    initial_vague_total = sum(
        1 for a in all_answers if _is_open(a) and a.is_vague
    )
    after_vague_total = sum(
        1 for a in all_answers if _is_open(a) and a.final_response_specific_flag is False
    )
    improved_total = sum(
        1
        for a in all_answers
        if _is_open(a) and a.specificity_improved_after_followups_flag
    )

    # Per-question follow-up effectiveness (top performing prompts)
    followup_prompt_stats: dict[str, dict] = defaultdict(
        lambda: {"shown": 0, "answered": 0, "improved": 0}
    )
    for a in all_answers:
        for prompt, ans, improved in (
            (a.followup_1, a.followup_1_answer, a.followup_1_is_vague is False),
            (a.followup_2, a.followup_2_answer, a.followup_2_is_vague is False),
        ):
            if not prompt:
                continue
            slot = followup_prompt_stats[prompt]
            slot["shown"] += 1
            if ans:
                slot["answered"] += 1
                if improved:
                    slot["improved"] += 1

    top_followup_prompts = sorted(
        [
            {
                "prompt": prompt,
                "shown": v["shown"],
                "answered": v["answered"],
                "improved": v["improved"],
                "improvement_rate": safe_ratio(v["improved"], v["shown"]),
            }
            for prompt, v in followup_prompt_stats.items()
        ],
        key=lambda x: (x["improvement_rate"], x["shown"]),
        reverse=True,
    )[:10]

    # ── H3 completion ──
    completion_rate = safe_ratio(len(completed), len(completed) + len(abandoned)) if (
        len(completed) + len(abandoned)
    ) else safe_ratio(len(completed), total)
    complete_times = [s.time_to_complete_sec for s in completed if s.time_to_complete_sec]
    avg_time_sec = round(mean(complete_times), 1) if complete_times else None
    median_time_sec = round(median(complete_times), 1) if complete_times else None

    # Abandonment breakdown
    abandonment_by_step = Counter(s.abandonment_stage for s in abandoned if s.abandonment_stage)
    abandonment_list = [
        {"question_id": qid, "count": n}
        for qid, n in sorted(abandonment_by_step.items(), key=lambda x: x[1], reverse=True)
    ]

    # ── H5 voice conversation completion ──
    started_in_voice = [
        s for s in submissions if rollups[str(s.id)].started_in_voice_flag is True
    ]
    vcc_count = sum(
        1 for s in started_in_voice if rollups[str(s.id)].voice_conversation_completed_flag
    )
    voice_conversation_completion_rate = safe_ratio(vcc_count, len(started_in_voice))

    # Voice adoption rate: fraction of submissions with >=1 voice open answer
    submissions_with_open = [
        s for s in submissions if rollups[str(s.id)].total_open_ended_questions_answered > 0
    ]
    voice_adoption_count = sum(
        1 for s in submissions_with_open if rollups[str(s.id)].voice_used_any_flag
    )
    voice_adoption_rate = safe_ratio(voice_adoption_count, len(submissions_with_open))

    # Mode-switch rate
    mode_switch_count = sum(
        1
        for s in submissions
        if rollups[str(s.id)].switched_voice_to_text_any_flag
        or rollups[str(s.id)].switched_text_to_voice_any_flag
    )
    mode_switch_rate = safe_ratio(mode_switch_count, total)

    # ── H6 reliability ──
    mic_prompted = [s for s in submissions if s.mic_permission_status]
    mic_denied = [s for s in mic_prompted if s.mic_permission_status == "denied"]
    mic_permission_failure_rate = safe_ratio(len(mic_denied), len(mic_prompted))

    critical_errors = sum(1 for s in submissions if s.critical_error_flag)
    critical_error_rate = safe_ratio(critical_errors, total)

    api_latencies = [s.avg_api_latency_ms for s in submissions if s.avg_api_latency_ms]
    avg_api_latency = round(mean(api_latencies), 1) if api_latencies else None
    max_api_latency = max(api_latencies) if api_latencies else None

    browser_breakdown = Counter(s.browser_name or "unknown" for s in submissions)
    os_breakdown = Counter(s.os_name or "unknown" for s in submissions)
    device_breakdown = Counter(s.device_type or "unknown" for s in submissions)

    browser_error_rate = {
        browser: safe_ratio(
            sum(
                1
                for s in submissions
                if (s.browser_name or "unknown") == browser and s.critical_error_flag
            ),
            n,
        )
        for browser, n in browser_breakdown.items()
    }

    # ── H4 extraction review ──
    review_values = list(reviews_by_sub.values()) if reviews_by_sub else []
    reviews_with_useful = [r for r in review_values if r.useful_flag is not None]
    useful_count = sum(1 for r in reviews_with_useful if r.useful_flag)
    # ``None`` (not 0.0) when no reviews exist so the dashboard can distinguish
    # "nobody has reviewed extractions yet" from "all reviews said not useful".
    extraction_usefulness_rate = (
        safe_ratio(useful_count, len(reviews_with_useful))
        if reviews_with_useful
        else None
    )
    review_coverage = safe_ratio(len(review_values), len(completed))
    accuracy_ratings = [r.accuracy_rating for r in review_values if r.accuracy_rating is not None]
    usefulness_ratings = [r.usefulness_rating for r in review_values if r.usefulness_rating is not None]
    avg_accuracy_rating = round(mean(accuracy_ratings), 2) if accuracy_ratings else None
    avg_usefulness_rating = round(mean(usefulness_ratings), 2) if usefulness_ratings else None

    # Extraction success
    extraction_rows = list(extractions_by_sub.values())
    extraction_success_rate = safe_ratio(
        sum(1 for e in extraction_rows if e.success_flag),
        len(extraction_rows),
    )

    # ── S8 Qualtrics sync ──
    qualtrics_attempted = [s for s in completed if (s.qualtrics_sync_attempt_count or 0) > 0]
    qualtrics_succeeded = [s for s in qualtrics_attempted if s.qualtrics_synced_at is not None]
    # ``None`` when Qualtrics hasn't been attempted for any submission (e.g.
    # the integration is not configured) so the dashboard can show "n/a"
    # rather than a misleading 0%.
    qualtrics_sync_success_rate = (
        safe_ratio(len(qualtrics_succeeded), len(qualtrics_attempted))
        if qualtrics_attempted
        else None
    )
    qualtrics_failed = [s for s in qualtrics_attempted if not s.qualtrics_synced_at]
    qualtrics_latencies = [s.qualtrics_sync_latency_ms for s in qualtrics_succeeded if s.qualtrics_sync_latency_ms]
    avg_qualtrics_latency_ms = round(mean(qualtrics_latencies), 1) if qualtrics_latencies else None
    recent_failures = [
        {
            "submission_id": str(s.id),
            "attempts": s.qualtrics_sync_attempt_count or 0,
            "last_attempt_at": s.qualtrics_sync_last_attempt_at.isoformat() if s.qualtrics_sync_last_attempt_at else None,
            "error": s.qualtrics_sync_last_error or "",
        }
        for s in sorted(
            qualtrics_failed,
            key=lambda s: _as_utc(s.qualtrics_sync_last_attempt_at) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:10]
    ]

    # ── Post-followup vagueness rate (S3) ──
    open_with_followup = [
        a for a in all_answers if _is_open(a) and (a.followup_1_answer or a.followup_2_answer)
    ]
    post_fu_vague = sum(
        1
        for a in open_with_followup
        if (a.final_response_specific_flag is False)
        or (a.followup_2_is_vague if a.followup_2_answer else a.followup_1_is_vague)
    )
    post_followup_vagueness_rate = safe_ratio(post_fu_vague, len(open_with_followup))

    # ── Transcript edit rate (voice answers only) ──
    voice_answers = [a for a in all_answers if _is_voice(a)]
    transcript_edit_rate = safe_ratio(
        sum(1 for a in voice_answers if a.user_edited_transcript_flag),
        len(voice_answers),
    )

    # ── Followup engagement / answer rate ──
    followup_engagement_rate = safe_ratio(followups_answered_total, followups_shown_total)

    # ── Funnel ──
    funnel = {
        "opened": total,
        "started": len(started),
        "first_answer_started": sum(
            1 for s in submissions if rollups[str(s.id)].total_questions_answered >= 1
        ),
        "followup_shown": sum(
            1 for s in submissions if rollups[str(s.id)].total_followups_shown > 0
        ),
        "completed": len(completed),
        "qualtrics_synced": len(qualtrics_succeeded),
    }
    funnel_stages = [
        {"stage": "opened", "count": funnel["opened"]},
        {"stage": "started", "count": funnel["started"]},
        {"stage": "first_answer", "count": funnel["first_answer_started"]},
        {"stage": "followup_shown", "count": funnel["followup_shown"]},
        {"stage": "completed", "count": funnel["completed"]},
        {"stage": "qualtrics_synced", "count": funnel["qualtrics_synced"]},
    ]

    # ── Participant feedback rollup ──
    experience_ratings = [s.experience_rating for s in submissions if s.experience_rating]
    voice_ratings = [s.voice_experience_rating for s in submissions if s.voice_experience_rating]
    would_use_again = [s for s in submissions if s.would_use_again_flag is not None]
    would_use_yes = sum(1 for s in would_use_again if s.would_use_again_flag)
    confusion_flags = sum(1 for s in submissions if s.confusion_flag)
    reported_issues = sum(1 for s in submissions if s.reported_issue_flag)

    # ── Hypothesis flag summary ──
    hypothesis_totals = {
        "h1": {"true": 0, "false": 0, "null": 0},
        "h2": {"true": 0, "false": 0, "null": 0},
        "h3": {"true": 0, "false": 0, "null": 0},
        "h4": {"true": 0, "false": 0, "null": 0},
        "h5": {"true": 0, "false": 0, "null": 0},
        "h6": {"true": 0, "false": 0, "null": 0},
    }
    for s in submissions:
        rollup = rollups[str(s.id)]
        review = reviews_by_sub.get(str(s.id)) if reviews_by_sub else None
        flags = compute_hypothesis_flags(s, rollup, review)
        for key, prefix in (
            ("h1_voice_more_detailed_support_flag", "h1"),
            ("h2_followups_improve_quality_support_flag", "h2"),
            ("h3_completion_success_flag", "h3"),
            ("h4_extraction_useful_support_flag", "h4"),
            ("h5_voice_natural_support_flag", "h5"),
            ("h6_device_compatibility_support_flag", "h6"),
        ):
            val = flags[key]
            bucket = "null" if val is None else ("true" if val else "false")
            hypothesis_totals[prefix][bucket] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": S_TARGETS,
        "totals": {
            "total_submissions": total,
            "started": len(started),
            "completed": len(completed),
            "abandoned": len(abandoned),
            "in_progress": total - len(completed) - len(abandoned),
        },
        "executive": {
            "completion_rate": completion_rate,
            "voice_adoption_rate": voice_adoption_rate,
            "avg_time_to_complete_sec": avg_time_sec,
            "median_time_to_complete_sec": median_time_sec,
            "follow_up_engagement_rate": followup_engagement_rate,
            "extraction_usefulness_rate": extraction_usefulness_rate,
            "qualtrics_sync_success_rate": qualtrics_sync_success_rate,
            "critical_error_count": critical_errors,
            "mode_switch_rate": mode_switch_rate,
        },
        "funnel": funnel_stages,
        "voice_vs_text": {
            "avg_voice_word_count": round(avg_voice_wc, 2) if avg_voice_wc is not None else None,
            "avg_text_word_count": round(avg_text_wc, 2) if avg_text_wc is not None else None,
            "median_voice_word_count": median_voice_wc,
            "median_text_word_count": median_text_wc,
            "voice_open_answer_count": len(voice_open),
            "text_open_answer_count": len(text_open),
            "voice_vague_rate": safe_ratio(
                sum(1 for a in voice_open if a.is_vague), len(voice_open)
            ),
            "text_vague_rate": safe_ratio(
                sum(1 for a in text_open if a.is_vague), len(text_open)
            ),
            "mode_switch_rate": mode_switch_rate,
        },
        "followup_effectiveness": {
            "followups_shown_total": followups_shown_total,
            "followups_answered_total": followups_answered_total,
            "followup_engagement_rate": followup_engagement_rate,
            "initial_vague_count": initial_vague_total,
            "vague_after_followups_count": after_vague_total,
            "post_followup_vagueness_rate": post_followup_vagueness_rate,
            "specificity_improvement_count": improved_total,
            "specificity_improvement_rate": safe_ratio(improved_total, initial_vague_total),
            "top_followup_prompts": top_followup_prompts,
        },
        "survey_friction": {
            "abandonment_by_step": abandonment_list,
            "avg_time_to_complete_sec": avg_time_sec,
            "median_time_to_complete_sec": median_time_sec,
        },
        "voice_ux": {
            "started_in_voice_count": len(started_in_voice),
            "voice_conversation_completed_count": vcc_count,
            "voice_conversation_completion_rate": voice_conversation_completion_rate,
            "transcript_edit_rate": transcript_edit_rate,
            "mic_permission_failure_rate": mic_permission_failure_rate,
            "voice_duration_distribution": _bucketize(
                [a.voice_duration_sec for a in voice_answers if a.voice_duration_sec],
                buckets=[0, 15, 30, 60, 120, 300, 600],
            ),
        },
        "technical_health": {
            "browser_breakdown": _counter_to_list(browser_breakdown),
            "os_breakdown": _counter_to_list(os_breakdown),
            "device_breakdown": _counter_to_list(device_breakdown),
            "browser_error_rate": browser_error_rate,
            "avg_api_latency_ms": avg_api_latency,
            "max_api_latency_ms": max_api_latency,
            "total_timeouts": sum(s.timeout_count or 0 for s in submissions),
            "total_api_failures": sum(s.total_api_failures or 0 for s in submissions),
            "client_error_count": sum(s.client_error_count or 0 for s in submissions),
            "critical_error_count": critical_errors,
            "critical_error_rate": critical_error_rate,
        },
        "extraction_quality": {
            "extraction_success_rate": extraction_success_rate,
            "extractions_total": len(extraction_rows),
            "reviews_total": len(review_values),
            "reviews_with_useful_flag": len(reviews_with_useful),
            "review_coverage_rate": review_coverage,
            "extraction_usefulness_rate": extraction_usefulness_rate,
            "avg_accuracy_rating": avg_accuracy_rating,
            "avg_usefulness_rating": avg_usefulness_rating,
        },
        "qualtrics_sync": {
            "completed_count": len(completed),
            "attempted_count": len(qualtrics_attempted),
            "succeeded_count": len(qualtrics_succeeded),
            "failed_count": len(qualtrics_failed),
            "success_rate": qualtrics_sync_success_rate,
            "avg_latency_ms": avg_qualtrics_latency_ms,
            "recent_failures": recent_failures,
        },
        "participant_feedback": {
            "experience_rating_count": len(experience_ratings),
            "avg_experience_rating": round(mean(experience_ratings), 2) if experience_ratings else None,
            "voice_experience_rating_count": len(voice_ratings),
            "avg_voice_experience_rating": round(mean(voice_ratings), 2) if voice_ratings else None,
            "would_use_again_yes": would_use_yes,
            "would_use_again_total": len(would_use_again),
            "confusion_flag_count": confusion_flags,
            "reported_issue_count": reported_issues,
        },
        "facilitator_feedback": _facilitator_summary(cohorts_by_id),
        "hypothesis_totals": hypothesis_totals,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _bucketize(values: list[int], buckets: list[int]) -> list[dict]:
    """Group a list of ints into inclusive-lower exclusive-upper buckets."""
    if not values:
        return []
    out: list[dict] = []
    sorted_buckets = sorted(buckets)
    for i, lo in enumerate(sorted_buckets):
        hi = sorted_buckets[i + 1] if i + 1 < len(sorted_buckets) else None
        if hi is None:
            count = sum(1 for v in values if v >= lo)
            label = f">={lo}s"
        else:
            count = sum(1 for v in values if lo <= v < hi)
            label = f"{lo}-{hi}s"
        out.append({"bucket": label, "count": count})
    return out


def _counter_to_list(counter: Counter) -> list[dict]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda x: x[1], reverse=True)
    ]


def _facilitator_summary(cohorts_by_id: dict[str, Cohort]) -> list[dict]:
    out: list[dict] = []
    for cohort in cohorts_by_id.values():
        if not cohort.facilitator_feedback_text and not cohort.facilitator_reported_issue_flag:
            continue
        out.append(
            {
                "cohort_id": str(cohort.id),
                "cohort_name": cohort.name,
                "facilitator_name": cohort.facilitator_name,
                "launch_phase": cohort.launch_phase,
                "feedback_text": cohort.facilitator_feedback_text,
                "reported_issue": bool(cohort.facilitator_reported_issue_flag),
                "issue_type": cohort.facilitator_issue_type,
                "issue_notes": cohort.facilitator_issue_notes,
                "received_at": cohort.facilitator_feedback_received_at.isoformat()
                if cohort.facilitator_feedback_received_at
                else None,
            }
        )
    return out
