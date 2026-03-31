# InnovateUS Public Voice -- Technical Architecture Document

**Version:** 1.0  
**Date:** March 25, 2026  
**Team:** InnovateUS Feedback Team  
**Repository:** [github.com/Swaapnikac/innovateus-feedback](https://github.com/Swaapnikac/innovateus-feedback)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [High-Level System Architecture](#2-high-level-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Voice-to-Text Pipeline (Dual-Layer Architecture)](#4-voice-to-text-pipeline)
5. [AI Pipeline -- Three Models, Three Purposes](#5-ai-pipeline)
6. [Prompt Engineering System](#6-prompt-engineering-system)
7. [Complete Data Flow -- Request Lifecycle](#7-complete-data-flow)
8. [Database Schema & Storage Design](#8-database-schema--storage-design)
9. [Authentication & Security Architecture](#9-authentication--security-architecture)
10. [Survey Version Control System](#10-survey-version-control-system)
11. [Question Randomization Engine](#11-question-randomization-engine)
12. [Ballot-Box Stuffing Prevention](#12-ballot-box-stuffing-prevention)
13. [Export & Reporting Engine](#13-export--reporting-engine)
14. [Deployment Architecture (Render)](#14-deployment-architecture)
15. [API Endpoint Reference](#15-api-endpoint-reference)
16. [Cost Analysis](#16-cost-analysis)
17. [Known Issues & Open Backend Questions](#17-known-issues--open-backend-questions)

---

## 1. Executive Summary

InnovateUS Public Voice is a **privacy-first, AI-enhanced post-course feedback platform** built for government training programs. It replaces traditional survey tools (Qualtrics, Google Forms) with a system that:

- Accepts **voice and text input** for open-ended questions
- Uses **AI to detect vague responses** and generates **targeted follow-up questions** in real time
- **Extracts structured insights** (themes, barriers, enablers, success stories) automatically from free-text answers
- Provides **version-controlled survey management** with immutable snapshots
- Delivers an **analytics dashboard** with export capabilities (CSV, PDF, PowerPoint)
- Prevents **ballot-box stuffing** via hashed IP tracking with configurable limits
- Runs fully **anonymous** -- no participant login required, no audio stored, IP addresses hashed

### Key Differentiators

| Capability | Traditional Tools (Qualtrics, Google Forms) | InnovateUS Public Voice |
|-----------|-------------------------------------------|------------------------|
| Voice input | Not available | Browser-native + OpenAI Whisper fallback |
| AI follow-ups | Static skip logic only | Dynamic GPT-powered follow-ups targeting specific gaps |
| Structured extraction | Manual researcher coding | Automatic per-submission GPT-4o extraction |
| Version control | Timestamps only | Immutable snapshots, auto-diff, per-response stamps |
| Randomization | Basic question shuffling | Group-aware, conditional-dependency-preserving shuffle |
| Privacy | Account/cookies required | Fully anonymous, no login, no audio stored, IP hashed |
| Export | CSV (often paid for more) | CSV + PDF + PPTX, all server-generated |

---

## 2. High-Level System Architecture

```
+------------------------------------------+
|          CLIENT LAYER (Browser)          |
|                                          |
|  Next.js 16 (App Router)                |
|  TypeScript + Tailwind CSS + shadcn/ui   |
|  Web Speech API (real-time preview)      |
|  MediaRecorder API (audio capture)       |
+------------------+-----------------------+
                   |
                   | HTTPS (REST API)
                   | Authorization: Bearer JWT
                   | credentials: include
                   |
+------------------v-----------------------+
|       APPLICATION LAYER (FastAPI)        |
|                                          |
|  Python 3.11 + Async/Await              |
|  +-----------+ +-----------+ +--------+ |
|  | Survey    | | Submission| | Admin  | |
|  | Router    | | Router    | | Router | |
|  +-----------+ +-----------+ +--------+ |
|  +-----------+ +-----------+ +--------+ |
|  | AI        | | Transcribe| | Editor | |
|  | Router    | | Router    | | Router | |
|  +-----------+ +-----------+ +--------+ |
|                                          |
|  +--------------------------------------+|
|  |         SERVICE LAYER                ||
|  | ai_service.py  transcribe_service.py ||
|  | export_service.py  auth.py           ||
|  +--------------------------------------+|
+------------------+-----------------------+
                   |
        +----------+----------+
        |                     |
+-------v--------+  +--------v---------+
|   AI LAYER     |  |   DATA LAYER     |
|   (OpenAI)     |  |  (PostgreSQL)    |
|                |  |                  |
| GPT-4o-mini    |  | 5 Tables         |
| GPT-4o         |  | JSONB configs    |
| Whisper-1      |  | Alembic managed  |
+----------------+  +------------------+
```

### Request Flow Summary

```
Browser --> Next.js Frontend --> FastAPI Backend --> PostgreSQL
                                    |
                                    +--> OpenAI API (GPT-4o, GPT-4o-mini, Whisper-1)
```

---

## 3. Technology Stack

### 3.1 Frontend

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Framework | Next.js (App Router) | 16.x | Server-rendered React with file-based routing |
| Language | TypeScript | 5.x | Type safety across all frontend code |
| Styling | Tailwind CSS | 4.x | Utility-first CSS framework |
| UI Library | shadcn/ui | Latest | Accessible, customizable component library |
| Icons | Lucide React | 0.575 | Consistent icon set |
| Internationalization | next-intl | 4.8 | English + Spanish localization |
| Audio Capture | Web Speech API + MediaRecorder | Browser native | Real-time transcription + audio recording |

### 3.2 Backend

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Framework | FastAPI | 0.115.0 | Async Python REST API with auto-generated docs |
| Runtime | Python | 3.11.6 | Async/await, type hints, performance |
| ORM | SQLAlchemy | 2.0.35 | Async database access with mapped classes |
| Migrations | Alembic | 1.13.3 | Versioned, incremental schema changes (4 migrations) |
| DB Driver | asyncpg | 0.30.0 | High-performance async PostgreSQL driver |
| Auth | python-jose + passlib/bcrypt | 3.3 / 1.7 | JWT creation/verification + password hashing |
| AI Client | openai (Python SDK) | 1.55.0 | Async calls to GPT-4o, GPT-4o-mini, Whisper |
| PDF Export | ReportLab | 4.2.5 | Programmatic PDF report generation |
| PPTX Export | python-pptx | 1.0.2 | PowerPoint slide deck generation |
| Data Export | pandas | 2.2.3 | CSV export and data manipulation |
| HTTP Client | httpx | 0.27.2 | HTTP client for external calls |
| Server | Uvicorn | 0.30.6 | ASGI server for FastAPI |

### 3.3 Database

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Engine | PostgreSQL 16 | Relational + JSONB for flexible survey configs |
| JSONB | Native PostgreSQL type | Stores survey configurations without rigid schema |
| Hosting | Render Managed PostgreSQL | Auto-backups, connection pooling |

### 3.4 AI Models Used

| Model | Provider | Purpose | Cost |
|-------|----------|---------|------|
| **GPT-4o-mini** | OpenAI | Vagueness detection + follow-up generation | ~$0.15/M input tokens |
| **GPT-4o** | OpenAI | Structured insight extraction | ~$2.50/M input tokens |
| **Whisper-1** | OpenAI | Speech-to-text (server-side fallback) | $0.006/minute audio |

---

## 4. Voice-to-Text Pipeline

### 4.1 Dual-Layer Architecture

Our voice system uses **two transcription layers running simultaneously** for the best user experience:

```
USER CLICKS "START RECORDING"
        |
        v
+------- navigator.mediaDevices.getUserMedia({ audio: true }) ------+
|                                                                    |
|   LAYER 1: Web Speech API              LAYER 2: MediaRecorder     |
|   (Browser-native, real-time)           (Audio capture, WebM)     |
|                                                                    |
|   - SpeechRecognition.start()           - MediaRecorder.start()   |
|   - continuous: true                    - 1000ms chunk interval    |
|   - interimResults: true                - audio/webm;codecs=opus  |
|   - lang: "en-US"                                                  |
|                                                                    |
|   Words appear LIVE as user speaks      Audio chunks stored in     |
|   (near-zero latency)                  memory (Ref, not disk)     |
|                                                                    |
+------- USER CLICKS "STOP" or 15s INACTIVITY AUTO-STOP -----------+
        |
        v
+----------- TRANSCRIPTION DECISION -----------+
|                                               |
|  IF Web Speech produced final transcript:     |
|    --> Use it directly (no server call)        |
|    --> Fastest path, zero cost                 |
|                                               |
|  ELSE (Speech API failed or empty):           |
|    --> Send audio blob to backend              |
|    --> POST /v1/transcribe (multipart)         |
|    --> OpenAI Whisper-1 processes audio         |
|    --> Return high-accuracy transcript          |
|                                               |
+-----------------------------------------------+
        |
        v
USER SEES EDITABLE TRANSCRIPT IN TEXTAREA
        |
        v
USER CLICKS "USE THIS RESPONSE"
        |
        v
FINAL TEXT SAVED AS answer_raw (transcript stored separately)
```

### 4.2 Layer 1: Web Speech API (Browser-Native, Real-Time)

| Property | Detail |
|----------|--------|
| **API** | `window.SpeechRecognition` / `webkitSpeechRecognition` |
| **Mode** | `continuous: true`, `interimResults: true` |
| **Language** | `en-US` |
| **Latency** | Near-instant (words appear as user speaks) |
| **Cost** | Free (runs entirely in the browser) |
| **Accuracy** | Good for clear speech; may struggle with accents/noise |
| **Browser support** | Chrome, Edge (full); Safari (partial); Firefox (not supported) |
| **Purpose** | Live preview so the user sees their words appearing immediately |

**How it works internally:**
1. `SpeechRecognition` fires `onresult` events containing `interim` (partial) and `final` (confirmed) segments
2. We accumulate `final` text in `finalTranscriptRef` and display `final + interim` as live preview
3. Each `onresult` event resets a 15-second inactivity timer
4. If recognition ends unexpectedly, `onend` handler auto-restarts it (while still recording)

### 4.3 Layer 2: OpenAI Whisper-1 (Server-Side Fallback)

| Property | Detail |
|----------|--------|
| **Model** | `whisper-1` (OpenAI) |
| **Input format** | Audio blob (`audio/webm;codecs=opus`), sent as multipart form data |
| **Output format** | Plain text (`response_format="text"`) |
| **Latency** | 1-5 seconds depending on audio length |
| **Cost** | $0.006 per minute of audio |
| **Accuracy** | State-of-the-art; handles accents, noise, technical vocabulary |
| **Purpose** | Fallback when browser Speech API fails or produces empty results |

**Backend processing** (`transcribe_service.py`):
```
1. Receive audio blob as UploadFile
2. Read into io.BytesIO buffer (in-memory only)
3. Send to OpenAI: client.audio.transcriptions.create(model="whisper-1", file=buffer)
4. Return plain text transcript
5. Close buffer + delete audio_bytes from memory
```

### 4.4 Audio Privacy Guarantees

| Guarantee | How It's Enforced |
|-----------|-------------------|
| No audio stored on server | Buffer is `close()`d + `del audio_bytes` immediately after transcription |
| No audio stored in browser | MediaRecorder chunks held in React `Ref` (memory); cleared after use |
| Microphone released | All `MediaStream` tracks explicitly stopped (`track.stop()`) |
| No audio in database | Only the edited text transcript is saved to `answers.transcript` column |
| No audio sent to third parties | Only OpenAI Whisper receives audio (when fallback is needed) |

### 4.5 Auto-Stop & Inactivity Behavior

| Feature | Detail |
|---------|--------|
| Inactivity timeout | 15 seconds of no new speech triggers auto-stop |
| Timer reset | Every `onresult` event from SpeechRecognition resets the 15s timer |
| Pause-safe | Brief silences do NOT stop recording; only 15 consecutive seconds of silence |
| Manual stop | User can click "Stop Recording" at any time |

---

## 5. AI Pipeline

### 5.1 Three Models, Three Purposes

```
PARTICIPANT ANSWERS AN OPEN-ENDED QUESTION
        |
        v
+-- STEP 1: VAGUENESS DETECTION (GPT-4o-mini) ----+
|                                                    |
|  Input: { question, answer }                       |
|  Output: { is_vague, reason, missing_info_types }  |
|  Temperature: 0.1 (deterministic)                  |
|  Format: JSON mode                                 |
|  Cost: ~$0.00015 per call                          |
|                                                    |
+-- is_vague = false? --> SAVE ANSWER, NEXT QUESTION |
|                                                    |
+-- is_vague = true? --+                             |
                       |
                       v
+-- STEP 2: FOLLOW-UP GENERATION (GPT-4o-mini) ----+
|                                                    |
|  Input: { question, answer, missing_info_types }   |
|  Output: { followups: [1-2 questions] }            |
|  Temperature: 0.3 (slight creativity)              |
|  Format: JSON mode                                 |
|  Cost: ~$0.0003 per call                           |
|  Rule: Each follow-up UNDER 18 words               |
|                                                    |
+-- User answers or skips follow-ups ---------------+
                       |
                       v
           (Survey continues...)
                       |
                       v
+-- STEP 3: STRUCTURED EXTRACTION (GPT-4o) --------+
|  Triggered: On survey completion (POST /complete)  |
|                                                    |
|  Input: ALL answers for the submission             |
|  Output: 8 structured fields (see below)           |
|  Temperature: 0.1 (deterministic)                  |
|  Format: JSON mode                                 |
|  Cost: ~$0.01 per call                             |
|                                                    |
+----------------------------------------------------+
```

### 5.2 Why These Specific Models?

| Task | Model | Why This Model |
|------|-------|---------------|
| Vagueness Detection | `gpt-4o-mini` | Fast, cheap, binary classification task -- doesn't need heavy reasoning |
| Follow-up Generation | `gpt-4o-mini` | Short outputs, conversational tone; creativity needs are modest |
| Structured Extraction | `gpt-4o` | Complex multi-field extraction from diverse free-text answers; needs stronger reasoning |

### 5.3 Step 1: Vagueness Detection -- Detail

**When triggered:** After a participant answers any `type: "open"` question with `voice_eligible: true`

**Classification criteria:**
- **SPECIFIC** = mentions a concrete task, outcome, barrier, or real example
- **VAGUE** = generic praise/criticism like "It was helpful" or "Good course" that could apply to any course

**Example input/output:**
```
Input:  {"question": "What will you try with GenAI?", "answer": "It was very helpful"}
Output: {"is_vague": true, "reason": "No specific task or outcome mentioned", "missing_info_types": ["task", "outcome"]}

Input:  {"question": "What will you try?", "answer": "I plan to use GPT to summarize policy memos weekly"}
Output: {"is_vague": false, "reason": "Mentions specific task and workflow", "missing_info_types": []}
```

### 5.4 Step 2: Follow-up Generation -- Detail

**When triggered:** Only if Step 1 returns `is_vague: true`

**Rules enforced by system prompt:**
1. Generate at most 2 follow-up questions
2. Each question MUST be under 18 words
3. Friendly, non-judgmental, easy to answer
4. NEVER ask for identifying details (name, department, agency)
5. Target the specific `missing_info_types` from vagueness detection

**Example output:**
```json
{
  "followups": [
    "Can you describe a specific task where you'd use what you learned?",
    "What outcome are you hoping to achieve with this new skill?"
  ]
}
```

**UX flow:** Participant sees follow-ups in a panel. They can answer either/both or skip. All follow-up data is stored alongside the main answer in the database.

### 5.5 Step 3: Structured Extraction -- Detail

**When triggered:** On `POST /v1/submissions/{id}/complete` (survey completion)

**Input:** All answers for the submission, including follow-up answers and original voice transcripts

**Output schema (8 fields):**

| Field | Type | Description |
|-------|------|-------------|
| `what_was_tried` | string or null | What the participant already tried with GenAI |
| `planned_task_or_workflow` | string or null | Specific task they plan to do |
| `outcome_or_expected_outcome` | string or null | Result achieved or expected |
| `barriers` | string[] | Challenges mentioned (e.g., "No IT support", "Policy restrictions") |
| `enablers` | string[] | Things that helped (e.g., "Supportive manager", "Good training materials") |
| `public_benefit` | string or null | How this benefits the public or agency mission |
| `top_themes` | string[] | 3-6 key themes from all responses |
| `success_story_candidate` | string or null | De-identified quote suitable for public sharing |

**Hard rules enforced by prompt:**
1. NEVER invent or hallucinate -- only extract what is explicitly stated
2. Null for missing fields, empty arrays for missing lists
3. Strip all identifying information (names, agencies, emails)
4. Success story must be de-identified and suitable for public sharing
5. All text concise -- 1-2 sentences max per field

### 5.6 Graceful Degradation

| Failure Scenario | System Behavior |
|-----------------|-----------------|
| OpenAI API key missing/invalid | Vagueness returns `is_vague: false` (no follow-ups shown); extraction returns nulls |
| Vagueness API call times out | Treated as non-vague; user proceeds normally |
| Follow-up generation fails | Empty array returned; user moves to next question |
| Extraction fails on submit | Submission still completes; extraction fields saved as null |
| Whisper transcription fails | Falls back to browser Web Speech result |
| All AI down | Survey works 100% normally as a standard text survey |

---

## 6. Prompt Engineering System

### 6.1 Prompt Storage Architecture

All AI system prompts are stored as **plain text files** in `docs/prompts/`:

```
docs/
  prompts/
    vagueness.txt      -- System prompt for vagueness detection
    followup.txt       -- System prompt for follow-up generation
    extraction.txt     -- System prompt for structured extraction
```

**Why external files instead of inline strings?**
- Easy to iterate on prompts without code changes
- Non-engineers can review/edit prompt logic
- Version controlled with the rest of the codebase
- Can be swapped per-environment if needed

### 6.2 Prompt Loading

```python
PROMPTS_DIR = Path(__file__).resolve().parents[4] / "docs" / "prompts"

def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
```

### 6.3 JSON Mode

All three AI calls use OpenAI's `response_format={"type": "json_object"}` which guarantees:
- Output is always valid JSON (no parsing failures)
- Model follows the schema defined in the system prompt
- No markdown wrapping, no extra text

---

## 7. Complete Data Flow

### 7.1 Participant Survey Flow

```
PARTICIPANT OPENS SURVEY LINK
  /c/{cohort_id}
        |
        v
CONSENT PAGE
  - Shows consent text
  - "Begin Survey" button
        |
        v
POST /v1/submissions/start
  - Check IP hash against completed submissions
  - If over limit: HTTP 429 "Already submitted"
  - If existing incomplete submission: return that submission_id (resume)
  - Else: create new submission, stamp with survey_version
        |
        v
GET /v1/survey/{cohort_id}
  - Fetch survey config from cohort
  - Apply within-group randomization
  - Return randomized question list (Cache-Control: no-store)
        |
        v
QUESTION-BY-QUESTION FLOW (for each question):
  |
  +-- Rating/MCQ/Multi-select:
  |     POST /v1/submissions/{id}/answer
  |     { question_id, question_type, answer_raw, input_mode: "none" }
  |
  +-- Open-ended (text):
  |     1. User types response
  |     2. POST /v1/ai/vagueness { question_text, answer_text }
  |     3. If vague: POST /v1/ai/followups --> show follow-up panel
  |     4. POST /v1/submissions/{id}/answer
  |        { question_id, answer_raw, input_mode: "text", is_vague, followups... }
  |
  +-- Open-ended (voice):
        1. User records voice (Web Speech API + MediaRecorder run together)
        2. On stop: use Web Speech transcript, OR fallback to POST /v1/transcribe
        3. User edits transcript in textarea
        4. User clicks "Use This Response"
        5. POST /v1/ai/vagueness { question_text, answer_text }
        6. If vague: follow-up flow (same as text)
        7. POST /v1/submissions/{id}/answer
           { answer_raw: edited_text, input_mode: "voice", transcript: original_ai_text }
        |
        v
POST /v1/submissions/{id}/complete
  - Gather all answers
  - Call GPT-4o extract_structured(answers)
  - Save Extraction to database
  - Mark submission as "completed"
  - Set ballot-stuffing cookie (httponly, 30 days)
  - Return extraction summary
        |
        v
"WHAT WE HEARD" PAGE
  - Shows extracted themes, barriers, enablers
  - Confirms submission received
```

### 7.2 How Data Is Stored Per Answer

```
+----------------------+     +---------------------------+
| answer_raw           |     | TEXT column               |
| (final user text)    |     | "I plan to use GPT to     |
|                      |     |  summarize policy memos"  |
+----------------------+     +---------------------------+

+----------------------+     +---------------------------+
| input_mode           |     | ENUM: "none"|"text"|"voice"|
| (how user entered it)|     |                           |
+----------------------+     +---------------------------+

+----------------------+     +---------------------------+
| transcript           |     | TEXT column (nullable)     |
| (original AI speech  |     | Only populated for voice   |
|  before user edits)  |     | input; preserves original  |
+----------------------+     +---------------------------+

+----------------------+     +---------------------------+
| is_vague             |     | BOOLEAN (nullable)         |
| (AI classification)  |     | true/false/null            |
+----------------------+     +---------------------------+

+----------------------+     +---------------------------+
| followup_1           |     | AI-generated question      |
| followup_1_answer    |     | User's response to it      |
| followup_2           |     | Second AI question         |
| followup_2_answer    |     | User's response to it      |
+----------------------+     +---------------------------+
```

---

## 8. Database Schema & Storage Design

### 8.1 Entity Relationship Diagram

```
+------------------+       +------------------------+
|     cohorts      |       | survey_config_versions |
+------------------+       +------------------------+
| id (PK, UUID)   |<------| id (PK, UUID)          |
| name             |       | cohort_id (FK)         |
| course_name      |       | version_label          |
| survey_config    |       | config (JSONB)         |
|   (JSONB)        |       | change_summary         |
| active_version   |       | created_by             |
| max_submissions  |       | created_at             |
|   _per_ip        |       +------------------------+
| created_at       |
+--------+---------+
         |
         | 1:N
         |
+--------v---------+
|   submissions    |
+------------------+
| id (PK, UUID)   |
| cohort_id (FK)  |
| status           |
| survey_version   |
| ip_hash          |
| consent_version  |
| created_at       |
| completed_at     |
| time_to_complete |
| client_metadata  |
|   (JSONB)        |
+--------+---------+
         |
    +----+----+
    |         |
    | 1:N     | 1:1
    |         |
+---v----+ +--v-----------+
| answers| | extractions  |
+--------+ +--------------+
| id (PK)|  | submission_id|
| submis- |  |   (PK, FK)  |
|  sion_id|  | what_was_   |
| question|  |   tried     |
|   _id   |  | planned_    |
| question|  |   task      |
|   _type |  | outcome     |
| answer  |  | barriers    |
|   _raw  |  |   (JSONB)   |
| input   |  | enablers    |
|   _mode |  |   (JSONB)   |
| trans-  |  | public_     |
|   cript |  |   benefit   |
| is_vague|  | top_themes  |
| followup|  |   (JSONB)   |
|   _1    |  | success_    |
| followup|  |   story     |
|   _1_ans|  | created_at  |
| followup|  +--------------+
|   _2    |
| followup|
|   _2_ans|
+--------+
```

### 8.2 Table Details

**cohorts** -- Programs/courses that have surveys
- `survey_config` (JSONB): Full survey question definition (title, questions, groups, options)
- `active_version`: Currently active version label (e.g., "v3")
- `max_submissions_per_ip`: Configurable anti-fraud limit (default: 1)

**survey_config_versions** -- Immutable snapshots of survey configurations
- `config` (JSONB): Frozen copy of the survey at that point in time
- `change_summary`: Auto-generated diff (e.g., "Changed text: q3; Added: q10")
- `version_label`: "v1", "v2", etc.

**submissions** -- One row per survey attempt
- `status`: "started" | "completed" | "abandoned"
- `survey_version`: Which version of the survey this response was collected against
- `ip_hash`: SHA-256(jwt_secret + ":" + client_ip) -- raw IP is NEVER stored
- `time_to_complete_sec`: Calculated on completion

**answers** -- One row per question answered
- `answer_raw`: The final text the user submitted
- `input_mode`: "none" (rating/MCQ), "text" (typed), "voice" (spoken)
- `transcript`: Original AI transcription (before user edits); only for voice
- `is_vague`: AI classification result
- `followup_1/2` and `followup_1/2_answer`: AI-generated follow-up Q&A pairs

**extractions** -- One row per completed submission (AI-generated structured insights)
- `barriers`, `enablers`, `top_themes` stored as JSONB arrays
- All text fields are de-identified by the AI prompt

### 8.3 Why JSONB?

| Field | Why JSONB Instead of Normalized Tables |
|-------|---------------------------------------|
| `cohort.survey_config` | Survey structure changes frequently; JSONB avoids migrations per question edit |
| `survey_config_versions.config` | Must store exact config as-is at a frozen point in time |
| `extraction.barriers/enablers/themes` | Variable-length lists of strings; arrays are natural in JSONB |
| `submission.client_metadata` | Optional browser/device info; schema varies per client |

---

## 9. Authentication & Security Architecture

### 9.1 Authentication Flow

```
ADMIN/EDITOR ENTERS PASSWORD
        |
        v
POST /v1/admin/login  (or /v1/admin/editor/login)
        |
        v
bcrypt.checkpw(password, stored_hash)
        |
        +-- FAIL --> HTTP 401 "Invalid password"
        |
        +-- PASS --> Create JWT:
                     {
                       "sub": "admin",     (or "editor")
                       "role": "manager",  (or "editor")
                       "exp": now + 24h
                     }
                     Signed with HS256 + JWT_SECRET
        |
        v
TOKEN DELIVERED TWO WAYS:
  1. Set-Cookie: httponly, secure, samesite=none (production)
  2. JSON response body: { "token": "eyJ..." }
        |
        v
FRONTEND STORES TOKEN:
  - Cookie (automatic, httponly)
  - localStorage (for cross-origin Bearer header)
        |
        v
EVERY PROTECTED REQUEST:
  Backend checks: Cookie first --> then Authorization: Bearer header
  Decode JWT --> verify signature + expiry --> check role claim
```

### 9.2 Token Extraction Logic

```python
def _extract_token(request: Request, cookie_name: str) -> str | None:
    # Try cookie first
    token = request.cookies.get(cookie_name)
    if not token:
        # Fall back to Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token
```

### 9.3 Security Measures Summary

| Measure | Implementation |
|---------|---------------|
| Password storage | bcrypt hash with random salt; plain password never stored |
| JWT signing | HS256 with server-side secret; 24-hour expiry |
| IP privacy | SHA-256(jwt_secret : IP); raw IP never reaches the database |
| CORS | Strict origin allowlist; only the exact frontend URL is permitted |
| Cross-origin cookies | `samesite=none; secure; httponly` in production |
| Audio privacy | Audio bytes exist only in transient memory; explicitly deleted after transcription |
| Participant anonymity | No login required; no PII collected; no email/name fields |

---

## 10. Survey Version Control System

### 10.1 How It Works

```
EDITOR SAVES SURVEY CONFIG
        |
        v
_configs_equal(old_config, new_config)?
        |
        +-- YES (no changes) --> Return "no_changes", do NOT create version
        |
        +-- NO (something changed):
              |
              v
        _compute_change_summary(old, new)
          --> "Changed text: q3; Added: q10; Changed question groups"
              |
              v
        _next_version_label(cohort_id)
          --> "v4" (count existing versions + 1)
              |
              v
        INSERT INTO survey_config_versions:
          { cohort_id, version_label: "v4", config: <frozen JSONB snapshot>,
            change_summary: "Changed text: q3; Added: q10" }
              |
              v
        UPDATE cohort: survey_config = new, active_version = "v4"
```

### 10.2 Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Immutability** | Every version row is a frozen JSONB snapshot; never overwritten |
| **Forward-only history** | Restoring v1 creates v5 (new label); history is never rewritten |
| **Auto-diffing** | `_compute_change_summary()` detects: added/removed questions, text changes, option changes, group changes, reordering |
| **Duplicate detection** | `_configs_equal()` does deep JSON comparison; identical saves produce no new version |
| **Per-response stamp** | Every submission records `survey_version` at creation time |
| **Dashboard filtering** | Metrics and responses can be filtered by version to compare across survey iterations |

---

## 11. Question Randomization Engine

### 11.1 How It Works

Survey questions are organized into **groups** (e.g., "closed-ended" and "open-ended"). Each group can independently opt into randomization.

```
SURVEY CONFIG DEFINES:
  question_groups: [
    { id: "closed", label: "Closed-ended", randomize: true },
    { id: "open",   label: "Open-ended",   randomize: true }
  ]

  questions: [
    { id: "q1", group: "closed", ... },
    { id: "q2", group: "closed", ... },
    { id: "q3", group: "open",   ... },
    { id: "q4", group: "open",   ... },
  ]

RANDOMIZATION (server-side, per request):
  1. Bucket questions by group
  2. For each group with randomize=true: shuffle the bucket
  3. Fix conditional dependencies (if B depends on A, ensure A comes before B)
  4. Concatenate: closed-group questions, then open-group questions, then ungrouped
  5. Return randomized list to browser

RESULT: Every participant sees questions in a different random order
        within each group, but group order is always preserved.
```

### 11.2 Conditional Dependency Fix

After shuffling, the algorithm runs `_fix_conditional_order()`:
- If question B has `condition: { question_id: "q1" }`, it depends on q1
- If q1 ended up after B in the shuffle, the algorithm moves B after q1
- Iterates until no more dependency violations exist

### 11.3 Why Server-Side?

Randomization happens in the **FastAPI backend**, not the browser:
- Prevents manipulation by inspecting/modifying client-side JavaScript
- Response includes `Cache-Control: no-store` to prevent browsers from caching a single order
- Each `GET /v1/survey/{cohort_id}` returns a freshly randomized order

---

## 12. Ballot-Box Stuffing Prevention

### 12.1 Flow

```
POST /v1/submissions/start
        |
        v
EXTRACT CLIENT IP
  - From X-Forwarded-For header (Render proxy)
  - Fallback: request.client.host
        |
        v
HASH IP
  - SHA-256(jwt_secret + ":" + raw_ip)
  - Produces 64-character hex digest
  - Raw IP is NEVER stored
        |
        v
CHECK LIMIT (max_submissions_per_ip)
  - If limit = 0: no checking, unlimited submissions
  - If limit > 0:
      SELECT COUNT(*) FROM submissions
      WHERE cohort_id = ? AND ip_hash = ? AND status = 'completed'
        |
        +-- count >= limit --> HTTP 429 "Already submitted"
        |
        +-- count < limit:
              |
              v
        CHECK FOR INCOMPLETE SUBMISSION
          SELECT * FROM submissions
          WHERE cohort_id = ? AND ip_hash = ? AND status = 'started'
          ORDER BY created_at DESC LIMIT 1
              |
              +-- Found --> Return existing submission_id (resume)
              |
              +-- Not found --> Create new submission
```

### 12.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Only count `completed` submissions | Allows users to resume incomplete surveys |
| Cookie set on completion (not start) | Prevents false blocks when user only opened the survey |
| IP hashed, not stored raw | Privacy; hash is salted with JWT_SECRET so it can't be reversed |
| Configurable limit per cohort | Different programs may want different thresholds |
| Limit = 0 disables check | Easy to turn off for testing or unrestricted programs |

---

## 13. Export & Reporting Engine

### 13.1 Available Exports

| Format | Endpoint | Contents |
|--------|----------|----------|
| Raw CSV | `GET /v1/admin/export/raw.csv` | One row per answer: submission_id, question_id, answer_raw, input_mode, vagueness, follow-ups |
| Structured CSV | `GET /v1/admin/export/structured.csv` | One row per submission: extracted themes, barriers, enablers, etc. |
| PDF Report | `GET /v1/admin/export/summary.pdf` | Visual summary report with metrics and charts |
| PPTX Slides | `GET /v1/admin/export/summary.pptx` | Presentation-ready PowerPoint slide deck |

### 13.2 Technologies Used

| Export | Library | How |
|--------|---------|-----|
| CSV | Python `csv` module + pandas | Query database, format as CSV string, stream as download |
| PDF | ReportLab 4.2 | Programmatic page layout, tables, charts |
| PPTX | python-pptx 1.0 | Slide-by-slide construction with text boxes and tables |

All exports are **server-generated** and streamed directly as file downloads. No client-side processing needed.

---

## 14. Deployment Architecture

### 14.1 Infrastructure (Render Cloud)

```
+------------------------------------------+
|              RENDER CLOUD                |
|                                          |
|  +-----------------------------------+  |
|  | FRONTEND WEB SERVICE (Node 20)    |  |
|  | innovateus-feedback.onrender.com  |  |
|  |                                   |  |
|  | Build: npm install && npm run build|  |
|  | Start: npx next start -p $PORT   |  |
|  +-----------------------------------+  |
|                    |                     |
|                    | NEXT_PUBLIC_API_URL  |
|                    v                     |
|  +-----------------------------------+  |
|  | BACKEND WEB SERVICE (Python 3.11) |  |
|  | innovateus-api-u59k.onrender.com  |  |
|  |                                   |  |
|  | Start: alembic upgrade head       |  |
|  |     && python seed.py             |  |
|  |     && uvicorn app.main:app       |  |
|  +-----------------------------------+  |
|                    |                     |
|                    | DATABASE_URL         |
|                    v                     |
|  +-----------------------------------+  |
|  | MANAGED POSTGRESQL                |  |
|  | innovateus_j690                   |  |
|  | Auto-backups, connection pooling  |  |
|  +-----------------------------------+  |
|                                          |
+------------------------------------------+
```

### 14.2 Deploy-on-Push

- Both services auto-deploy when code is pushed to `main` branch on GitHub
- Backend startup sequence: `alembic upgrade head` (migrations) -> `python seed.py` (default data) -> `uvicorn` (start server)

### 14.3 Environment Variables

| Variable | Service | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | Backend | PostgreSQL connection (internal Render URL) |
| `OPENAI_API_KEY` | Backend | All AI features (GPT-4o, GPT-4o-mini, Whisper) |
| `JWT_SECRET` | Backend | Token signing + IP hash salt |
| `ADMIN_PASSWORD_HASH` | Backend | bcrypt hash for manager login |
| `EDITOR_PASSWORD_HASH` | Backend | bcrypt hash for editor login |
| `CORS_ORIGINS` | Backend | Exact frontend origin URL |
| `ENVIRONMENT` | Backend | "production" -- controls cookie security, SQL echo, seed behavior |
| `PYTHON_VERSION` | Backend | "3.11.6" -- pins runtime version |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend URL (baked into bundle at build time) |
| `NODE_VERSION` | Frontend | "20.11.0" -- pins runtime version |

---

## 15. API Endpoint Reference

### 15.1 Public Endpoints (No Auth Required)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/survey/{cohort_id}` | Get randomized survey config for a cohort |
| POST | `/v1/submissions/start` | Start or resume a submission (IP checked) |
| POST | `/v1/submissions/{id}/answer` | Save a single answer |
| POST | `/v1/submissions/{id}/complete` | Complete submission + trigger AI extraction |
| POST | `/v1/transcribe` | Transcribe audio via Whisper |
| POST | `/v1/ai/vagueness` | Check if answer is vague |
| POST | `/v1/ai/followups` | Generate follow-up questions |

### 15.2 Admin Endpoints (JWT Required, role: manager)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/admin/login` | Admin login |
| GET | `/v1/admin/cohorts` | List all programs/cohorts |
| POST | `/v1/admin/cohorts` | Create a new program |
| POST | `/v1/admin/cohorts/{id}/settings` | Update cohort settings (e.g., max submissions) |
| GET | `/v1/admin/metrics` | Dashboard metrics (filterable by cohort, date, version) |
| GET | `/v1/admin/responses` | Paginated response list |
| DELETE | `/v1/admin/responses` | Delete all responses (optional cohort filter) |
| GET | `/v1/admin/export/raw.csv` | Export raw answers as CSV |
| GET | `/v1/admin/export/structured.csv` | Export AI extractions as CSV |
| GET | `/v1/admin/export/summary.pdf` | Export PDF report |
| GET | `/v1/admin/export/summary.pptx` | Export PowerPoint deck |

### 15.3 Editor Endpoints (JWT Required, role: editor)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/admin/editor/login` | Editor login |
| GET | `/v1/admin/editor/survey/{cohort_id}` | Get survey config for editing |
| PUT | `/v1/admin/editor/survey/{cohort_id}` | Save survey config (auto-versioning) |
| GET | `/v1/admin/editor/survey/{cohort_id}/versions` | List version history |
| GET | `/v1/admin/editor/survey/{cohort_id}/versions/{label}` | Get specific version |
| POST | `/v1/admin/editor/survey/{cohort_id}/versions/{label}/restore` | Restore a version |

---

## 16. Cost Analysis

### 16.1 Per Submission (Estimated)

| Component | When | Estimated Cost |
|-----------|------|---------------|
| Whisper transcription | Per voice answer (~30 sec audio) | ~$0.003 |
| Vagueness check | Per open-ended answer | ~$0.00015 |
| Follow-up generation | Only if vague (~30% of open answers) | ~$0.0003 |
| Structured extraction | Once per completed submission | ~$0.01 |
| **Total per submission** | | **~$0.015 - $0.025** |

### 16.2 Infrastructure (Monthly)

| Service | Plan | Cost |
|---------|------|------|
| Render Web Service x2 | Free / Standard | $0 - $50/month |
| Render PostgreSQL | Free / Starter | $0 - $20/month |
| OpenAI API | Pay-as-you-go | ~$5-50/month (depends on volume) |

---

## 17. Known Issues & Open Backend Questions

### 17.1 Critical Issues We Are Investigating

1. **Export uses hardcoded default survey config**  
   The export service reads question metadata from `docs/survey-config/survey-en.json` on disk instead of from the cohort's actual `survey_config` in the database. If the survey has been edited, export column headers may be stale or wrong.  
   *Question: Should we refactor exports to always read the cohort's live config from PostgreSQL?*

2. **Export file path broken on Render**  
   The `DEFAULT_SURVEY_PATH` in `admin.py` resolves relative to the source file. On Render, the working directory differs from local development, and the path may not resolve correctly.  
   *Question: What is the most robust way to handle file paths that work both locally and on Render?*

3. **Dashboard catch-all error redirects to login**  
   Any API error (network timeout, 500, validation error) in the dashboard triggers a redirect to the login page, because the error handler can't distinguish "401 Unauthorized" from other failures.  
   *Question: Should we implement error-type-specific handling (only redirect on 401, show error toast for other failures)?*

4. **AI/Transcribe endpoints have no authentication**  
   `POST /v1/ai/vagueness`, `POST /v1/ai/followups`, and `POST /v1/transcribe` are publicly accessible with no auth. Anyone with the URL could call them, consuming OpenAI API credits.  
   *Question: Should we add rate limiting, API key validation, or tie these to an active submission_id?*

5. **Shared IP problem for same-WiFi users**  
   Multiple users on the same WiFi network share a public IP address. The second person would be incorrectly blocked by ballot-box stuffing protection.  
   *Question: What alternative fingerprinting or per-user identification can we use while maintaining full anonymity?*

### 17.2 High Priority Issues

6. **Answer resume does not restore previous answers**  
   When a user resumes an incomplete submission, the backend returns the old `submission_id` but the frontend doesn't fetch/restore previously saved answers. The user sees blank questions again.

7. **Randomization can break answer resume**  
   Since question order is re-randomized on every `GET /survey/{cohort_id}` call, a resumed session may show questions in a different order than when answers were originally saved.

8. **`complete_submission` can be called multiple times**  
   There is no check to prevent completing an already-completed submission. Calling it again would re-run the GPT-4o extraction and overwrite the extraction data.

9. **No rate limiting on any endpoint**  
   The API has no rate limiting middleware. A single client could send unlimited requests.

10. **sessionStorage-dependent "Done" page**  
    The post-survey "What We Heard" page reads extraction data from `sessionStorage`. If the user refreshes or opens in a new tab, the data is lost and the page breaks.

### 17.3 Medium Priority Issues

11. **No unsaved-changes warning in the survey editor**  
    Navigating away from the editor with unsaved changes causes silent data loss.

12. **Free-text version filter in dashboard**  
    The version filter is a text input, not a dropdown. Users must know exact version labels (e.g., "v3") to filter.

13. **No survey preview in editor**  
    Editors cannot preview what the survey looks like to participants without publishing changes.

14. **Structured respondent ID counter is fragile**  
    The respondent ID uses sequential numbering that depends on query order and pagination, which could produce duplicates under concurrent submissions.

### 17.4 Questions for Discussion

- **Scaling**: If we expect 500+ concurrent submissions, should we move to connection pooling (pgbouncer) or add Redis caching?
- **Offline support**: Should we support offline survey completion (PWA with local storage sync)?
- **Multi-language AI**: Our AI prompts are English-only. If Spanish-speaking participants use the Spanish UI, should vagueness detection and extraction also be multilingual?
- **Whisper model upgrades**: OpenAI has released newer speech models. Should we evaluate `whisper-large-v3` or the new `gpt-4o-audio` capabilities for better accuracy?
- **Data retention policy**: How long should we retain completed submission data? Should we implement automatic purging after a configurable period?

---

*This document was prepared for the InnovateUS Public Voice prototype architecture review. For questions or updates, refer to the GitHub repository or contact the development team.*
