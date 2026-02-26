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
- **API Docs**: http://localhost:8000/docs

## Project Structure

```
innovateus-feedback/
  apps/
    web/                  # Next.js frontend
      src/
        app/              # Pages (consent, survey, done, admin)
        components/       # UI components
        lib/              # API client, i18n config
        messages/         # Translation files (en, es)
    api/                  # FastAPI backend
      app/
        routers/          # API endpoints
        services/         # AI, transcription, export logic
        models.py         # SQLAlchemy models
        schemas.py        # Pydantic schemas
      alembic/            # Database migrations
  docs/
    prompts/              # AI prompt templates
    survey-config/        # Survey definition JSON (en, es)
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

### Manager Dashboard
- Overview metrics (submissions, completion rate, avg scores)
- Response table with filters (cohort, date range)
- Top themes, barriers, success stories
- Export: Raw CSV, Structured CSV, Summary PDF, Summary PPTX

### Privacy
- No participant login or identifiers
- Audio exists only in browser memory and transient server memory
- Server never writes audio to disk
- All responses anonymous by default

## API Endpoints

### Public (Participant)
- `GET /v1/survey/{cohort_id}` — Survey config
- `POST /v1/submissions/start` — Start submission
- `POST /v1/submissions/{id}/answer` — Save answer
- `POST /v1/submissions/{id}/complete` — Complete + extract
- `POST /v1/transcribe` — Audio to text (Whisper)
- `POST /v1/ai/vagueness` — Check answer vagueness
- `POST /v1/ai/followups` — Generate follow-ups

### Admin (Manager)
- `POST /v1/admin/login` — Password auth
- `GET /v1/admin/metrics` — Dashboard metrics
- `GET /v1/admin/responses` — Paginated responses
- `GET /v1/admin/export/raw.csv` — Raw data export
- `GET /v1/admin/export/structured.csv` — Structured export
- `GET /v1/admin/export/summary.pdf` — PDF report
- `GET /v1/admin/export/summary.pptx` — PPTX report

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string |
| `DATABASE_URL_SYNC` | Sync PostgreSQL connection string (Alembic) |
| `OPENAI_API_KEY` | OpenAI API key |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash of admin password |
| `JWT_SECRET` | JWT signing secret |
| `CORS_ORIGINS` | Allowed CORS origins |
| `NEXT_PUBLIC_API_URL` | Backend URL for frontend |
