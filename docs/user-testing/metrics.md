# User-Testing Metrics — Source of Truth

Every number shown on the **User Testing Analytics** dashboard and every column
in the three user-testing CSV exports (`raw.csv`, `structured.csv`,
`user-testing.csv`) is computed by
[`apps/api/app/services/metrics_service.py`](../../apps/api/app/services/metrics_service.py).

If a metric is not in this table, it is not a real metric yet. If you find a
discrepancy between the dashboard and the CSVs, it is a bug — the bug is *not*
that they disagree, the bug is that one of them stopped reading from
`metrics_service`.

## Conventions

- **Submission status** is one of `started`, `completed`, `abandoned`.
  `abandoned` is inferred when `abandoned_at IS NOT NULL` on a non-completed
  row, or when `last_activity_at` is older than the session idle timeout.
- **Open-ended** means `question_type` in `{open, short_text}`.
- **Voice answer** means `input_mode == 'voice'`.
- **Word count** uses `str.split()` (whitespace tokenizer), consistent across
  dashboard and exports.
- Ratios are rounded to 4 decimals. `None` means "insufficient data" (e.g.
  avg word count when there are no answers of that mode).

## Metric catalog

| metric | soft-launch tie-in | definition | calculation | dashboard | export |
| --- | --- | --- | --- | --- | --- |
| `completion_rate` | S1 | Fraction of started sessions that finish | `completed / (completed + abandoned)` | Exec card, funnel | `user-testing.csv.completed_flag`, `raw.csv.final_completion_percent` |
| `voice_adoption_rate` | S2 | Participants who used voice for ≥1 open question | `subs with ≥1 voice open answer / subs with ≥1 open answer` | Exec card, Voice vs Text | `user-testing.csv.voice_used_any_flag` |
| `post_followup_vagueness_rate` | S3 | How often answers remain vague even after follow-ups | `vague_after_followups / open_answers_with_followup_shown` | Follow-up effectiveness | `structured.csv.final_response_specific_flag` |
| `avg_voice_word_count` | S4 / H1 | Richness of voice responses | `mean(answer_word_count) where input_mode='voice' and type∈open` | Voice vs Text | `user-testing.csv.avg_voice_open_ended_word_count` |
| `avg_text_word_count` | H1 compare | Richness of text responses | `mean(answer_word_count) where input_mode='text'` | Voice vs Text | `user-testing.csv.avg_text_open_ended_word_count` |
| `extraction_usefulness_rate` | S5 / H4 | Human-judged insight quality | `reviews.useful_flag=true / reviews.useful_flag IS NOT NULL` | Exec card, Extraction quality | `user-testing.csv.extraction_useful_flag`, `raw.csv.extraction_usefulness_rating` |
| `avg_time_to_complete_sec` | S6 | Time pressure / onboarding friction | `mean(time_to_complete_sec) over completed` | Exec card | `user-testing.csv.completion_time_sec` |
| `qualtrics_sync_success_rate` | S8 | Data-pipeline health | `subs with qualtrics_synced_at IS NOT NULL / completed` | Qualtrics card | `user-testing.csv.qualtrics_sync_success_flag`, `raw.csv.qualtrics_*` |
| `voice_conversation_completion_rate` | S10 / H5 | Stickiness of voice UX | `subs where started_in_voice AND ended_in_voice AND NOT switched_voice_to_text_any / subs started_in_voice` | Voice UX | `user-testing.csv.voice_conversation_completed_flag` |
| `followup_engagement_rate` | H2 participation | How often users engage when asked | `followups_answered / followups_shown` | Follow-up effectiveness | `raw.csv.total_followups_answered` |
| `specificity_improvement_rate` | H2 quality | How often follow-ups turn vague → specific | `specificity_improved_count / initial_vague_count` | Follow-up effectiveness | `structured.csv.specificity_improvement_rate` |
| `abandonment_rate_by_step` | Funnel | Where drop-off happens | `group by abandonment_stage, count / total_abandoned` | Friction | `raw.csv.abandonment_stage` |
| `transcript_edit_rate` | H5 / UX | Friction in voice-to-text flow | `voice answers with user_edited_transcript_flag / voice answers` | Voice UX | `structured.csv.user_edited_transcript_flag` |
| `mic_permission_failure_rate` | H6 | Device / browser friction | `subs where mic_permission_status='denied' / subs that prompted` | Tech health | `user-testing.csv.mic_permission_failure_flag` |
| `critical_error_rate` | H6 / S7 | Show-stopping failures | `subs where critical_error_flag / total subs` | Exec card, Tech health | `user-testing.csv.critical_error_flag` |
| `api_latency_p50 / p95` | UX | Slow-request diagnostic | `percentile over answer-level avg_api_latency_ms` | Tech health | `raw.csv.avg_api_latency_ms` / `max_api_latency_ms` |
| `browser_breakdown` | H6 | Compatibility spread | `count group by browser_name` | Tech health | `raw.csv.browser_name` |

## Soft-launch targets

The S-criteria targets live in `metrics_service.S_TARGETS` and are surfaced in
the dashboard as "hit / miss" badges.

```python
S_TARGETS = {
    "completion_rate": 0.80,             # S1
    "voice_adoption_rate": 0.50,         # S2
    "post_followup_vagueness_rate_max": 0.30,  # S3
    "avg_voice_word_count_min": 40,      # S4
    "extraction_usefulness_rate_min": 0.85,    # S5
    "avg_time_to_complete_max_sec": 480, # S6
    "qualtrics_sync_success_rate_min": 0.95,   # S8
    "voice_conversation_completion_rate_min": 0.70,  # S10
}
```

## Per-submission hypothesis flags

These are on every row of `user-testing.csv` and are computed by
`metrics_service.compute_hypothesis_flags`. Each flag is tri-state: `True` /
`False` / `None` (insufficient data).

| flag | supports hypothesis if | set to `False` if | `None` when |
| --- | --- | --- | --- |
| `h1_voice_more_detailed_support_flag` | voice avg > text avg on same submission | voice avg ≤ text avg | only one mode used |
| `h2_followups_improve_quality_support_flag` | at least one vague → specific after follow-ups | no improvement observed | no vague answers to begin with |
| `h3_completion_success_flag` | completed within `avg_time_to_complete_max_sec` | abandoned, or > target time | still in progress |
| `h4_extraction_useful_support_flag` | reviewer rated useful | reviewer rated not useful | not reviewed yet |
| `h5_voice_natural_support_flag` | started voice AND finished voice AND never switched | started voice but switched or ended text | never started in voice |
| `h6_device_compatibility_support_flag` | no critical error AND no mic denial AND no API failure | any of those occurred | — |

## Exports overview

There are exactly three user-testing CSVs. Do not create more structured CSVs.

| file | granularity | intended audience | primary use |
| --- | --- | --- | --- |
| `raw.csv` | 1 row per submission, per-question columns (`q1_`, `q2_`, …) repeated | data engineer / debugging | full fidelity; every field that exists on the submission |
| `structured.csv` | 1 row per (submission × main question) | analyst in pandas/Tableau | question-level and follow-up analysis |
| `user-testing.csv` | 1 row per submission | product/program manager | rapid soft-launch read-out, hypothesis-flag scorecard |

## Tests

- `apps/api/tests/test_metrics_service.py` — locks the definitions of
  `compute_submission_rollup`, `compute_hypothesis_flags`, and
  `compute_user_testing_metrics`.
- `apps/api/tests/test_export_service.py` — CSV schema snapshots for all
  three exports. Updating any column requires updating the corresponding
  snapshot in the same change.

Run both with:

```bash
cd apps/api && python -m pytest tests/ -q
```
