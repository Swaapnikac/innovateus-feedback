# Soft-Launch Checklist (April 22 – May 5)

This page maps every soft-launch success criterion to the widget on the
**User Testing Analytics** page (`/admin/user-testing`) and to the CSV column
that backs it. It is the single checklist to run through before calling the
soft launch "green" or pulling the fallback Qualtrics link.

## Success criteria → dashboard widget → CSV column

| # | Criterion | Target | Dashboard widget | CSV column |
| --- | --- | --- | --- | --- |
| **S1** | Completion rate > 80% | ≥ 0.80 | Exec card "Completion rate" + Funnel section | `user-testing.csv.completed_flag`, `raw.csv.final_completion_percent` |
| **S2** | Voice adoption > 50% | ≥ 0.50 | Exec card "Voice adoption" | `user-testing.csv.voice_used_any_flag` |
| **S3** | Post-follow-up vagueness < 30% | ≤ 0.30 | Follow-up effectiveness → "Vague after follow-ups" | `structured.csv.final_response_specific_flag`, `raw.csv.followup_*_is_vague_flag` |
| **S4** | Avg voice open answer > 40 words | ≥ 40 | Voice vs Text comparison | `user-testing.csv.avg_voice_open_ended_word_count`, `structured.csv.answer_word_count` |
| **S5** | > 85% of extractions rated useful | ≥ 0.85 | Extraction quality → "Usefulness rate" | `user-testing.csv.extraction_useful_flag`, `raw.csv.extraction_usefulness_rating` |
| **S6** | Avg time to complete < 8 min | ≤ 480 s | Exec card "Avg time to complete" | `user-testing.csv.completion_time_sec` |
| **S7** | Zero critical production errors | 0 | Exec card "Critical errors" + Tech health section | `user-testing.csv.critical_error_flag`, `raw.csv.sentry_error_count` |
| **S8** | Qualtrics sync reliability > 95% | ≥ 0.95 | Qualtrics sync section | `user-testing.csv.qualtrics_sync_success_flag`, `raw.csv.qualtrics_*` |
| **S9** | Facilitators report tool is easy | Qualitative | Facilitator feedback section (admin-entered) | `raw.csv.facilitator_feedback_text`, `raw.csv.facilitator_issue_*` |
| **S10** | > 70% of voice starters finish in voice | ≥ 0.70 | Voice UX → "Voice conversation completion" | `user-testing.csv.voice_conversation_completed_flag` |

## Hypotheses → dashboard evidence

| # | Hypothesis | Dashboard evidence | Per-submission flag |
| --- | --- | --- | --- |
| **H1** | Voice is more detailed than text | Voice vs Text: avg word count grouped bars | `h1_voice_more_detailed_support_flag` |
| **H2** | Follow-ups meaningfully improve quality | Follow-up effectiveness: before/after bars + top prompts | `h2_followups_improve_quality_support_flag` |
| **H3** | Participants complete without drop-off | Funnel + Friction sections | `h3_completion_success_flag` |
| **H4** | Extractions are accurate and useful | Extraction quality + review table | `h4_extraction_useful_support_flag` |
| **H5** | Voice conversation feels natural | Voice UX: transitions, switch-away rate | `h5_voice_natural_support_flag` |
| **H6** | Government-managed devices can run it | Tech health: browser / mic / error breakdowns | `h6_device_compatibility_support_flag` |

## Go / no-go decision guide

Run `/admin/user-testing` on the morning of May 5. Decision tree:

1. **S7 = 0 critical errors?** If no → **Do not launch more broadly.** Export
   `raw.csv`, pivot on `critical_error_flag`, and ship the failing submissions
   to engineering.
2. **S1 ≥ 0.75?** If no → investigate Friction (abandonment by step) before
   expanding cohorts.
3. **S5 ≥ 0.80?** If no → improve extraction prompt before using results in
   program reports.
4. **S8 ≥ 0.90?** If no → re-run failed syncs from the Qualtrics sync section;
   do not export Qualtrics-joined datasets until fixed.
5. **S10 + S5 both green?** → Ready for broader rollout.

## Data-quality checks before every standup

- All three CSVs regenerate without errors: `POST /v1/admin/exports/*`.
- The exec card numbers on `/admin/user-testing` match the corresponding
  `user-testing.csv` column sums (spot-check 2-3 metrics).
- At least one extraction reviewed per cohort in the last 24 h
  (Extraction quality → review coverage).
- Facilitator feedback captured for every cohort that ran a session.

## What to do if a metric disagrees between dashboard and export

1. Check `apps/api/app/services/metrics_service.py` — dashboard and exports
   must both call `compute_user_testing_metrics` / `compute_submission_rollup`.
2. Run `python -m pytest apps/api/tests/`. If tests pass but numbers still
   differ, the caller is the problem, not the service.
3. Do not patch the dashboard in isolation.
