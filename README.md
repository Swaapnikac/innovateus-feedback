# InnovateUS Voice Feedback Tool

A privacy-first, no-login web check-in that collects InnovateUS post-course feedback using voice-to-text for open-ended questions, adds bounded AI follow-ups when responses are vague, extracts structured insights, and provides a program manager dashboard with exports.

## Architecture

- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
- **Backend**: FastAPI (Python) + SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL 16
- **AI**: OpenAI GPT-4o/GPT-4o-mini (vagueness detection, follow-ups, extraction)
- **Speech-to-Text**: OpenAI Whisper API
- **Exports**: CSV (pandas), PDF (ReportLab), PPTX (python-pptx)
- **i18n**: English + Spanish via next-intl
- **Survey Versioning**: Immutable config snapshots with auto-diffing and per-response version stamps

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.12+
- PostgreSQL 16 (or Docker)
- OpenAI API key

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env with your OpenAI API key and admin password hash
```

Generate an admin password hash:

```bash
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-password'))"
```

### 2. Start with Docker Compose

```bash
cd infra
docker compose up -d
```

This starts PostgreSQL, the FastAPI backend (port 8000), and the Next.js frontend (port 3000).

### 3. Local Development (without Docker)

**Database:**

```bash
# Start PostgreSQL (e.g., via Docker)
docker run -d --name innovateus-db -p 5432:5432 \
  -e POSTGRES_DB=innovateus -e POSTGRES_PASSWORD=postgres \
  postgres:16-alpine
```

**Backend:**

```bash
cd apps/api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Seed default cohort
python seed.py

# Start server
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd apps/web
npm install
npm run dev
```

### 4. Access

- **Survey (participant)**: http://localhost:3000/c/00000000-0000-0000-0000-000000000001
- **Manager Dashboard**: http://localhost:3000/admin/login
- **Survey Editor**: http://localhost:3000/admin/editor/login
- **API Docs**: http://localhost:8000/docs

## Project Structure

```
innovateus-feedback/
  apps/
    web/                  # Next.js frontend
      src/
        app/              # Pages (consent, survey, done, admin)
          admin/
            dashboard/    # Manager dashboard with version filter
            editor/       # Survey editor with version history
        components/       # UI components (VoiceRecorder, etc.)
        lib/              # API client, types, i18n config
        messages/         # Translation files (en, es)
    api/                  # FastAPI backend
      app/
        routers/          # API endpoints (survey, submissions, admin, editor, ai)
        services/         # AI, transcription, export logic
        models.py         # SQLAlchemy models (Cohort, Submission, Answer, SurveyConfigVersion)
        schemas.py        # Pydantic schemas
      alembic/
        versions/         # Database migrations (001–003)
  docs/
    prompts/              # AI prompt templates
    survey-config/        # Survey definition JSON with question groups
  infra/                  # Docker configuration
```

## Key Features

### Participant Flow
1. Open survey link (no login required)
2. Accept consent (privacy notice)
3. Answer questions with progress bar
4. Open-ended questions support voice or text input
5. Vague answers trigger up to 2 AI follow-up questions (skippable)
6. Confirmation page shows AI-extracted "What We Heard" summary

### Voice Recording
- Pause-safe: does not stop on silence
- Auto-finish after 15 seconds of inactivity
- Live transcript editing before submission
- Audio never persisted — only held in memory

### Question Grouping & Randomization
- Group questions by type (e.g. closed-ended vs open-ended)
- Per-group randomization toggle — each respondent sees a different question order within each group
- Spreads attrition evenly across questions instead of concentrating it on later items
- Server-side shuffling respects conditional dependencies (questions with conditions always appear after their prerequisites)
- Editor UI for creating, editing, and reordering groups

### Survey Version Control
- Every meaningful edit creates an immutable versioned snapshot (`v1`, `v2`, `v3`...)
- Auto-generated change summaries describe what changed (added/removed questions, text edits, option changes, reordering, etc.)
- Duplicate saves are detected — no new version created when config hasn't changed
- Each submission is stamped with the survey version it was collected against
- Version history panel in the editor with timestamps, change summaries, and one-click restore
- Admin dashboard supports filtering responses by survey version
- Restoring an old version creates a new forward version (history is never rewritten)

### Manager Dashboard
- Overview metrics (submissions, completion rate, avg scores)
- Response table with filters (cohort, date range, survey version)
- Top themes, barriers, success stories
- Export: Raw CSV, Structured CSV, Summary PDF, Summary PPTX

### Survey Editor
- Visual question editor with drag-to-reorder, conditional logic, and group assignment
- Question group management with randomization toggles
- Active version label displayed next to save button
- Save feedback: "Saved as v4" or "No changes detected"
- Collapsible version history panel with view and restore

### Privacy
- No participant login or identifiers
- Audio exists only in browser memory and transient server memory
- Server never writes audio to disk
- All responses anonymous by default

## API Endpoints

### Public (Participant)
- `GET /v1/survey/{cohort_id}` — Survey config (randomized per request)
- `POST /v1/submissions/start` — Start submission (stamps survey version)
- `POST /v1/submissions/{id}/answer` — Save answer
- `POST /v1/submissions/{id}/complete` — Complete + extract
- `POST /v1/transcribe` — Audio to text (Whisper)
- `POST /v1/ai/vagueness` — Check answer vagueness
- `POST /v1/ai/followups` — Generate follow-ups

### Admin (Manager)
- `POST /v1/admin/login` — Password auth
- `GET /v1/admin/metrics` — Dashboard metrics (filterable by survey version)
- `GET /v1/admin/responses` — Paginated responses (filterable by survey version)
- `GET /v1/admin/cohorts` — List all cohorts
- `GET /v1/admin/export/raw.csv` — Raw data export
- `GET /v1/admin/export/structured.csv` — Structured export
- `GET /v1/admin/export/summary.pdf` — PDF report
- `GET /v1/admin/export/summary.pptx` — PPTX report

### Editor
- `POST /v1/admin/editor/login` — Editor password auth
- `GET /v1/admin/editor/survey/{cohort_id}` — Get survey config (canonical order, includes active version)
- `PUT /v1/admin/editor/survey/{cohort_id}` — Save survey config (auto-versions on change)
- `GET /v1/admin/editor/survey/{cohort_id}/versions` — List version history
- `GET /v1/admin/editor/survey/{cohort_id}/versions/{label}` — Get specific version config
- `POST /v1/admin/editor/survey/{cohort_id}/versions/{label}/restore` — Restore old version

## Database Migrations

The project uses Alembic for schema migrations:

| Migration | Description |
|---|---|
| `001` | Initial schema (cohorts, submissions, answers, extractions) |
| `002` | Add extractions table |
| `003` | Survey version control (survey_config_versions table, survey_version on submissions, active_version on cohorts, v1 backfill) |

Run all pending migrations:

```bash
cd apps/api
alembic upgrade head
```

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string |
| `DATABASE_URL_SYNC` | Sync PostgreSQL connection string (Alembic) |
| `OPENAI_API_KEY` | OpenAI API key |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash of admin password |
| `EDITOR_PASSWORD_HASH` | Bcrypt hash of editor password |
| `JWT_SECRET` | JWT signing secret |
| `CORS_ORIGINS` | Allowed CORS origins |
| `NEXT_PUBLIC_API_URL` | Backend URL for frontend |
| `ENVIRONMENT` | `development` or `production` |
