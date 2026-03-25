# InnovateUS Voice Feedback Tool

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3116/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991.svg)](https://openai.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Deploy to Render](https://img.shields.io/badge/deploy-Render-46E3B7.svg)](https://render.com/deploy)

A privacy-first, no-login web check-in that collects post-course feedback for government training programs using **voice-to-text** for open-ended questions, adds bounded **AI follow-ups** when responses are vague, extracts **structured insights** automatically, and provides a **program manager dashboard** with multi-format exports.

**Live Demo** : [innovateus-feedback.onrender.com](https://innovateus-feedback.onrender.com)

---

## Table of Contents

- [What Is This?](#what-is-this)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
  - [Voice Recording and Transcription](#voice-recording-and-transcription)
  - [AI Pipeline](#ai-pipeline)
  - [Survey Editor with Version Control](#survey-editor-with-version-control)
  - [Question Grouping and Randomization](#question-grouping-and-randomization)
  - [Ballot-Box Stuffing Protection](#ballot-box-stuffing-protection)
  - [Manager Dashboard and Exports](#manager-dashboard-and-exports)
  - [Privacy and Security](#privacy-and-security)
- [User Flows](#user-flows)
  - [Participant Flow](#participant-flow)
  - [Admin / Manager Flow](#admin--manager-flow)
  - [Editor Flow](#editor-flow)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Clone and Configure](#1-clone-and-configure)
  - [Local Development](#2-local-development)
  - [Access the Application](#3-access-the-application)
- [Project Structure](#project-structure)
- [Survey Configuration](#survey-configuration)
  - [Question Types](#question-types)
  - [Question Groups](#question-groups)
  - [Conditional Logic](#conditional-logic)
- [AI Prompts](#ai-prompts)
- [API Reference](#api-reference)
  - [Public Endpoints (Participant)](#public-endpoints-participant)
  - [Admin Endpoints (Manager)](#admin-endpoints-manager)
  - [Editor Endpoints](#editor-endpoints)
- [Database Schema](#database-schema)
  - [Models](#models)
  - [Migrations](#migrations)
- [Environment Variables](#environment-variables)
- [Deployment](#deployment)
  - [One-Click Deploy to Render](#one-click-deploy-to-render)
  - [Manual Service Setup](#manual-service-setup)

---

## What Is This?

The **InnovateUS Voice Feedback Tool** is a web application built for government training programs (such as "Generative AI for Government") to collect anonymous post-course feedback from participants. Unlike traditional survey tools, it uses **voice input** as the primary interaction model for open-ended questions, letting respondents speak naturally instead of typing lengthy responses.

When a participant gives a vague answer like "It was helpful," the system uses **OpenAI GPT-4o-mini** to detect the vagueness and generate up to two friendly follow-up questions that coax out specific, actionable details -- what task they plan to do, what barriers they face, or what outcomes they expect. All of this happens transparently within the survey flow.

Upon completion, **GPT-4o** performs structured extraction across all answers, pulling out themes, barriers, enablers, planned workflows, and de-identified success story quotes. Program managers access a password-protected dashboard to view aggregated metrics, filter by cohort/date/survey version, and export results as CSV, PDF, or PowerPoint.

The entire system is **privacy-first**: no participant login, no stored audio, hashed IP addresses, and fully anonymous responses.

---

## Architecture

```mermaid
flowchart TB
    subgraph participant [Participant Browser]
        Landing["Landing Page"]
        Consent["Consent Page"]
        Survey["Survey Page"]
        VR["VoiceRecorder\n(MediaRecorder + Web Speech API)"]
        Done["Done Page\n(What We Heard)"]
    end

    subgraph frontend [Next.js 16 Frontend]
        AppRouter["App Router\n/c/[cohortId]/*\n/admin/*"]
        APIClient["API Client\n(lib/api.ts)"]
    end

    subgraph backend [FastAPI Backend]
        SurveyRouter["Survey Router\n(randomized config)"]
        SubmissionRouter["Submission Router\n(start, answer, complete)"]
        TranscribeRouter["Transcribe Router"]
        AIRouter["AI Router\n(vagueness, followups)"]
        AdminRouter["Admin Router\n(metrics, exports, cohorts)"]
        EditorRouter["Editor Router\n(versioned survey config)"]
    end

    subgraph services [Backend Services]
        AISvc["AI Service\n(GPT-4o / GPT-4o-mini)"]
        TranscribeSvc["Transcribe Service\n(Whisper API)"]
        ExportSvc["Export Service\n(CSV, PDF, PPTX)"]
    end

    subgraph external [External Services]
        OpenAI["OpenAI API"]
        PG["PostgreSQL 16"]
    end

    Landing --> Consent --> Survey --> Done
    Survey --> VR
    VR -->|"audio blob"| APIClient
    Survey -->|"answers"| APIClient

    APIClient -->|"HTTP REST"| SurveyRouter
    APIClient --> SubmissionRouter
    APIClient --> TranscribeRouter
    APIClient --> AIRouter
    APIClient --> AdminRouter
    APIClient --> EditorRouter

    TranscribeRouter --> TranscribeSvc
    AIRouter --> AISvc
    AdminRouter --> ExportSvc
    SubmissionRouter -->|"on complete"| AISvc

    AISvc --> OpenAI
    TranscribeSvc --> OpenAI

    SurveyRouter --> PG
    SubmissionRouter --> PG
    AdminRouter --> PG
    EditorRouter --> PG
```

The application follows a **two-service architecture**:

| Layer | Technology | Location |
|-------|-----------|----------|
| **Frontend** | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui | `apps/web/` |
| **Backend** | FastAPI, Python 3.11, SQLAlchemy 2.0 (async), Alembic | `apps/api/` |
| **Database** | PostgreSQL 16 (asyncpg driver) | Managed or Docker |
| **AI / STT** | OpenAI GPT-4o, GPT-4o-mini, Whisper | External API |

The frontend communicates with the backend exclusively through REST API calls (`/v1/*` endpoints). There are no Next.js API routes; all server logic lives in the FastAPI backend.

---

## Tech Stack

### Frontend

| Technology | Purpose |
|-----------|---------|
| **Next.js 16** | React framework with App Router for file-based routing |
| **React 19** | UI library |
| **TypeScript 5** | Type safety |
| **Tailwind CSS v4** | Utility-first styling via PostCSS plugin |
| **shadcn/ui** | Radix-based accessible component primitives (New York variant) |
| **next-intl** | Internationalization (English locale configured) |
| **next-themes** | Theme management |
| **react-hook-form + zod** | Form validation |
| **sonner** | Toast notifications |
| **lucide-react** | Icon library |

### Backend

| Technology | Purpose |
|-----------|---------|
| **FastAPI 0.115** | Async Python web framework with auto-generated OpenAPI docs |
| **SQLAlchemy 2.0** | Async ORM with mapped column declarations |
| **Alembic 1.13** | Database migration management |
| **asyncpg** | Async PostgreSQL driver |
| **psycopg2-binary** | Sync PostgreSQL driver (used by Alembic) |
| **OpenAI SDK 1.55** | GPT-4o/4o-mini for AI analysis, Whisper for transcription |
| **python-jose** | JWT token creation and verification |
| **passlib + bcrypt** | Password hashing |
| **ReportLab** | PDF report generation |
| **python-pptx** | PowerPoint report generation |
| **pandas** | Data manipulation for CSV exports |
| **pydantic-settings** | Environment variable management |
| **httpx** | Async HTTP client |

---

## Features

### Voice Recording and Transcription

Open-ended questions marked as `voice_eligible` give participants the choice between typing and speaking. The voice recording system works as follows:

1. **MediaRecorder API** captures audio in WebM format in the browser
2. **Web Speech API** provides optional live captions as the user speaks (browser-native, no server call)
3. Recording is **pause-safe** -- it does not stop on silence
4. After **15 seconds of inactivity**, recording auto-finishes to prevent forgotten recordings
5. When recording stops, the system prefers the browser's final speech recognition transcript; if unavailable, the audio blob is sent to the backend's `/v1/transcribe` endpoint which calls **OpenAI Whisper**
6. The participant can **edit the transcript** before submitting their answer
7. **Audio is never persisted** -- it exists only in browser memory and transiently in server memory during Whisper processing. The server never writes audio to disk.

### AI Pipeline

The AI pipeline runs three distinct analyses using prompt templates stored in `docs/prompts/`:

```mermaid
flowchart LR
    Answer["Participant Answer\n(open-ended)"] --> Vagueness
    Vagueness["Vagueness Detection\n(GPT-4o-mini)"]
    Vagueness -->|"is_vague: true"| FollowUp["Follow-Up Generation\n(GPT-4o-mini)"]
    Vagueness -->|"is_vague: false"| Next["Next Question"]
    FollowUp -->|"1-2 questions"| Participant["Participant Answers\nFollow-Ups"]
    Participant --> Next
    Next -->|"survey complete"| Extraction["Structured Extraction\n(GPT-4o)"]
    Extraction --> Summary["What We Heard\nSummary Page"]
```

**Vagueness Detection** (`docs/prompts/vagueness.txt`): Classifies open-ended answers as VAGUE or SPECIFIC. An answer is considered specific if it mentions a concrete task, intended outcome, barrier, or real example. Returns `is_vague` (boolean), `reason`, and `missing_info_types` (array of what's missing: example, context, outcome, barrier, task).

**Follow-Up Generation** (`docs/prompts/followup.txt`): When an answer is vague, generates 1-2 friendly, non-judgmental follow-up questions (each under 18 words) that target the specific missing information types. Follow-ups are skippable by the participant.

**Structured Extraction** (`docs/prompts/extraction.txt`): Runs on survey completion using GPT-4o across all answers (including follow-up responses). Extracts:

| Field | Description |
|-------|-------------|
| `what_was_tried` | What the participant has already tried with GenAI |
| `planned_task_or_workflow` | Specific task or workflow they plan to do |
| `outcome_or_expected_outcome` | Outcomes achieved or expected |
| `barriers` | Array of challenges mentioned |
| `enablers` | Array of things that helped or would help |
| `public_benefit` | How this benefits the public or their agency |
| `top_themes` | 3-6 key themes from responses |
| `success_story_candidate` | De-identified quote suitable for public sharing |

All AI calls degrade gracefully -- if no OpenAI API key is configured, vagueness always returns `false`, follow-ups return empty, and extraction returns null fields.

### Survey Editor with Version Control

The survey editor (`/admin/editor`) provides a visual interface for modifying the survey per cohort:

- **Question editor**: Edit question text, description, type, options, required flag, voice eligibility, group assignment, and conditional logic
- **Drag-to-reorder**: Rearrange questions within the survey
- **Question groups**: Create, rename, and delete groups; toggle per-group randomization
- **Version snapshots**: Every meaningful save creates an immutable versioned snapshot (`v1`, `v2`, `v3`...)
- **Auto-generated change summaries**: Describes what changed -- added/removed questions, text edits, option changes, reordering
- **Duplicate detection**: No new version is created when the config hasn't actually changed
- **One-click restore**: Restoring an old version creates a new forward version (history is never rewritten)
- **Submission stamping**: Each submission records which survey version it was collected against

### Question Grouping and Randomization

Questions are organized into named groups (e.g., "Closed-ended questions" and "Open-ended questions"). Each group has a `randomize` toggle:

- When enabled, the backend shuffles question order within that group on every request, so each respondent sees questions in a different order
- This spreads survey attrition evenly across questions instead of concentrating it on later items
- Server-side shuffling respects conditional dependencies -- questions with `condition` fields always appear after their prerequisite questions regardless of randomization

### Ballot-Box Stuffing Protection

- **IP hashing**: Client IP addresses are hashed with SHA-256 (salted) before storage -- plain IPs are never persisted
- **Configurable limits**: Each cohort has a `max_submissions_per_ip` setting (default: 1, set to 0 for unlimited)
- **Smart counting**: Only completed submissions count toward the limit. Starting and abandoning does not block future attempts
- **Automatic resume**: If a participant returns with an incomplete submission, it resumes that submission instead of creating a duplicate
- **Friendly blocking**: Users who exceed the limit see a "Thank You" page rather than an error

### Manager Dashboard and Exports

The password-protected dashboard (`/admin/dashboard`) provides:

**Metrics** (all respect active cohort / date range / survey version filters):
- Total submissions and completion rate
- Average recommendation score (from `q1_recommend` rating)
- Confidence distribution (from `q2_confidence` MCQ)
- Vagueness rate across open-ended answers

**Aggregated Insights** (computed from AI extractions):
- Top themes across all responses
- Most common barriers
- Success story highlights

**Response Management**:
- Paginated response table with status badges, version stamps, and duplicate IP detection hints
- Create new programs (cohorts) with auto-generated survey links
- Delete all responses with confirmation dialog (scoped to selected program or all)

**Exports** (four formats, all filterable):

| Format | Contents |
|--------|----------|
| **Raw CSV** | One row per respondent, all questions + follow-ups as columns, voice indicator |
| **Structured CSV** | One row per question-answer pair, concatenated follow-up answers |
| **Summary PDF** | Branded report with metrics, top themes, barriers, success stories, planned workflows |
| **Summary PPTX** | Presentation-ready slides: title, metrics, workflows, barriers, stories, themes, recommendations |

### Privacy and Security

| Concern | How It's Handled |
|---------|-----------------|
| **Authentication** | No participant login. Admin and editor use bcrypt-hashed passwords with JWT tokens (HS256, 24-hour expiry) |
| **Audio storage** | Audio exists only in browser memory and transiently in server memory. Never written to disk. |
| **IP privacy** | IPs are SHA-256 hashed with a salt before storage. Plain IPs are never persisted. |
| **Anonymity** | No names, emails, or identifying information collected. Extraction strips any incidentally mentioned PII. |
| **CORS** | Configurable allowed origins via `CORS_ORIGINS` environment variable |
| **Token transport** | JWT sent via `Authorization: Bearer` header or HTTP-only cookies |

---

## User Flows

### Participant Flow

```
GET /                              Landing page (marketing site)
  |
  v
GET /c/{cohortId}                  Consent page
  |  - Privacy notice displayed
  |  - Participant checks consent box
  |  - POST /v1/submissions/start  (creates or resumes submission)
  |  - submission_id stored in sessionStorage
  v
GET /c/{cohortId}/survey           Survey page
  |  - GET /v1/survey/{cohortId}   (loads randomized questions)
  |  - Progress bar shows "Question X of Y"
  |  - Conditional questions shown/hidden based on prior answers
  |  - For each answered question:
  |      POST /v1/submissions/{id}/answer
  |  - For voice-eligible open-ended questions:
  |      1. Record audio (MediaRecorder) or type text
  |      2. POST /v1/transcribe (if browser STT unavailable)
  |      3. POST /v1/ai/vagueness (check answer quality)
  |      4. If vague: POST /v1/ai/followups -> show FollowUpPanel
  |  - POST /v1/submissions/{id}/complete (triggers extraction)
  v
GET /c/{cohortId}/done             Confirmation page
     - "Thank you" message
     - "What We Heard" summary from AI extraction
```

### Admin / Manager Flow

```
GET /admin/login                   Login page
  |  - POST /v1/admin/login        (bcrypt verify -> JWT)
  |  - Token stored in localStorage
  v
GET /admin/dashboard               Dashboard page
     - GET /v1/admin/cohorts       (populate program filter)
     - GET /v1/admin/metrics       (with cohort/date/version filters)
     - GET /v1/admin/responses     (paginated, filtered)
     - POST /v1/admin/cohorts      (create new program)
     - DELETE /v1/admin/responses  (delete responses)
     - GET /v1/admin/export/*      (download CSV/PDF/PPTX)
```

### Editor Flow

```
GET /admin/editor/login            Editor login page
  |  - POST /v1/admin/editor/login (bcrypt verify -> JWT with role:editor)
  v
GET /admin/editor                  Survey editor page
     - GET /v1/admin/cohorts                        (cohort picker)
     - GET /v1/admin/editor/survey/{cohortId}       (load config + active version)
     - PUT /v1/admin/editor/survey/{cohortId}       (save -> auto-version)
     - GET .../versions                              (version history)
     - POST .../versions/{label}/restore             (restore old version)
     - POST /v1/admin/cohorts/{id}/settings          (update max submissions per IP)
```

---

## Quick Start

### Prerequisites

- **Node.js** 20+
- **Python** 3.11+
- **PostgreSQL** 16 (or Docker to run it)
- **OpenAI API key** (for AI features and Whisper transcription)

### 1. Clone and Configure

```bash
git clone https://github.com/Swaapnikac/innovateus-feedback.git
cd innovateus-feedback
cp .env.example .env
```

Edit `.env` and fill in your values. To generate password hashes:

```bash
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-admin-password'))"
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-editor-password'))"
```

### 2. Local Development

**Start PostgreSQL** (if not already running):

```bash
docker run -d --name innovateus-db -p 5432:5432 \
  -e POSTGRES_DB=innovateus -e POSTGRES_PASSWORD=postgres \
  postgres:16-alpine
```

**Start the backend:**

```bash
cd apps/api
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pip install -r requirements.txt

alembic upgrade head    # Run database migrations
python seed.py          # Seed the default "Pilot Cohort 1" program

uvicorn app.main:app --reload --port 8000
```

**Start the frontend** (in a separate terminal):

```bash
cd apps/web
npm install
npm run dev
```

### 3. Access the Application

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Landing page |
| http://localhost:3000/c/00000000-0000-0000-0000-000000000001 | Participant survey (default cohort) |
| http://localhost:3000/admin/login | Manager dashboard login |
| http://localhost:3000/admin/editor/login | Survey editor login |
| http://localhost:8000/docs | Interactive API documentation (Swagger UI) |
| http://localhost:8000/health | Health check endpoint |

---

## Project Structure

```
innovateus-feedback/
├── .env.example                    # Environment variable template
├── render.yaml                     # Render deployment blueprint (Postgres + API + Web)
│
├── docs/
│   ├── prompts/
│   │   ├── vagueness.txt           # GPT prompt: classify answer as vague or specific
│   │   ├── followup.txt            # GPT prompt: generate follow-up questions
│   │   └── extraction.txt          # GPT prompt: extract structured insights
│   └── survey-config/
│       └── survey-en.json          # Default survey definition (9 questions, 2 groups)
│
├── apps/
│   ├── api/                        # ── FastAPI Backend ──
│   │   ├── requirements.txt        # Python dependencies
│   │   ├── seed.py                 # Seeds default cohort on first run
│   │   ├── alembic.ini             # Alembic configuration
│   │   ├── alembic/
│   │   │   ├── env.py              # Migration environment (reads DATABASE_URL)
│   │   │   └── versions/
│   │   │       ├── 001_initial_schema.py
│   │   │       ├── 002_add_survey_config.py
│   │   │       ├── 003_survey_version_control.py
│   │   │       └── 004_ballot_stuffing_protection.py
│   │   └── app/
│   │       ├── main.py             # FastAPI app, CORS, router mounting
│   │       ├── config.py           # Pydantic Settings (env vars)
│   │       ├── db.py               # Async SQLAlchemy engine + session
│   │       ├── models.py           # ORM models: Cohort, Submission, Answer, Extraction, SurveyConfigVersion
│   │       ├── schemas.py          # Pydantic request/response schemas
│   │       ├── auth.py             # bcrypt verify, JWT create/verify, require_admin/require_editor
│   │       ├── routers/
│   │       │   ├── survey.py       # GET /v1/survey/{cohort_id} (randomized config)
│   │       │   ├── submissions.py  # Start, answer, complete submission
│   │       │   ├── transcribe.py   # POST /v1/transcribe (Whisper)
│   │       │   ├── ai.py           # POST /v1/ai/vagueness, /v1/ai/followups
│   │       │   ├── admin.py        # Login, metrics, responses, exports, cohorts
│   │       │   └── editor.py       # Login, get/save survey, version history, restore
│   │       └── services/
│   │           ├── ai_service.py   # detect_vagueness, generate_followups, extract_structured
│   │           ├── transcribe_service.py  # Whisper audio-to-text
│   │           └── export_service.py      # CSV, PDF (ReportLab), PPTX generation
│   │
│   └── web/                        # ── Next.js Frontend ──
│       ├── package.json            # Dependencies: React 19, Next.js 16, shadcn/ui, zod
│       ├── next.config.ts          # next-intl plugin, unoptimized images
│       ├── tsconfig.json           # Strict mode, @/* path alias
│       ├── postcss.config.mjs      # Tailwind CSS v4 via @tailwindcss/postcss
│       ├── components.json         # shadcn/ui config (New York variant)
│       ├── public/
│       │   └── images/
│       │       ├── logo.png        # InnovateUS logo (light)
│       │       └── logo-dark.png   # InnovateUS logo (dark)
│       └── src/
│           ├── app/
│           │   ├── layout.tsx      # Root layout: fonts (DM Serif Display, Libre Franklin, Geist Mono)
│           │   ├── page.tsx        # Landing page: hero, features, how-it-works, CTA
│           │   ├── globals.css     # Tailwind v4 + shadcn theme tokens + brand colors
│           │   ├── c/
│           │   │   └── [cohortId]/
│           │   │       ├── page.tsx        # Consent page (privacy notice + start submission)
│           │   │       ├── survey/
│           │   │       │   └── page.tsx    # Survey page (stepped questions + AI flow)
│           │   │       └── done/
│           │   │           └── page.tsx    # Done page (thank you + extraction summary)
│           │   └── admin/
│           │       ├── page.tsx            # Redirects to /admin/login
│           │       ├── login/
│           │       │   └── page.tsx        # Admin login
│           │       ├── dashboard/
│           │       │   └── page.tsx        # Manager dashboard (metrics, responses, exports)
│           │       └── editor/
│           │           ├── login/
│           │           │   └── page.tsx    # Editor login
│           │           └── page.tsx        # Survey editor (question editor, groups, versions)
│           ├── components/
│           │   ├── InnovateLogo.tsx        # Brand logo component
│           │   ├── QuestionCard.tsx        # Card wrapper for survey questions
│           │   ├── ProgressBar.tsx         # "Question X of Y" progress indicator
│           │   ├── ChoiceQuestion.tsx      # Rating (Select) and MCQ (RadioGroup) inputs
│           │   ├── MultiSelectQuestion.tsx # Checkbox-based multi-select input
│           │   ├── OpenEndedQuestion.tsx   # Text/voice toggle, Textarea or VoiceRecorder
│           │   ├── VoiceRecorder.tsx       # MediaRecorder + Web Speech API + Whisper fallback
│           │   ├── FollowUpPanel.tsx       # AI follow-up questions (up to 2, text or voice)
│           │   ├── PrivacyFooter.tsx       # Fixed footer: "no audio stored, anonymous"
│           │   └── ui/                     # shadcn/ui primitives (button, card, dialog, etc.)
│           ├── lib/
│           │   ├── api.ts          # HTTP client, types, all API method wrappers
│           │   ├── i18n.ts         # next-intl config (loads en.json)
│           │   └── utils.ts        # cn() helper (clsx + tailwind-merge)
│           └── messages/
│               └── en.json         # English UI strings
```

---

## Survey Configuration

Surveys are stored as JSON in each cohort's `survey_config` column. The default configuration lives in `docs/survey-config/survey-en.json`.

### Question Types

| Type | Frontend Component | Input | Stored Value |
|------|--------------------|-------|-------------|
| `rating` | `ChoiceQuestion` (Select dropdown) | Single numeric selection | String of the number (e.g. `"8"`) |
| `mcq` | `ChoiceQuestion` (RadioGroup) | Single option selection | Selected option string |
| `multi` | `MultiSelectQuestion` (Checkboxes) | Multiple options | JSON array of selected strings |
| `open` | `OpenEndedQuestion` (Textarea or VoiceRecorder) | Free text or voice transcript | Text string |

### Question Groups

Questions are assigned to named groups. Each group has an `id`, `label`, and `randomize` flag:

```json
{
  "question_groups": [
    { "id": "closed", "label": "Closed-ended questions", "randomize": true },
    { "id": "open", "label": "Open-ended questions", "randomize": true }
  ]
}
```

When `randomize` is `true`, the server shuffles question order within that group on each request, distributing survey fatigue evenly.

### Conditional Logic

Questions can have a `condition` field that controls visibility based on a prior answer:

```json
{
  "id": "q6_most_impactful",
  "type": "open",
  "text": "What is your most impactful use of Generative AI now?",
  "voice_eligible": true,
  "group": "open",
  "condition": {
    "question_id": "q2_confidence",
    "operator": "not_equals",
    "value": "I am not using generative AI yet"
  }
}
```

Supported operators: `equals`, `not_equals`. The server-side randomizer ensures prerequisite questions always appear before their dependents.

---

## AI Prompts

The three prompt templates in `docs/prompts/` define how OpenAI models analyze responses:

| File | Model | Temperature | Purpose |
|------|-------|-------------|---------|
| `vagueness.txt` | GPT-4o-mini | 0.1 | Classify answers as vague or specific. Returns `is_vague`, `reason`, and `missing_info_types`. |
| `followup.txt` | GPT-4o-mini | 0.3 | Generate 1-2 short follow-up questions targeting the missing information types. Max 18 words each. |
| `extraction.txt` | GPT-4o | 0.1 | Extract structured fields (themes, barriers, workflows, success stories) from all answers combined. |

All prompts enforce JSON response format and include hard rules: never hallucinate information, strip PII, keep text concise. The AI service degrades gracefully when no API key is configured.

---

## API Reference

All endpoints are prefixed with the backend URL (default `http://localhost:8000`).

### Public Endpoints (Participant)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/survey/{cohort_id}` | Returns the survey config with questions randomized per request. Groups with `randomize: true` have their questions shuffled while respecting conditional dependencies. |
| `POST` | `/v1/submissions/start` | Starts a new submission or resumes an existing incomplete one. Accepts `cohort_id`. Hashes the client IP for ballot-stuffing detection. Returns `submission_id` and `survey_version`. |
| `POST` | `/v1/submissions/{id}/answer` | Upserts an answer for a question. Accepts `question_id`, `question_type`, `answer_raw`, `input_mode`, `transcript`, `is_vague`, follow-up fields. |
| `POST` | `/v1/submissions/{id}/complete` | Marks submission as completed. Triggers structured extraction via GPT-4o. Returns the extraction result. Sets a `submitted_{cohort_id}` cookie. |
| `POST` | `/v1/transcribe` | Accepts an audio file (multipart form). Sends to OpenAI Whisper. Returns `{ "text": "..." }`. |
| `POST` | `/v1/ai/vagueness` | Accepts `question_text` and `answer_text`. Returns `{ "is_vague": bool, "reason": str, "missing_info_types": [...] }`. |
| `POST` | `/v1/ai/followups` | Accepts `question_text`, `answer_text`, and `missing_info_types`. Returns `{ "followups": ["...", "..."] }`. |

### Admin Endpoints (Manager)

All admin endpoints require a valid JWT token (via `Authorization: Bearer` header or `admin_token` cookie).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/admin/login` | Accepts `password`. Verifies against `ADMIN_PASSWORD_HASH`. Returns JWT with 24-hour expiry. |
| `GET` | `/v1/admin/metrics` | Dashboard metrics. Supports query params: `cohort_id`, `start`, `end`, `survey_version`. Returns submission count, completion rate, avg recommendation score, confidence distribution, vagueness rate. |
| `GET` | `/v1/admin/responses` | Paginated response list. Supports `cohort_id`, `start`, `end`, `survey_version`, `page`, `per_page`. Returns responses with answers, extraction data, and duplicate IP hints. |
| `DELETE` | `/v1/admin/responses` | Deletes all responses. Optional `cohort_id` to scope deletion. |
| `GET` | `/v1/admin/cohorts` | Lists all programs/cohorts with their IDs, names, and active survey versions. |
| `POST` | `/v1/admin/cohorts` | Creates a new program with a default survey config and initial v1 version snapshot. |
| `POST` | `/v1/admin/cohorts/{id}/settings` | Updates cohort settings (currently `max_submissions_per_ip`). |
| `GET` | `/v1/admin/export/raw.csv` | Raw CSV export with one row per respondent. Supports date/cohort filters. |
| `GET` | `/v1/admin/export/structured.csv` | Structured CSV with one row per question-answer pair. |
| `GET` | `/v1/admin/export/summary.pdf` | Branded PDF report with metrics, themes, barriers, stories, workflows. |
| `GET` | `/v1/admin/export/summary.pptx` | PowerPoint deck with 7 slides: title, metrics, workflows, barriers, stories, themes, recommendations. |

### Editor Endpoints

All editor endpoints require a valid JWT with `role: editor` (via `Authorization: Bearer` header or `editor_token` cookie).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/admin/editor/login` | Accepts `password`. Verifies against `EDITOR_PASSWORD_HASH`. Returns JWT with `role: editor`. |
| `GET` | `/v1/admin/editor/survey/{cohort_id}` | Returns the current survey config in canonical (non-randomized) order, plus the active version label. |
| `PUT` | `/v1/admin/editor/survey/{cohort_id}` | Saves the survey config. If the config has changed, creates a new version with an auto-generated change summary. Returns the new version label or "no changes detected." |
| `GET` | `/v1/admin/editor/survey/{cohort_id}/versions` | Lists all version snapshots with labels, timestamps, change summaries, and author. |
| `GET` | `/v1/admin/editor/survey/{cohort_id}/versions/{label}` | Returns the full config for a specific version. |
| `POST` | `/v1/admin/editor/survey/{cohort_id}/versions/{label}/restore` | Restores an old version by creating a new forward version (e.g., restoring v2 when active is v5 creates v6). |

---

## Database Schema

### Models

The backend uses SQLAlchemy 2.0 declarative models with PostgreSQL-specific types (UUID, JSONB):

**Cohort** -- Represents a training program/cohort.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated UUID |
| `name` | String(255) | Program name (e.g., "Pilot Cohort 1") |
| `course_name` | String(255) | Course name (e.g., "Generative AI for Government") |
| `survey_config` | JSONB | Current survey JSON config |
| `active_version` | String(20) | Active survey version label (e.g., "v3") |
| `max_submissions_per_ip` | Integer | Max completed submissions per hashed IP (default: 1, 0 = unlimited) |
| `created_at` | DateTime | Creation timestamp |

**Submission** -- A participant's survey session.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated UUID |
| `cohort_id` | UUID (FK) | References `cohorts.id` |
| `status` | String(20) | `started`, `completed`, or `abandoned` |
| `survey_version` | String(20) | Survey version at time of submission |
| `ip_hash` | String(64) | SHA-256 hash of client IP (salted) |
| `created_at` | DateTime | When submission started |
| `completed_at` | DateTime | When submission completed |
| `time_to_complete_sec` | Integer | Duration in seconds |
| `consent_version` | String(20) | Consent notice version accepted |
| `client_metadata` | JSONB | Optional browser/device metadata |

**Answer** -- A single question response within a submission.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated UUID |
| `submission_id` | UUID (FK) | References `submissions.id` |
| `question_id` | String(50) | Question identifier (e.g., `q1_recommend`) |
| `question_type` | String(20) | `rating`, `mcq`, `multi`, or `open` |
| `answer_raw` | Text | The raw answer value |
| `input_mode` | String(10) | `none`, `text`, or `voice` |
| `transcript` | Text | Voice transcript (if voice input) |
| `is_vague` | Boolean | Whether AI flagged this answer as vague |
| `followups_asked` | Integer | Number of follow-ups generated (0-2) |
| `followup_1` | Text | First follow-up question text |
| `followup_1_answer` | Text | Participant's answer to first follow-up |
| `followup_2` | Text | Second follow-up question text |
| `followup_2_answer` | Text | Participant's answer to second follow-up |

**Extraction** -- AI-extracted structured insights for a completed submission.

| Column | Type | Description |
|--------|------|-------------|
| `submission_id` | UUID (PK, FK) | One-to-one with `submissions.id` |
| `what_was_tried` | Text | GenAI usage described by participant |
| `planned_task_or_workflow` | Text | Specific task they plan to do |
| `outcome_or_expected_outcome` | Text | Results achieved or expected |
| `barriers` | JSONB | Array of challenges |
| `enablers` | JSONB | Array of helpful factors |
| `public_benefit` | Text | Public/agency mission benefit |
| `top_themes` | JSONB | Array of 3-6 key themes |
| `success_story_candidate` | Text | De-identified shareable quote |
| `created_at` | DateTime | Extraction timestamp |

**SurveyConfigVersion** -- Immutable snapshot of a survey configuration.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated UUID |
| `cohort_id` | UUID (FK) | References `cohorts.id` |
| `version_label` | String(20) | Version label (e.g., `v1`, `v2`) |
| `config` | JSONB | Full survey config snapshot |
| `change_summary` | Text | Auto-generated description of changes |
| `created_by` | String(50) | Author role (default: `editor`) |
| `created_at` | DateTime | Version creation timestamp |

### Migrations

| Migration | File | Description |
|-----------|------|-------------|
| 001 | `001_initial_schema.py` | Creates `cohorts`, `submissions`, `answers` tables |
| 002 | `002_add_survey_config.py` | Adds `extractions` table |
| 003 | `003_survey_version_control.py` | Adds `survey_config_versions` table, `survey_version` column on submissions, `active_version` on cohorts, backfills v1 for existing configs |
| 004 | `004_ballot_stuffing_protection.py` | Adds `ip_hash` on submissions, `max_submissions_per_ip` on cohorts, composite index for efficient lookups |

Run all pending migrations:

```bash
cd apps/api
alembic upgrade head
```

---

## Environment Variables

All variables are configured in the root `.env` file (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://postgres:postgres@localhost:5432/innovateus` | Async PostgreSQL connection string (asyncpg driver) |
| `DATABASE_URL_SYNC` | No | Derived from `DATABASE_URL` | Sync PostgreSQL connection string (psycopg2 driver, used by Alembic). Auto-derived if not set. |
| `OPENAI_API_KEY` | No | `""` | OpenAI API key for GPT and Whisper. AI features gracefully degrade without it. |
| `ADMIN_PASSWORD_HASH` | Yes | `""` | Bcrypt hash of the admin dashboard password |
| `EDITOR_PASSWORD_HASH` | Yes | `""` | Bcrypt hash of the survey editor password |
| `JWT_SECRET` | Yes | `change-me-in-production` | Secret key for signing JWT tokens (HS256) |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated list of allowed CORS origins |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Backend URL used by the frontend API client |
| `ENVIRONMENT` | No | `development` | Set to `production` to disable SQLAlchemy echo logging |

Generate password hashes with:

```bash
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-password'))"
```

---

## Deployment

### One-Click Deploy to Render

The repository includes a `render.yaml` blueprint that provisions three services automatically:

| Service | Type | Runtime | Description |
|---------|------|---------|-------------|
| `innovateus-db` | PostgreSQL | Managed | Free-tier PostgreSQL database |
| `innovateus-api` | Web Service | Python 3.11 | FastAPI backend (auto-runs migrations + seed on start) |
| `innovateus-web` | Web Service | Node 20 | Next.js frontend (auto-wired to API URL) |

Steps:

1. Push your code to GitHub
2. Go to [render.com/deploy](https://render.com/deploy) and connect your repository
3. Render auto-detects the `render.yaml` blueprint
4. Fill in the required secret values:
   - `OPENAI_API_KEY` -- your OpenAI key
   - `ADMIN_PASSWORD_HASH` -- bcrypt hash of your admin password
   - `EDITOR_PASSWORD_HASH` -- bcrypt hash of your editor password
5. Click **Apply** -- migrations and seeding run automatically on first deploy
6. The frontend's `NEXT_PUBLIC_API_URL` is auto-wired to the backend's external URL

### Manual Service Setup

If deploying to another platform, configure two services:

| Service | Root Dir | Build Command | Start Command |
|---------|----------|---------------|---------------|
| **Backend** (Python 3.11) | `apps/api` | `pip install -r requirements.txt` | `alembic upgrade head && python seed.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Frontend** (Node 20) | `apps/web` | `npm install && npm run build` | `npx next start -p $PORT` |

Set `NEXT_PUBLIC_API_URL` on the frontend to point to the backend's public URL, and `CORS_ORIGINS` on the backend to include the frontend's URL.

---

<p align="center">
  <strong>InnovateUS Voice Feedback Tool</strong><br>
  Privacy-first feedback for public service professionals
</p>
