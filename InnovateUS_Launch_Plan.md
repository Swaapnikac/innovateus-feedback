# Public Voice Product Launch Plan

**Target Launch Date:** May 4, 2026 (Monday)
**Launch Window:** May 4 - May 18, 2026 (2-week soft launch)
**Document Version:** 2.0 (launch date updated from April 22)

---

## Why the Launch Date Moved

The original April 22 launch was postponed to May 4 to accommodate a significant body of bug fixes, stability improvements, and major new features that emerged during testing. Rather than launch a buggy product, we chose to take two extra weeks to ship a tool that actually works reliably and includes the measurement infrastructure we need to learn from the soft launch.

The delay also creates space for an **internal testing phase with the InnovateUS team (April 22-25)** before external launch — giving us real feedback from the people closest to the product before participants ever see it.

---

## Launch Milestones

| Milestone | Target Date | Description | Check in |
| :---- | :---- | :---- | :---- |
| M1 - Bug Fixes & Core Improvements Complete | April 18 | All critical bug fixes, follow-up overhaul, AI speed improvements, dashboard fixes | Ani, Punith |
| M2 - Major New Features Complete | April 18 | User Testing dashboard, expanded survey editor, enhanced main dashboard, new tracking, pre-submit review | Ani, Punith |
| M3 - Internal Testing Launch | April 22 | Product + Google Form shared with InnovateUS internal team for feedback | Beth, David, Ani |
| M4 - Internal Feedback Collected | April 25 | Feedback reviewed; any critical issues identified for fixing | Beth, David, Ani |
| M5 - AWS Migration Complete | April 30 | Application fully deployed and running on AWS with production database | Dhruv, Ani |
| M6 - Security Hardening Complete | May 1 | HTTPS, rate limiting, PII stripping, credential rotation, security headers, input validation | Ani, Dhruv |
| M7 - Testing & QA Complete | May 2 | E2E walkthrough on AWS and all bug fixes done | Ani, Dhruv |
| M8 - Code Freeze & Sign-Off | May 2 | Demo on production; approval to proceed; no new features after this date | Beth, David, Ani, Dhruv |
| M9 - Go / No-Go Decision | May 3 | Team reviews launch readiness checklist; final launch call | Beth, David, Ani, Dhruv |
| M10 - LAUNCH | May 4 | Product goes live for soft launch cohort | Beth, David, Ani, Dhruv |

---

## 1. Executive Summary

The InnovateUS Voice-Based Feedback Tool is a privacy-first, AI-enhanced feedback platform designed for government training programs. It enables participants to provide feedback via voice or text, uses AI to detect vague responses and generate targeted follow-ups, and automatically extracts structured insights for program managers.

### Current State (as of April 21)

The product is a complete, working feedback platform. Here's everything it does today:

**Participant Experience**
- Anonymous survey flow with consent screen and plain-language privacy disclosures
- Voice-to-text recording using OpenAI Whisper with live transcript preview in the browser
- Text input always available as an alternative for every open-ended question
- AI-powered vagueness detection on open-ended answers
- Up to 2 AI-generated follow-up questions per vague answer, targeted at missing information
- On-the-fly second follow-up if the first follow-up answer is still vague
- Pre-submit "What We Heard" review screen — participants see all responses, can edit any answer before submitting
- Conditional question logic — questions can depend on previous answers
- Question group randomization with dependency preservation
- Ballot-box stuffing protection via salted IP hashing with configurable per-program limits

**Manager Dashboard**
- Real-time metrics (total submissions, completion rate, average time, average recommendation score)
- Response filters by cohort, date range, and survey version
- Paginated response table with full answer details, follow-ups, and extracted insights
- Per-question stat cards with appropriate chart types for each question type
- AI-written summary of responses (top topics, sentiment, recommendations)
- Side-by-side cohort comparison with AI-generated wins / risks / recommendations
- Create new cohort from a dialog with shareable link and QR code
- Duplicate, delete, or reconfigure cohorts
- Adjust per-visitor submission limits

**User Testing Dashboard** (dedicated page for the soft launch)
- Funnel chart (visited → started → finished)
- Voice vs. text usage comparison
- How much follow-ups improve answer specificity
- Drop-off points
- Voice experience details (recording length, voice↔text switches, transcript edits)
- Technical health (browsers, OS, devices, response times, errors)
- Extraction quality with space for manual human review
- Participant feedback and facilitator notes
- Everything filterable by cohort and date

**Survey Editor**
- 12 question types: rating, multiple choice, checkboxes, open-ended, NPS, slider, matrix grid, ranking, yes/no, dropdown, short text, date
- Drag-and-drop question reordering
- Question grouping with randomization within groups
- "Generate a survey for me" AI feature — describe the goal, AI drafts the full survey
- Live preview while editing
- Version history — every save creates an immutable snapshot with one-click restore

**AI & Data Processing**
- Structured insight extraction on every submission — themes, barriers, enablers, planned workflows, success stories
- PII stripping on voice transcriptions (emails, phone numbers, SSN patterns removed before storage)
- Combined vagueness detection + follow-up generation in a single AI call (~1.5s latency, ~2x faster than before)
- De-identified success story candidates surfaced for use in reports

**Exports & Reports**
- Raw CSV export (one row per person, every question as columns)
- Structured CSV export (one row per question answered)
- User-Testing CSV export (every soft-launch metric per participant)
- PDF summary report (charts, metrics, key findings)
- PowerPoint deck (7 slides, presentation-ready for leadership briefings)

**Anonymous Tracking Infrastructure**
Captures (with no personal info): browser/OS/device, app response times, microphone permission status, recording start/stop events, transcript edits, voice↔text switches, browser errors — all for measuring the soft launch

**Access Control & Roles**
- Separate Admin and Editor roles with JWT authentication
- Program type field on each cohort (Course or Workshop)
- Admin can view and edit each follow-up answer inline with voice-or-text toggle

**Quality & Reliability**
- Automated tests that prevent silent regressions in metrics and exports
- Fast admin dashboard (made hundreds of database requests before; now just a few)
- Every follow-up answer saved the moment it's finished
- Edit-from-review preserves existing follow-up conversations instead of wiping them

### What's Still Needed for Launch

- **Internal testing** - Share with InnovateUS internal team for feedback (April 22-25)
- **AWS migration** - Move from development environment to production AWS infrastructure (April 21 - April 30)
- **Security hardening** - Credential rotation, HTTPS, rate limiting, PII stripping enforcement, security headers
- **Final testing on production** - E2E walkthrough, volume testing
- **Documentation** - Demo video, deployment runbook, facilitator instructions

### Why May 4 (Monday)?

- Gives us a full 2-week runway for AWS migration and security hardening on a real production environment
- Incorporates internal feedback from InnovateUS team before external launch
- Monday launch gives the team the full week to respond to any production issues
- Still lands two weeks of soft launch data (May 4 - May 18) before the mid-May data report deadline

---

## 2. What's New Since the Last Plan

### Bug Fixes - Survey Behavior

- **Questions stay in order** - Previously they got reshuffled every time someone clicked "Review" or went back. Fixed.
- **Each visit is a fresh start** - If someone filled out the survey twice in the same browser tab, the system thought it was the same person. Fixed.
- **Next button unblocked** - Was getting stuck for no reason. Now it only blocks when a voice recording is actually in progress.

### Follow-Up Question Overhaul

- Every follow-up answer is saved immediately (previously could get lost)
- If a first follow-up answer is still vague, the system now asks a second clarifying question on the fly
- Follow-up answers can be edited from the review page without starting over

### AI Performance

- Vagueness detection + follow-up generation combined into a single AI call
- Latency dropped from ~3 seconds to ~1.5 seconds (roughly 2x faster)

### Data Integrity Fixes

- Several actions (creating a cohort, deleting responses, saving ratings) weren't saving to the database properly - fixed
- Deleting all responses now cleans up tracking data too (was leaving orphan data that broke the funnel chart)
- Admin dashboard no longer double-counts visitors or miscounts "in progress" surveys
- CSV exports now show the correct course name and voice vs. text counts
- Summary charts (themes, barriers, success stories) now include everyone's responses, not just the first page

### Major New Features

**New "User Testing" Dashboard Page**
A dedicated dashboard page built specifically for measuring the soft launch:
- Funnel chart (visited → started → finished)
- Voice vs. text usage comparison
- How much follow-up questions actually helped answers get more specific
- Drop-off points
- Voice experience details (recording length, voice↔text switches, transcript edits)
- Technical health (browsers, OS, devices, response times, errors)
- Extraction quality (with space for manual human review)
- Participant feedback and facilitator notes
- Everything filterable by cohort and date

**Expanded Survey Editor**
- 12 question types (up from 4): rating, multiple choice, checkboxes, open-ended, NPS, slider, matrix grid, ranking, yes/no, dropdown, short text, date
- Drag-and-drop reordering
- Question grouping + randomization within groups
- "Generate a survey for me" AI feature - describe the goal, AI drafts the full survey
- Live preview while editing
- Version history with one-click restore

**Enhanced Main Dashboard**
- Filters by program, survey, time period, version
- Per-question stat cards with the right chart type
- AI-written summary of responses (top topics, sentiment, recommendations)
- Side-by-side cohort comparison with AI-generated wins/risks/recommendations
- New cohort creation with shareable link + QR code
- Duplicate / delete cohorts, adjust per-visitor submission limits

**Three Export Formats**
- Raw CSV (one row per person, all questions as columns)
- Structured CSV (one row per question answered)
- **New: User-Testing CSV** with every soft launch metric per participant

**New Anonymous Tracking**
Captures (with no personal info): browser/OS/device, app response times, microphone permission status, recording start/stop events, transcript edits, voice↔text switches, browser errors

**AI Instruction Improvements**
- More generous vagueness detection (one specific detail is enough)
- Doesn't push people who say "nothing" or "not sure"
- Never asks for personal info
- Never just repeats the original question back

**Behind-the-Scenes**
- Two new database migrations for tracking data
- New "program type" field (Course vs. Workshop)
- Automated tests to prevent silent regressions

---

## 3. Prioritized Work Items (Remaining Before Launch)

### CRITICAL - Must Complete Before Launch

| # | Category | Task | Description |
| :---- | :---- | :---- | :---- |
| C1 | Documentation | Update Bug Tracker, Launch Plan, Decide Post-Survey Questions | Refresh all docs to reflect current state; finalize the 4 tool-feedback questions to ask participants after the survey |
| C2 | Internal Testing | Share with InnovateUS Internal Team | Distribute survey link + Google Form for feedback to Beth, David, and other internal stakeholders |
| C3 | Internal Testing | Collect & Review Internal Feedback | Document feedback, prioritize, identify any critical fixes needed before external launch |
| C4 | Infrastructure | AWS Setup & Migration | Complete cloud infrastructure setup, deploy backend and frontend, migrate database, verify all services running in production |
| C5 | Security | Credential Rotation & Hardening | Rotate all API keys, generate strong JWT secret, set strong admin/editor passwords, configure AWS secrets management |
| C6 | Security | HTTPS & Transport Security | Enforce encrypted connections for all traffic; HTTP-to-HTTPS redirect |
| C7 | Security | API Rate Limiting | Per-endpoint rate limits on public-facing APIs |
| C8 | Security | Security Headers | CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| C9 | Security | PII Stripping Service | Automated PII detection and removal for voice transcriptions |
| C10 | Security | Input Validation | Audio file type/size limits; text length limits |
| C11 | Quality | Full E2E Walkthrough on AWS | Complete user journey testing on production environment |
| C12 | Quality | Fix Critical Issues from Internal Testing | Address blocking issues identified during April 22-25 internal testing |
| C13 | Documentation | Demo Video | 2-3 minute polished video for facilitator training |
| C14 | Documentation | Facilitator Briefing Materials | Instruction sheet, survey links, demo video, technical contact |
| C15 | Documentation | Launch Communications | Email templates, rollout plan for external cohorts |

### IMPORTANT - Should Complete

| # | Category | Task | Description |
| :---- | :---- | :---- | :---- |
| I1 | Operations | Error Tracking (Sentry) | Configure real-time error monitoring for frontend + backend |
| I2 | Operations | Production Monitoring & Alerts | Alerts for API error rates, response latency, database performance |
| I3 | Operations | Database Backup Configuration | Daily backups, 7-day retention, tested restore process |
| I4 | Quality | Volume/Load Testing | Simulate 50-100 concurrent users on AWS |
| I5 | Documentation | Deployment Runbook | Deploy + rollback procedures, log locations, escalation contacts |

---

## 4. Day-by-Day Schedule

### WEEK 1: April 21-25 — Documentation Refresh, Internal Testing, AWS Migration Begins

**Goal:** Update all project documentation, get the product in front of the InnovateUS internal team for real feedback, and begin AWS migration work in parallel.

#### April 21 (Monday) — Documentation Refresh + AWS Migration Begins

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Update bug tracker with all fixes completed April 7-18 | Documentation | Swaapnika | |
| 2 | Update launch plan to reflect new May 4 timeline and completed work | Documentation | Swaapnika | |
| 3 | Decide and finalize the 4 post-survey questions to ask participants about the tool | Content | Swaapnika | |
| 4 | Create Google Form for internal feedback collection (tool experience, bugs, suggestions) | Content | Swaapnika | |
| 5 | Begin AWS migration work - provisioning, initial infrastructure setup | Infrastructure | Dhruv | |

#### April 22 (Tuesday) — Internal Launch + AWS Migration Continues

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | **Share product link with InnovateUS internal team** | Launch Prep | Swaapnika | |
| 2 | Distribute Google Form alongside the survey link for tool-feedback collection | Launch Prep | Swaapnika | |
| 3 | Post short walkthrough / instructions for internal testers | Communication | Swaapnika | |
| 4 | Continue AWS infrastructure setup | Infrastructure | Dhruv | |
| 5 | Monitor early internal responses and note any blockers | Monitoring | Swaapnika | |

**MILESTONE M3: Internal Testing Launch** ✓

#### April 23 (Wednesday) — Internal Testing Observation + AWS

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Review internal testers' submissions on the User Testing dashboard | Monitoring | Swaapnika | |
| 2 | Review Google Form responses as they come in | Feedback | Swaapnika | |
| 3 | Note any bugs or confusing flows that internal testers encounter | Quality | Swaapnika | |
| 4 | Continue AWS migration - compute, database, networking | Infrastructure | Dhruv | |

#### April 24 (Thursday) — Mid-Week Feedback Review + AWS

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Mid-week internal feedback sync with Beth/David/team | Stakeholder | Swaapnika | |
| 2 | Prioritize fixes needed before external launch | Quality | Swaapnika | |
| 3 | Begin fixing any critical issues identified | Quality | Punith, Swaapnika | |
| 4 | Continue AWS migration work | Infrastructure | Dhruv | |

#### April 25 (Friday) — Feedback Consolidation + AWS Progress Check

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Final internal feedback collection and consolidation | Feedback | Swaapnika | |
| 2 | Document all identified issues in bug tracker | Documentation | Swaapnika | |
| 3 | Continue fixing critical issues | Quality | Punith, Swaapnika | |
| 4 | AWS migration status check with Dhruv - confirm on track for April 30 | Infrastructure | Dhruv | |

**MILESTONE M4: Internal Feedback Collected** ✓

---

### WEEK 2: April 28 - May 2 — AWS Migration Complete, Security Hardening, Final Testing

**Goal:** Finish AWS migration, complete all security hardening, run the full E2E walkthrough on production, get sign-off, and lock code.

#### April 28 (Monday) — AWS Deployment

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Deploy backend to AWS - run database migrations, seed data, verify health check | Infrastructure | Dhruv, Ani | |
| 2 | Deploy frontend to AWS - configure for production domain | Infrastructure | Dhruv, Ani | |
| 3 | Configure AWS secrets management with rotated credentials | Security | Dhruv | |
| 4 | Fix any remaining issues from internal testing feedback | Quality | Punith, Swaapnika | |

#### April 29 (Tuesday) — Security Hardening + API Updates

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Configure production CORS policy - lock to production domain only | Security | Dhruv | |
| 2 | Add API rate limiting on all public endpoints | Security | Ani | |
| 3 | Add security headers middleware (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy) | Security | Ani | |
| 4 | Enforce HTTPS - configure HTTP-to-HTTPS redirect at load balancer | Security | Dhruv | |
| 5 | Fix session cookie security - Secure, HttpOnly, SameSite attributes | Security | Ani | |

#### April 30 (Wednesday) — PII Stripping + Input Validation + Final Hardening

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Deploy PII stripping service to AWS; verify applied automatically to transcripts | Security | Ani | |
| 2 | Deploy input validation - audio file type/size limits; text length limits | Security | Ani | |
| 3 | Improve health check endpoint to verify database connectivity | Quality | Ani | |
| 4 | Codebase cleanup - final check for exposed secrets, debug code | Quality | Swaapnika | |

**MILESTONE M5: AWS Migration Complete** ✓
**MILESTONE M6: Security Hardening Complete** ✓

#### May 1 (Thursday) — Full E2E Walkthrough + Demo Video + Monitoring

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Complete E2E walkthrough on production - voice input + text input | Quality | Swaapnika | |
| 2 | Verify all 4 dashboards (Admin, User Testing, Survey Editor, Dashboard) work on production | Quality | Swaapnika | |
| 3 | Verify all 3 export formats generate correctly from production data | Quality | Swaapnika | |
| 4 | Set up error tracking (Sentry) and production monitoring alerts | Operations | Ani | |
| 5 | Configure automated database backups | Operations | Dhruv | |
| 6 | Record demo video - screen captures + voiceover | Documentation | Swaapnika | |
| 7 | Volume testing on AWS - simulate 50-100 concurrent users | Quality | Ani | |

#### May 2 (Friday) — Documentation, Demo, Code Freeze, Sign-Off

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Edit and finalize demo video | Documentation | Swaapnika | |
| 2 | Write deployment runbook | Documentation | Ani | |
| 3 | Prepare facilitator briefing materials (instructions, survey links, demo video) | Documentation | Swaapnika | |
| 4 | **Final team demo on production** - walk through complete product | Stakeholder | Swaapnika | |
| 5 | Collect any final feedback from demo | Stakeholder | Swaapnika | |
| 6 | Fix only critical blocking feedback | Quality | Punith, Swaapnika | |
| 7 | Prepare launch day communications (email templates, rollout plan) | Documentation | Swaapnika | |

**MILESTONE M7: Testing & QA Complete** ✓
**MILESTONE M8: Code Freeze & Sign-Off** ✓ — No new features after end of day

---

### WEEK 3: May 3-8 — Go/No-Go, Launch, Post-Launch Support

**Goal:** Final verification, launch, and support the first week of production.

#### May 3 (Saturday) — Final Verification + Go/No-Go

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Production smoke test - complete 1 survey with voice input + 1 with text input | Verification | Swaapnika | |
| 2 | Verify error tracking and monitoring alerts are working | Verification | Swaapnika | |
| 3 | Review production logs for any warnings | Verification | Swaapnika | |
| 4 | Final security checklist pass | Security | Ani | |
| 5 | **GO / NO-GO DECISION** - Review launch readiness checklist | Decision | Team | |
| 6 | If GO: notify team, prepare for Monday launch | Launch Prep | Swaapnika | |

**MILESTONE M9: Go / No-Go Decision** ✓

#### May 4 (Monday) — LAUNCH DAY

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Morning production health check | Verification | Swaapnika | |
| 2 | Brief facilitators - share demo video, instruction sheet, survey links | Launch Prep | Swaapnika | |
| 3 | **Enable production traffic - share survey links with participants and facilitators** | Launch | Swaapnika | |
| 4 | Monitor system closely for first 4 hours - error rates, latency, API costs | Monitoring | Swaapnika | |
| 5 | Monitor voice input specifically - transcription accuracy, completion rate, voice adoption | Monitoring | Swaapnika | |
| 6 | Team on standby for critical hotfixes | Support | ALL | |

**MILESTONE M10: LAUNCH** ✓

#### May 5 (Tuesday) — Post-Launch Day 1

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Review overnight metrics and error logs | Monitoring | Swaapnika | |
| 2 | Address any urgent production issues | Support | Punith, Swaapnika | |
| 3 | Check User Testing dashboard - are we hitting the targets? | Monitoring | Swaapnika | |
| 4 | Collect early participant and facilitator feedback | Feedback | Swaapnika | |

#### May 6 (Wednesday) — Post-Launch Day 2

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Continue monitoring production metrics | Monitoring | Swaapnika | |
| 2 | Fix any non-critical issues discovered during first 48 hours | Support | Punith, Swaapnika | |
| 3 | Mid-week check on success criteria trajectory | Reporting | Swaapnika | |
| 4 | Sync with facilitators - are they comfortable with the tool? | Feedback | Swaapnika | |

#### May 7 (Thursday) — Post-Launch Day 3

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Continue monitoring | Monitoring | Swaapnika | |
| 2 | Review extraction quality on first batch of submissions | Quality | Swaapnika, Beth | |
| 3 | Identify any patterns in participant feedback that need addressing | Feedback | Swaapnika | |

#### May 8 (Friday) — Post-Launch Week 1 Wrap

| # | Task | Category | Check in | Status |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Compile Week 1 usage report - submissions, voice vs text, completion rates | Reporting | Swaapnika | |
| 2 | Document lessons learned from first week | Planning | Swaapnika | |
| 3 | Begin planning adjustments for Week 2 of soft launch | Planning | Swaapnika | |

---

### Soft Launch Continuation: May 11 - May 18

Continue monitoring and collecting data through May 18. Begin analysis for mid-May data report.

---

## 5. Go / No-Go Checklist (May 3)

Every item must pass for a GO decision. Any failing item requires a documented mitigation plan or the launch is postponed.

| # | Category | Criterion | Pass? |
| :---- | :---- | :---- | :---- |
| 1 | Security | HTTPS enforced on all traffic | |
| 2 | Security | All API keys and secrets rotated and stored in AWS secrets management | |
| 3 | Security | Strong admin/editor passwords set (not development defaults) | |
| 4 | Security | Rate limiting active on all public-facing API endpoints | |
| 5 | Security | PII stripping working on voice transcriptions | |
| 6 | Security | Security headers present (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) | |
| 7 | Security | CORS locked to production domain only | |
| 8 | Security | Session cookies configured with Secure, HttpOnly, appropriate SameSite | |
| 9 | Infrastructure | Application fully deployed and stable on AWS production | |
| 10 | Infrastructure | Database backups configured and restore tested | |
| 11 | Operations | Error tracking (Sentry) active and receiving events | |
| 12 | Operations | Production monitoring alerts configured and tested | |
| 13 | Feature | Voice input + text input both working end-to-end | |
| 14 | Feature | AI vagueness detection and follow-up questions working reliably | |
| 15 | Feature | Pre-submit "What We Heard" summary with edit capability | |
| 16 | Feature | User Testing dashboard populated and accurate | |
| 17 | Feature | Expanded survey editor working (all 12 question types) | |
| 18 | Quality | All 3 export formats (Raw CSV, Structured CSV, User-Testing CSV) generating correctly | |
| 19 | Quality | Volume tested for 50-100 concurrent users | |
| 20 | Quality | Internal testing feedback addressed | |
| 21 | Documentation | Demo video completed and approved | |
| 22 | Documentation | Deployment runbook written | |
| 23 | Launch Readiness | Facilitators briefed with survey links, instructions, demo video | |
| 24 | Launch Readiness | Post-survey tool feedback questions finalized and integrated | |

---

## 6. Soft Launch Strategy — What We're Testing

This is a soft launch to 1-2 InnovateUS training cohorts (30-75 participants) running May 4 - May 18. The goal is to validate that the product delivers real value, not just that it works technically.

### Hypotheses We're Testing

| # | Hypothesis | How We'll Measure It |
| :---- | :---- | :---- |
| H1 | Voice produces more specific feedback than typing | Average word count: voice >15 words vs. text ~8 words (current survey baseline is ~6 words) |
| H2 | AI follow-ups meaningfully improve response quality | Vagueness rate drops below 30% after follow-ups |
| H3 | Participants complete the survey without confusion | Completion rate >60%; average time <8 minutes |
| H4 | The extracted insights are accurate and useful | >85% of extractions rated "useful" by program managers |
| H5 | The tool runs smoothly on real government devices | No systemic browser/microphone/network failures |

### Success Criteria

| Metric | Target |
| :---- | :---- |
| Survey completion rate | >60% |
| Voice adoption (used for ≥1 open-ended question) | >50% |
| Vagueness rate after follow-ups | <30% |
| Extraction usefulness (manager review) | >85% rated useful |
| Average time to complete | <8 minutes |
| Critical production errors | Zero |
| Facilitator satisfaction | "Easy to deploy" and "better than current process" |

### Post-Survey Feedback Questions (to be asked after the survey)

The final 4 questions will be decided April 21. Working set:

1. **Rating:** Rate your experience with this feedback tool (1-5 stars)
2. **Comparison:** Compared to feedback surveys you've taken before, this was: Much easier / Somewhat easier / About the same / Harder
3. **Follow-ups:** When the tool asked you to elaborate, that felt: Helpful / Fine / Unnecessary / Wasn't asked
4. **Open text:** What's one thing you'd improve about this experience?

### Post-Soft-Launch Decision (by May 18)

- **Success criteria met:** Expand to more InnovateUS cohorts; begin multi-language and polish work
- **Some criteria fail:** Identify root causes, fix, re-test with next cohort
- **Fundamental issues:** Pause wider rollout, reassess approach

---

## 7. Post-Launch Roadmap

| Sprint | Dates | Focus | Key Deliverables |
| :---- | :---- | :---- | :---- |
| Sprint 1 | May 11 - May 22 | Soft launch continuation + immediate improvements | Continue data collection, address urgent issues, mid-launch tuning based on User Testing dashboard signals |
| Sprint 2 | May 25 - June 5 | Data report + first wave of improvements | Mid-May data report published, prioritized improvements from soft launch, facilitator feedback incorporated |
| Sprint 3 | June 8 - June 19 | Voice experience polish | Voice input UX refinements, accent handling improvements, multi-language support (translations + QA) |
| Sprint 4 | June 22 - July 3 | Platform hardening | Comprehensive automated test suite expansion, NLP-based PII detection, CI/CD pipeline |

---

*Public Voice Launch Plan v2.0 — Last updated April 21, 2026. Target launch May 4, 2026.*
