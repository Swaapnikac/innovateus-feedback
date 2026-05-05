# InnovateUS Voice Feedback Tool — Bug Tracker

**Last updated:** 2026-04-21
**Launch target:** 2026-05-04 (Monday)
**Owner:** Swaapnika (documentation) · Punith, Ani, Dhruv (engineering)

This tracker records every defect found, fixed, or still pending for the voice-based feedback tool. It is the single source of truth for release readiness and is referenced by the Launch Plan (`InnovateUS_Launch_Plan.md`, task C1).

---

## Conventions

| Field | Values |
| :---- | :---- |
| **Severity** | `Critical` — blocks use, data loss, security breach · `High` — major feature broken or incorrect data · `Medium` — degraded UX, recoverable · `Low` — minor UX / cosmetic |
| **Status** | `Fixed` · `Open` · `In Progress` · `Deferred` · `Won't Fix` |
| **Area** | Survey Flow · Follow-ups · Voice/Transcription · AI · Dashboard/Metrics · Exports · Editor · Auth · Data Integrity · Deployment · Integrations · Security · Infrastructure |

---

## 1. Summary

| Metric | Count |
| :---- | :---- |
| Fixed bugs tracked | **35** |
| Open / planned items | **11** |
| Critical still open | **0 product** · **6 security-hardening** (scheduled Apr 28–30) |
| Deferred / post-launch | **3** |

---

## 2. Fixed Bugs

### 2a. Survey Flow

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-001 | High | Question order reshuffled on navigation | Questions with `randomize: true` groups were re-randomized every time the user hit *Review* or went back, leading to inconsistent ordering and lost answer mapping. Now question order is cached in `sessionStorage` (`question_data`, `question_order`) on first load. | `fe1dc79` | 2026-04-14 |
| BUG-002 | High | "Already submitted" error on same tab | Within one browser tab a second attempt was treated as a duplicate because session/submission state was not reset on the consent page. Consent page now clears `sessionStorage` on fresh visit. | `fe1dc79` | 2026-04-14 |
| BUG-003 | Medium | Next button stuck unnecessarily | The *Next* button blocked advancement during intermediate states (e.g., vagueness check running) even when no recording was active. Now only disabled when a voice recording is actually in progress. | `fe1dc79` | 2026-04-14 |
| BUG-004 | Medium | Conditional-order questions displayed out of sequence | Randomization could place a conditional question before its dependency. Added `_fix_conditional_order()` pass after group shuffle to re-sort. | `f4205fa` | 2026-03-16 |

### 2b. Follow-Up Questions

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-005 | Critical | Follow-up answers lost on interruption | Follow-up answers were only saved on the final `complete` call, so navigation, refresh, or network hiccups lost them. Now each follow-up answer is persisted immediately on submit. | `fe1dc79` | 2026-04-14 |
| BUG-006 | High | No second follow-up when first was still vague | Only a single follow-up was ever asked, even if the first follow-up answer was also vague. Now if Followup 1 is still vague, a Followup 2 is generated on the fly. | `fe1dc79` | 2026-04-14 |
| BUG-007 | High | Edit-from-review broke follow-up context | Editing an answer from the review page reset the follow-up chain. Now the full follow-up conversation is preserved and editable inline. | `fe1dc79` | 2026-04-14 |

### 2c. AI / Latency

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-008 | High | Vagueness + follow-up latency ~3s (perceived hang) | Vagueness detection and follow-up generation were sequential OpenAI calls. Combined into single `gpt-4.1-mini` call via `vagueness_with_followups.txt` prompt and new `/v1/ai/check` endpoint. Latency ~1.5s (~2x faster). | `fe1dc79` | 2026-04-14 |
| BUG-009 | Medium | `vagueness_score` could return NaN / None | Model occasionally returned malformed scores; downstream logic crashed. Added coercion (defaults: 0.7 if vague, 0.1 if not vague) and null-safe handling. | `44ce526` | 2026-04-17 |
| BUG-010 | Medium | AI extraction silent failure wiped results | On API error the empty extraction response was being persisted as a success. Now errors are logged with `success_flag=False` + `error_message` on the `Extraction` row; submission still completes. | `fe1dc79` | 2026-04-14 |

### 2d. Voice / Transcription

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-011 | Medium | Recording never auto-stopped on long silence | No idle timeout — users sat staring at a recording bar. Added 15 s silence timeout that auto-stops and tags the event as `silence_timeout`. | `ddfb621` | 2026-03-11 |
| BUG-012 | Medium | Transcript edits not tracked | `transcript_edit_distance` / `user_edited_transcript_flag` were never populated, so H5 (voice naturalness) signal was missing. Now Levenshtein distance (capped at 2000 chars) is computed and stored. | `fe1dc79` | 2026-04-14 |

### 2e. Data Integrity

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-013 | Critical | Cohort creation silently failed | Cohort rows were not committed to the database; dashboard showed nothing. Added proper commit + refresh in editor route. | `fe1dc79` | 2026-04-14 |
| BUG-014 | Critical | Delete responses did not persist | Bulk delete call returned success but rows remained. Transaction was rolled back due to FK cascade mis-config; fixed cascade on `Answer`, `Extraction`, `Event`. | `fe1dc79` | 2026-04-14 |
| BUG-015 | High | Experience-rating submission lost | POST to `/v1/submissions/{id}/experience-rating` returned 200 but never wrote. Fixed async session commit. | `fe1dc79` | 2026-04-14 |
| BUG-016 | High | Orphan events survived response deletion | After "Delete all responses" the `events` table kept rows linked to deleted submissions, skewing the funnel. Delete now cascades to tracking/events. | `fe1dc79` | 2026-04-14 |
| BUG-017 | High | None-type crashes in analytics aggregation | Several dashboard endpoints returned `None` for aggregate queries with zero rows and then raised when front-end tried to divide. Added null-safe returns across `admin.py`, `metrics_service.py`, `events.py`, `editor.py`, `submissions.py`. | `44ce526` | 2026-04-17 |
| BUG-018 | High | Timestamp timezone corruption | `created_at` / `completed_at` were being saved naive-UTC in some paths and tz-aware in others, breaking date-range filters. Added Alembic migration `004_fix_timestamp_tz.py` to normalize columns. | `068ac61` | 2026-04-17 |
| BUG-019 | Medium | Alembic migration 007 failed on re-run | Migration attempted to add a column that already existed on some environments. Made migration idempotent. | `eeb773c` | 2026-03-31 |

### 2f. Dashboard & Metrics

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-020 | High | Visitor count double-counted | Page-view events were being counted twice (once on mount, once on route change). Deduped via session token. | `fe1dc79` | 2026-04-14 |
| BUG-021 | High | "In progress" count wrong | Submissions in `started` state were being classified as completed due to stale status cache. Fixed status derivation in `metrics_service.compute_*`. | `fe1dc79` | 2026-04-14 |
| BUG-022 | High | Metrics sub-queries ignored cohort/date/version filters | `/v1/admin/metrics` aggregate queries applied filters only at the top level, not in sub-queries for voice/vagueness. Now all filters propagate uniformly. | `8cc1b38` | 2026-03-20 |
| BUG-023 | Medium | Summary charts (themes, barriers, success stories) only showed first page of responses | Aggregation was being run on the paginated response set instead of the full filtered set. Switched to full-cohort aggregation. | `fe1dc79` | 2026-04-14 |

### 2g. Exports

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-024 | High | CSV exports showed wrong course name | Export used cohort ID where course_name was expected. Fixed column mapping in `export_service.py`. | `fe1dc79` | 2026-04-14 |
| BUG-025 | High | Voice-vs-text counts inconsistent between dashboard and CSV | Dashboard used event-based count, CSV used per-answer `input_mode`. Both now use `metrics_service` as single source of truth. | `fe1dc79` | 2026-04-14 |
| BUG-026 | Medium | Export download button broken in browser | Download used `window.open` which was blocked by popup blockers. Switched to `<a download>` approach with token query param. | `67e8674` | 2026-04-06 |
| BUG-027 | Medium | Multi-select Q4 answers not syncing to Qualtrics | Qualtrics payload used `QID_TEXT` for multi-select; should use embedded-data field. Fixed `qualtrics_service._build_payload`. | `7a73fbe` | 2026-03-31 |
| BUG-028 | Medium | Qualtrics embedded data sent in wrong envelope | Payload sent `embeddedData` key; Qualtrics API expects values inline. Restructured request. | `88b80d5` | 2026-03-31 |

### 2h. Auth / Security

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-029 | Critical | Cross-origin auth broken in production | Same-site cookie defaults blocked Bearer/Cookie auth across the Render frontend ↔ backend domains. Now sends JWT as `Authorization: Bearer` header AND sets cookie `SameSite=None; Secure` in production. | `8195995` | 2026-03-18 |
| BUG-030 | High | Stale admin cookie blocked survey access after "Delete all responses" | Cookie still referenced deleted submission ID causing 404 on survey start. Clear stale cookies on response deletion. | `c631c1d` | 2026-03-18 |
| BUG-031 | Medium | `require_editor` rejected admin role | Admins (higher privilege) were being rejected from editor routes. Fixed dependency to accept both `admin` and `editor`. | `714db5b` | 2026-04-06 |
| BUG-032 | Low | CORS origins list broken on whitespace after comma | `CORS_ORIGINS="http://a, http://b"` produced a literal `" http://b"` origin. Added `.strip()` on split. | `40221ce` | 2026-03-25 |

### 2i. Deployment / Infrastructure

| ID | Severity | Title | Description | Fix Commit | Date |
| :---- | :---- | :---- | :---- | :---- | :---- |
| BUG-033 | High | SQLAlchemy incompatible with Render's Python 3.12 default | Build failed on Render due to Python 3.12 / SQLAlchemy async driver mismatch. Pinned `PYTHON_VERSION=3.11.6`. | `d2e5f02` | 2026-03-18 |
| BUG-034 | Medium | `seed.py` could not find survey config on Render | Path resolution used relative path that worked locally but not in Render's build context. Switched to absolute path resolution. | `15a8bdd` | 2026-03-18 |
| BUG-035 | Medium | DynamoDB scan `Limit` parameter mis-used (legacy path) | `Limit` was interpreted as page size instead of total cap; resulted in partial scans. Fixed pagination logic. *Kept for historical reference; not on hot path since PostgreSQL migration.* | `7c95239` | 2026-04-06 |

---

## 3. Open / Planned Items (Pre-Launch)

These are scheduled before the May 4 launch and are tracked as work items in the Launch Plan.

### 3a. Security Hardening (CRITICAL — blocks launch)

| ID | Severity | Area | Title | Description | Target | Owner | Ref |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| OPEN-001 | Critical | Security | Credential rotation | Rotate all API keys (OpenAI, JWT secret, admin/editor password hashes), store in AWS secrets management. | 2026-04-30 | Dhruv | C5 |
| OPEN-002 | Critical | Security | Enforce HTTPS | HTTP→HTTPS redirect at ALB; HSTS header. | 2026-04-29 | Dhruv | C6 |
| OPEN-003 | Critical | Security | API rate limiting | Per-endpoint rate limits on public `/v1/submissions/*`, `/v1/ai/*`, `/v1/transcribe`. Prevent abuse + cost blow-up on OpenAI. | 2026-04-29 | Ani | C7 |
| OPEN-004 | Critical | Security | Security headers middleware | CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy on FastAPI + Next.js. | 2026-04-29 | Ani | C8 |
| OPEN-005 | Critical | Security | Session cookie attributes | Ensure `Secure`, `HttpOnly`, `SameSite=None` for production; `Lax` for dev. | 2026-04-29 | Ani | C8 |
| OPEN-006 | Critical | Security | Input validation hardening | Enforce audio file type / size limits (currently 10 MB, need to confirm), text length caps on all answer endpoints, reject non-whitelisted MIME types on `/v1/transcribe`. | 2026-04-30 | Ani | C10 |

### 3b. Product / Quality

| ID | Severity | Area | Title | Description | Target | Owner | Ref |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| OPEN-007 | High | Infrastructure | AWS migration | Full migration off Render to AWS (compute, RDS Postgres, secrets). Currently running on Render free tier. | 2026-04-30 | Dhruv, Ani | C4 |
| OPEN-008 | High | Quality | Full E2E walkthrough on production AWS | Complete voice + text survey path, all 4 dashboards, all 3 exports. | 2026-05-01 | Swaapnika | C11 |
| OPEN-009 | High | Quality | Fix issues from internal testing (Apr 22–25) | Placeholder — bugs found by Beth, David, and internal team during internal launch will be logged here as BUG-036+. | 2026-04-28 → 05-02 | Punith, Swaapnika | C12 |
| OPEN-010 | Medium | Operations | Error tracking (Sentry) | Wire Sentry SDK into FastAPI + Next.js. Front-end SDK appears installed (`sentry_sdk` seen in venv) but not initialized. | 2026-05-01 | Ani | I1 |
| OPEN-011 | Medium | Quality | Volume / load test | 50–100 concurrent users on AWS; verify latency + OpenAI cost ceiling. | 2026-05-01 | Ani | I4 |

---

## 4. Known Limitations (not bugs — explicit design choices)

| ID | Area | Item | Rationale |
| :---- | :---- | :---- | :---- |
| KNOWN-001 | PII | Regex-only PII stripping (SSN / email / phone) | NLP-based PII detection is on the post-launch roadmap (Sprint 4, June 22 – July 3). Current regex covers the common patterns with no false-positive cost. |
| KNOWN-002 | i18n | English only (Spanish strings exist in README but unused) | next-intl is configured; `messages/en.json` is the only translation file. Multi-language is in Sprint 3 (June 8 – 19). |
| KNOWN-003 | Voice fallback | Whisper fallback only triggers if Web Speech API produces no transcript | Intentional — avoids double-billing OpenAI Whisper when browser-native recognition already succeeds. |
| KNOWN-004 | DynamoDB code | `dynamo.py`, `create_tables.py`, etc. are unused on hot path | Kept for optional AWS Lambda deployment variant. Not wired into `main.py` — safe to remove if Lambda path is abandoned. |
| KNOWN-005 | Facilitator feedback | Single record per cohort (overwrites on resave) | By design — one facilitator note per cohort per session is enough for soft launch. |

---

## 5. Deferred / Post-Launch

| ID | Area | Title | Target Sprint |
| :---- | :---- | :---- | :---- |
| DEF-001 | Voice UX | Accent / dialect handling improvements | Sprint 3 (Jun 8–19) |
| DEF-002 | Quality | CI/CD pipeline with automated E2E on every PR | Sprint 4 (Jun 22 – Jul 3) |
| DEF-003 | Privacy | NLP-based PII detection (replaces regex) | Sprint 4 (Jun 22 – Jul 3) |

---

## 6. Change Log

| Date | Change | Author |
| :---- | :---- | :---- |
| 2026-04-21 | Initial bug tracker created — consolidated fixes from commits `af303e1` (initial) through `44ce526` (latest on `render` branch). | Swaapnika |

---

## 7. How to Add a New Bug

1. Assign the next sequential `BUG-0XX` ID.
2. Place it under the correct area subsection (Survey Flow, AI, etc.).
3. Fill in severity, short title, one-paragraph description, fix commit hash (once fixed), and date.
4. If the bug came from internal testing (Apr 22–25) or production, note the source in the description.
5. Update the summary counts in Section 1.
