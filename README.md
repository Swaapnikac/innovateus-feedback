# InnovateUS Voice Feedback Tool

[![Dependency Review](https://img.shields.io/badge/dependencies-monitored-brightgreen)](https://github.com/Swaapnikac/innovateus-feedback/security)

A privacy-first, no-login web check-in that collects InnovateUS post-course feedback using voice-to-text for open-ended questions, adds bounded AI follow-ups when responses are vague, extracts structured insights, and provides a program manager dashboard with exports.

**Live Demo**: [innovateus-feedback.onrender.com](https://innovateus-feedback.onrender.com)

## Architecture

- **Frontend**: Next.js 16 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
- **Backend**: FastAPI (Python 3.11) + SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL 16
- **AI**: OpenAI GPT-4o/GPT-4o-mini (vagueness detection, follow-ups, extraction)
- **Speech-to-Text**: OpenAI Whisper API
- **Exports**: CSV (pandas), PDF (ReportLab), PPTX (python-pptx)
- **i18n**: English + Spanish via next-intl
- **Hosting**: Render (render.yaml blueprint for one-click deploy)

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- PostgreSQL 16 (or Docker)
- OpenAI API key

### 1. Clone and configure

```bash
git clone https://github.com/Swaapnikac/innovateus-feedback.git
cd innovateus-feedback
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
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
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

## Deploy to Render

This project includes a `render.yaml` blueprint for one-click deployment:

1. Go to [render.com/deploy](https://render.com/deploy) and connect your GitHub repo
2. Render auto-detects the blueprint and creates 3 services: PostgreSQL, backend, frontend
3. Fill in the required secrets (`OPENAI_API_KEY`, `ADMIN_PASSWORD_HASH`, `EDITOR_PASSWORD_HASH`)
4. Click Apply — migrations and seeding run automatically on first deploy

Alternatively, create each service manually:

| Service | Runtime | Root Directory | Build Command | Start Command |
|---|---|---|---|---|
| Backend | Python 3.11 | `apps/api` | `pip install -r requirements.txt` | `alembic upgrade head && python seed.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Frontend | Node 20 | `apps/web` | `npm install && npm run build` | `npx next start -p $PORT` |

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
        versions/         # Database migrations (001–004)
  docs/
    prompts/              # AI prompt templates
    survey-config/        # Survey definition JSON with question groups
  render.yaml             # Render deployment blueprint
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

### Ballot-Box Stuffing Protection
- IP-based duplicate submission detection with SHA-256 hashing (salted for privacy)
- Configurable `max_submissions_per_ip` limit per program (default: 1, set to 0 for unlimited)
- Only completed submissions count — starting and abandoning does not block future attempts
- Incomplete submissions are automatically resumed instead of creating duplicates
- Friendly "Thank You" page for blocked users

### Manager Dashboard
- Overview metrics (submissions, completion rate, avg recommend score, confidence distribution, vagueness rate)
- All metrics respect active filters (cohort, date range, survey version)
- Response table with status badges, version stamps, and duplicate IP detection
- Create new programs directly from the dashboard with auto-generated survey links
- Delete all responses with confirmation dialog (scoped to selected program or all)
- Export: Raw CSV, Structured CSV, Summary PDF, Summary PPTX

### Survey Editor
- Visual question editor with drag-to-reorder, conditional logic, and group assignment
- Question group management with randomization toggles
- Configurable max submissions per IP setting
- Active version label displayed next to save button
- Save feedback: "Saved as v4" or "No changes detected"
- Collapsible version history panel with view and restore

### Privacy
- No participant login or identifiers
- Audio exists only in browser memory and transient server memory
- Server never writes audio to disk
- IP addresses are hashed (never stored in plain text)
- All responses anonymous by default

## API Endpoints

### Public (Participant)
- `GET /v1/survey/{cohort_id}` — Survey config (randomized per request)
- `POST /v1/submissions/start` — Start or resume submission (stamps survey version)
- `POST /v1/submissions/{id}/answer` — Save answer
- `POST /v1/submissions/{id}/complete` — Complete + extract
- `POST /v1/transcribe` — Audio to text (Whisper)
- `POST /v1/ai/vagueness` — Check answer vagueness
- `POST /v1/ai/followups` — Generate follow-ups

### Admin (Manager)
- `POST /v1/admin/login` — Password auth (JWT)
- `GET /v1/admin/metrics` — Dashboard metrics (filterable by cohort, date range, survey version)
- `GET /v1/admin/responses` — Paginated responses (filterable by cohort, date range, survey version)
- `DELETE /v1/admin/responses` — Delete all responses (optional cohort filter)
- `GET /v1/admin/cohorts` — List all cohorts/programs
- `POST /v1/admin/cohorts` — Create new program with default survey config
- `POST /v1/admin/cohorts/{id}/settings` — Update program settings (max submissions per IP)
- `GET /v1/admin/export/raw.csv` — Raw data export
- `GET /v1/admin/export/structured.csv` — Structured export
- `GET /v1/admin/export/summary.pdf` — PDF report
- `GET /v1/admin/export/summary.pptx` — PPTX report

### Editor
- `POST /v1/admin/editor/login` — Editor password auth (JWT)
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
| `004` | Ballot-box stuffing protection (ip_hash on submissions, max_submissions_per_ip on cohorts, composite index) |

Run all pending migrations:

```bash
cd apps/api
alembic upgrade head
```

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `OPENAI_API_KEY` | OpenAI API key |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash of admin password |
| `EDITOR_PASSWORD_HASH` | Bcrypt hash of editor password |
| `JWT_SECRET` | JWT signing secret |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) |
| `NEXT_PUBLIC_API_URL` | Backend URL for frontend |
| `ENVIRONMENT` | `development` or `production` |
