# InnovateUS Feedback Platform - AWS Architecture

## High-Level Architecture Overview

```
                                    USERS (Browser)
                                         |
                                         v
                              +---------------------+
                              |    CloudFront CDN    |
                              |  (Static Frontend)   |
                              +---------------------+
                                         |
                          +--------------+--------------+
                          |                             |
                          v                             v
                   +-------------+              +-------------+
                   |   S3 Bucket |              | API Gateway  |
                   | (Next.js    |              | (REST API)   |
                   |  Static     |              | /v1/*        |
                   |  Export)    |              +-------------+
                   +-------------+                    |
                                                      v
                          +---------------------------+---------------------------+
                          |              |              |              |           |
                          v              v              v              v           v
                   +-----------+  +-----------+  +-----------+  +-----------+  +-----------+
                   | Lambda:   |  | Lambda:   |  | Lambda:   |  | Lambda:   |  | Lambda:   |
                   | Survey    |  | Submit    |  | AI        |  | Admin     |  | Editor    |
                   | Service   |  | Service   |  | Service   |  | Service   |  | Service   |
                   +-----------+  +-----------+  +-----------+  +-----------+  +-----------+
                          |              |              |              |           |
                          v              v              v              v           v
                   +----------------------------------------------------------------+
                   |                        DynamoDB                                 |
                   |   +------------------------+  +-----------------------------+   |
                   |   | innovateus-surveys     |  | innovateus-submissions      |   |
                   |   | (Cohorts + Versions)   |  | (Submissions + Answers)     |   |
                   |   +------------------------+  +-----------------------------+   |
                   +----------------------------------------------------------------+
                                                      |
                                    +-----------------+-----------------+
                                    |                                   |
                                    v                                   v
                          +------------------+                +------------------+
                          |  OpenAI API      |                | Qualtrics /      |
                          |  (GPT-4o, Whisper)|               | JotForm APIs     |
                          +------------------+                +------------------+
```

---

## Detailed Lambda Architecture

### Overview: 7 Lambda Functions

Instead of 20+ micro-Lambdas (which adds cold start overhead and deployment complexity), the architecture groups related endpoints into **7 logical Lambda functions** using the Mangum adapter (FastAPI on Lambda).

```
API Gateway (HTTP API)
    |
    +-- /v1/survey/*           --> Lambda 1: Survey Service
    +-- /v1/submissions/*      --> Lambda 2: Submission Service
    +-- /v1/ai/*               --> Lambda 3: AI Service
    +-- /v1/transcribe         --> Lambda 4: Transcribe Service
    +-- /v1/admin/*            --> Lambda 5: Admin Service
    +-- /v1/admin/editor/*     --> Lambda 6: Editor Service
    +-- /v1/admin/export/*     --> Lambda 7: Export Service
```

---

## Lambda 1: Survey Service

**Purpose:** Serve survey configuration to end users

```
Trigger:  API Gateway
Routes:   GET /v1/survey/{cohort_id}
Memory:   256 MB
Timeout:  10 seconds
```

**Flow:**
```
Browser Request
    |
    v
API Gateway --> Lambda 1
    |
    v
DynamoDB: get_item(COHORT#{id}, METADATA)
    |
    v
Randomize questions within groups
    |
    v
Return JSON survey config
```

**What it does:**
- Reads cohort metadata from DynamoDB surveys table
- Gets the active survey_config
- Randomizes questions within groups (respects conditional dependencies)
- Returns survey JSON with Cache-Control: no-store

**DynamoDB Access:** READ only (surveys table)
**External APIs:** None
**Cold Start Impact:** Low (fast, lightweight)

---

## Lambda 2: Submission Service

**Purpose:** Handle the full survey submission lifecycle

```
Trigger:  API Gateway
Routes:   POST /v1/submissions/start
          POST /v1/submissions/{id}/answer
          POST /v1/submissions/{id}/complete
Memory:   512 MB
Timeout:  60 seconds (extraction can take time)
```

**Flow - Start Submission:**
```
POST /v1/submissions/start
    |
    v
Get cohort metadata (max_submissions_per_ip)
    |
    v
Hash client IP (SHA256 with salt)
    |
    v
Query IpHashIndex GSI: check completed count
    |
    +-- >= limit? --> 429 "Already submitted"
    |
    +-- Check for in-progress submission
    |       |
    |       +-- Found? --> Return existing submission_id
    |
    v
Create new submission in DynamoDB
    |
    v
Return { submission_id }
```

**Flow - Save Answer:**
```
POST /v1/submissions/{id}/answer
    |
    v
Find submission by scan (submission_id)
    |
    v
Upsert answer in embedded answers array
    |
    v
Update DynamoDB item
    |
    v
Return { id, question_id }
```

**Flow - Complete Submission:**
```
POST /v1/submissions/{id}/complete
    |
    v
Find submission from DynamoDB
    |
    v
Gather all answers for extraction
    |
    +---> OpenAI GPT-4o: extract_structured()
    |     (what_was_tried, barriers, enablers,
    |      themes, success_story, etc.)
    |
    v
Update submission:
  - status = "completed"
  - completed_at = now
  - time_to_complete_sec = calculated
  - extraction = AI result
    |
    v
Attempt Qualtrics sync (non-blocking)
    |
    v
Set duplicate-prevention cookie
    |
    v
Return { status: "completed", extraction }
```

**DynamoDB Access:** READ + WRITE (both tables)
**External APIs:** OpenAI (GPT-4o for extraction), Qualtrics (auto-sync)
**Why 512MB:** AI extraction payload can be large; JSON parsing needs memory

---

## Lambda 3: AI Service

**Purpose:** Real-time AI analysis during survey (vagueness + followups)

```
Trigger:  API Gateway
Routes:   POST /v1/ai/vagueness
          POST /v1/ai/followups
Memory:   256 MB
Timeout:  30 seconds
```

**Flow - Vagueness Check:**
```
POST /v1/ai/vagueness
  { question_text, answer_text }
    |
    v
OpenAI GPT-4o-mini (temperature=0.1)
  System prompt: detect vagueness
  JSON mode response
    |
    v
Return {
  is_vague: true/false,
  reason: "...",
  missing_info_types: ["specifics", "examples", ...]
}
```

**Flow - Follow-up Generation:**
```
POST /v1/ai/followups
  { question_text, answer_text, missing_info_types }
    |
    v
OpenAI GPT-4o-mini (temperature=0.3)
  System prompt: generate probing followups
  JSON mode response
    |
    v
Return { followups: ["Question 1?", "Question 2?"] }
```

**DynamoDB Access:** None
**External APIs:** OpenAI (GPT-4o-mini)
**Why separate Lambda:** Isolates AI latency from other operations; can scale independently during high survey traffic

---

## Lambda 4: Transcribe Service

**Purpose:** Convert voice recordings to text

```
Trigger:  API Gateway
Routes:   POST /v1/transcribe
Memory:   512 MB
Timeout:  30 seconds
```

**Flow:**
```
POST /v1/transcribe
  (multipart/form-data: audio file)
    |
    v
Read audio blob from request
    |
    v
OpenAI Whisper API (model: whisper-1)
    |
    v
Return { transcript: "..." }
```

**DynamoDB Access:** None
**External APIs:** OpenAI Whisper
**Why separate Lambda:** Audio processing needs more memory; different scaling pattern (only used by voice-input users)

---

## Lambda 5: Admin Service

**Purpose:** Dashboard, metrics, cohort management, pipeline integrations

```
Trigger:  API Gateway
Routes:   POST /v1/admin/login
          GET  /v1/admin/cohorts
          POST /v1/admin/cohorts
          POST /v1/admin/cohorts/{id}/settings
          GET  /v1/admin/metrics
          GET  /v1/admin/responses
          DELETE /v1/admin/responses
          GET  /v1/admin/qualtrics/status
          POST /v1/admin/qualtrics/sync/{id}
          POST /v1/admin/qualtrics/sync-all
          GET  /v1/admin/jotform/status
          POST /v1/admin/jotform/sync/{id}
          POST /v1/admin/jotform/sync-all
Memory:   512 MB
Timeout:  120 seconds (bulk sync can take time)
```

**Flow - Metrics:**
```
GET /v1/admin/metrics?cohort_id=...&start=...&end=...
    |
    v
Verify JWT (admin_token cookie or Bearer header)
    |
    v
Query/Scan DynamoDB submissions table
    |
    v
Filter by cohort_id, date range, survey_version
    |
    v
Compute in Python:
  - total_submissions, completed_submissions
  - completion_rate
  - avg_time_to_complete_sec
  - avg_recommend_score (q1_recommend)
  - confidence_distribution (q2_confidence)
  - vagueness_rate (open-ended answers)
    |
    v
Return MetricsResponse
```

**Flow - Qualtrics Bulk Sync:**
```
POST /v1/admin/qualtrics/sync-all?force=false
    |
    v
Load all completed submissions
    |
    v
Filter: skip already-synced (unless force=true)
    |
    v
For each submission:
    +---> Build Qualtrics payload (field mapping + recode)
    +---> POST to Qualtrics Response Import API
    +---> On success: update qualtrics_synced_at
    |
    v
Return { total, synced, failed, errors[] }
```

**DynamoDB Access:** READ + WRITE (both tables)
**External APIs:** Qualtrics API, JotForm API
**Auth:** JWT Bearer token or cookie

---

## Lambda 6: Editor Service

**Purpose:** Survey question editor with version control

```
Trigger:  API Gateway
Routes:   POST /v1/admin/editor/login
          GET  /v1/admin/editor/cohorts
          GET  /v1/admin/editor/survey/{cohort_id}
          PUT  /v1/admin/editor/survey/{cohort_id}
          GET  /v1/admin/editor/survey/{cohort_id}/versions
          GET  /v1/admin/editor/survey/{cohort_id}/versions/{label}
          POST /v1/admin/editor/survey/{cohort_id}/versions/{label}/restore
Memory:   256 MB
Timeout:  15 seconds
```

**Flow - Save Survey:**
```
PUT /v1/admin/editor/survey/{cohort_id}
  { version, title, questions[], question_groups[] }
    |
    v
Verify JWT (editor or admin role)
    |
    v
Get current cohort from DynamoDB
    |
    v
Compare new config vs current (deep JSON compare)
    |
    +-- No changes? --> Return { status: "no_changes" }
    |
    v
Auto-generate change summary:
  "Changed survey title; Added: q10_new; Changed text: q3_clarity"
    |
    v
Create VERSION#{next_version} item in DynamoDB
    |
    v
Update METADATA with new survey_config + active_version
    |
    v
Return { status: "saved", version_label: "v4" }
```

**Flow - Restore Version:**
```
POST .../versions/v2/restore
    |
    v
Read old version config from DynamoDB
    |
    v
Create new VERSION#{next} with old config
    |
    v
Update METADATA with restored config
    |
    v
Return { status: "restored", version_label: "v5", restored_from: "v2" }
```

**DynamoDB Access:** READ + WRITE (surveys table)
**External APIs:** None

---

## Lambda 7: Export Service

**Purpose:** Generate downloadable reports (CSV, PDF, PPTX)

```
Trigger:  API Gateway
Routes:   GET /v1/admin/export/raw.csv
          GET /v1/admin/export/structured.csv
          GET /v1/admin/export/summary.pdf
          GET /v1/admin/export/summary.pptx
Memory:   1024 MB
Timeout:  60 seconds
```

**Flow:**
```
GET /v1/admin/export/summary.pdf?cohort_id=...&start=...&end=...
    |
    v
Verify JWT (admin)
    |
    v
Fetch all matching submissions from DynamoDB
    |
    v
Filter: completed only, apply date range
    |
    v
Generate report:
  +-- raw.csv:        Flat CSV, one row per answer
  +-- structured.csv: One row per respondent with followups
  +-- summary.pdf:    Branded PDF with metrics, themes, barriers
  +-- summary.pptx:   6-slide PowerPoint presentation
    |
    v
Return StreamingResponse with file
```

**DynamoDB Access:** READ (submissions table, surveys table for cohort name)
**External APIs:** None
**Why 1024MB:** PDF/PPTX generation with reportlab and python-pptx needs memory; large datasets need buffer space
**Why separate Lambda:** Export can be slow for large datasets; isolation prevents blocking other endpoints

---

## DynamoDB Table Design

### Table 1: innovateus-surveys

```
+---------------------------+------------------+----------------------------------+
| pk (Partition Key)        | sk (Sort Key)    | Attributes                       |
+---------------------------+------------------+----------------------------------+
| COHORT#uuid-1             | METADATA         | name, course_name,               |
|                           |                  | survey_config, active_version,   |
|                           |                  | max_submissions_per_ip,          |
|                           |                  | created_at                       |
+---------------------------+------------------+----------------------------------+
| COHORT#uuid-1             | VERSION#v1       | config, change_summary,          |
|                           |                  | created_by, created_at           |
+---------------------------+------------------+----------------------------------+
| COHORT#uuid-1             | VERSION#v2       | config, change_summary,          |
|                           |                  | created_by, created_at           |
+---------------------------+------------------+----------------------------------+
| COHORT#uuid-2             | METADATA         | ...                              |
+---------------------------+------------------+----------------------------------+

Billing: PAY_PER_REQUEST (on-demand)
No GSIs needed
```

### Table 2: innovateus-submissions

```
+---------------------------+------------------+----------------------------------+
| pk (Partition Key)        | sk (Sort Key)    | Attributes                       |
+---------------------------+------------------+----------------------------------+
| COHORT#uuid-1             | SUB#sub-uuid-1   | submission_id, cohort_id,        |
|                           |                  | status, created_at, completed_at,|
|                           |                  | time_to_complete_sec,            |
|                           |                  | consent_version, survey_version, |
|                           |                  | ip_hash, answers[], extraction,  |
|                           |                  | jotform_synced_at,               |
|                           |                  | qualtrics_synced_at              |
+---------------------------+------------------+----------------------------------+

Billing: PAY_PER_REQUEST (on-demand)

GSI: IpHashIndex
  Partition Key: ip_hash (String)
  Sort Key: created_at (String)
  Projection: ALL
  Purpose: Fast duplicate detection per IP
```

---

## Complete Request Flow Diagrams

### Flow 1: User Takes Survey (End-to-End)

```
Step 1: User opens survey link
  Browser --> CloudFront --> S3 (Next.js static)
  Page: /c/{cohortId} (Consent page)

Step 2: User accepts consent
  Browser --> API Gateway --> Lambda 1 (Survey)
  GET /v1/survey/{cohortId}
  Returns: survey config with randomized questions

  Browser --> API Gateway --> Lambda 2 (Submission)
  POST /v1/submissions/start
  Returns: { submission_id }

Step 3: User answers each question
  For each question:
    |
    +-- Browser --> API Gateway --> Lambda 2
    |   POST /v1/submissions/{id}/answer
    |   Saves answer incrementally
    |
    +-- If open-ended question with voice:
    |     Browser --> API Gateway --> Lambda 4 (Transcribe)
    |     POST /v1/transcribe (audio file)
    |     Returns: { transcript }
    |
    +-- If open-ended & voice-eligible:
    |     Browser --> API Gateway --> Lambda 3 (AI)
    |     POST /v1/ai/vagueness
    |     Returns: { is_vague, missing_info_types }
    |
    +-- If vague:
          Browser --> API Gateway --> Lambda 3 (AI)
          POST /v1/ai/followups
          Returns: { followups: ["Q1?", "Q2?"] }

Step 4: User completes survey
  Browser --> API Gateway --> Lambda 2 (Submission)
  POST /v1/submissions/{id}/complete
    |
    +-- Lambda 2 calls OpenAI GPT-4o (extraction)
    +-- Lambda 2 calls Qualtrics API (auto-sync)
    +-- Returns: { status: "completed", extraction }

Step 5: Thank you page
  Browser shows extraction summary (from Step 4 response)
```

### Flow 2: Admin Views Dashboard

```
Step 1: Admin logs in
  Browser --> API Gateway --> Lambda 5 (Admin)
  POST /v1/admin/login { password }
  Returns: { token } + sets admin_token cookie

Step 2: Dashboard loads
  Browser --> API Gateway --> Lambda 5 (Admin)
  Parallel requests:
    GET /v1/admin/cohorts
    GET /v1/admin/metrics?cohort_id=...&start=...&end=...
    GET /v1/admin/responses?page=1&page_size=10

Step 3: Admin exports data
  Browser --> API Gateway --> Lambda 7 (Export)
  GET /v1/admin/export/summary.pdf?cohort_id=...
  Returns: PDF binary stream --> Browser downloads file

Step 4: Admin triggers Qualtrics sync
  Browser --> API Gateway --> Lambda 5 (Admin)
  POST /v1/admin/qualtrics/sync-all?force=false
    |
    +-- For each unsynced submission:
    |     POST to Qualtrics API
    |
    v
  Returns: { total: 50, synced: 48, failed: 2, errors: [...] }
```

### Flow 3: Editor Modifies Survey

```
Step 1: Editor logs in
  Browser --> API Gateway --> Lambda 6 (Editor)
  POST /v1/admin/editor/login { password }
  Returns: { token }

Step 2: Editor page loads
  Browser --> API Gateway --> Lambda 6 (Editor)
  GET /v1/admin/editor/cohorts
  GET /v1/admin/editor/survey/{cohortId}
  GET /v1/admin/editor/survey/{cohortId}/versions

Step 3: Editor saves changes
  Browser --> API Gateway --> Lambda 6 (Editor)
  PUT /v1/admin/editor/survey/{cohortId}
    |
    v
  Creates VERSION#v5 in DynamoDB
  Updates METADATA with new config
  Returns: { status: "saved", version_label: "v5" }

Step 4: Editor restores old version
  Browser --> API Gateway --> Lambda 6 (Editor)
  POST .../versions/v2/restore
  Returns: { status: "restored", version_label: "v6" }
```

---

## AWS Services Used

| Service | Purpose | Cost Estimate |
|---------|---------|---------------|
| **API Gateway (HTTP API)** | Route requests to Lambdas | ~$1/million requests |
| **Lambda (x7)** | Run backend logic | Free tier: 1M requests + 400K GB-sec/month |
| **DynamoDB (x2 tables)** | Data storage | Free tier: 25 GB + 25 RCU/WCU |
| **S3** | Host Next.js static site | ~$0.023/GB/month |
| **CloudFront** | CDN for frontend + API caching | Free tier: 1TB/month |
| **IAM** | Permissions & roles | Free |
| **CloudWatch** | Logs & monitoring | Free tier: 5GB logs |
| **Secrets Manager** (optional) | Store API keys securely | $0.40/secret/month |

### Estimated Monthly Cost

| Component | Your Scale (~100-500 submissions/month) |
|-----------|---------------------------------------|
| Lambda | $0 (free tier) |
| DynamoDB | $0 (free tier) |
| API Gateway | $0 (free tier covers 1M requests) |
| S3 + CloudFront | $0-1 |
| **OpenAI API** | ~$2-10 (GPT-4o extraction + vagueness checks) |
| **Total AWS** | **~$0-1/month** |
| **Total with OpenAI** | **~$2-11/month** |

---

## Lambda Configuration Summary

| Lambda | Memory | Timeout | Env Vars |
|--------|--------|---------|----------|
| 1. Survey Service | 256 MB | 10s | AWS_REGION, SURVEYS_TABLE |
| 2. Submission Service | 512 MB | 60s | AWS_REGION, ALL_TABLES, OPENAI_API_KEY, QUALTRICS_*, JWT_SECRET |
| 3. AI Service | 256 MB | 30s | OPENAI_API_KEY |
| 4. Transcribe Service | 512 MB | 30s | OPENAI_API_KEY |
| 5. Admin Service | 512 MB | 120s | AWS_REGION, ALL_TABLES, JWT_SECRET, ADMIN_PASSWORD_HASH, QUALTRICS_*, JOTFORM_* |
| 6. Editor Service | 256 MB | 15s | AWS_REGION, SURVEYS_TABLE, JWT_SECRET, EDITOR_PASSWORD_HASH |
| 7. Export Service | 1024 MB | 60s | AWS_REGION, ALL_TABLES, JWT_SECRET, ADMIN_PASSWORD_HASH |

---

## IAM Roles (Least Privilege)

### Lambda-Survey-Role
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem"],
  "Resource": "arn:aws:dynamodb:*:*:table/innovateus-surveys"
}
```

### Lambda-Submission-Role
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:Scan"],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/innovateus-surveys",
    "arn:aws:dynamodb:*:*:table/innovateus-submissions",
    "arn:aws:dynamodb:*:*:table/innovateus-submissions/index/IpHashIndex"
  ]
}
```

### Lambda-Admin-Role
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:BatchWriteItem"],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/innovateus-surveys",
    "arn:aws:dynamodb:*:*:table/innovateus-submissions",
    "arn:aws:dynamodb:*:*:table/innovateus-submissions/index/IpHashIndex"
  ]
}
```

### Lambda-Editor-Role
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:Scan"],
  "Resource": "arn:aws:dynamodb:*:*:table/innovateus-surveys"
}
```

### Lambda-Export-Role
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/innovateus-surveys",
    "arn:aws:dynamodb:*:*:table/innovateus-submissions"
  ]
}
```

---

## Deployment Architecture

```
GitHub Repository
    |
    v
GitHub Actions (CI/CD)
    |
    +-- Build Next.js --> Deploy to S3 + CloudFront invalidation
    |
    +-- Package Lambda code --> Deploy via AWS SAM / CDK / Terraform
    |
    +-- Run tests --> Gate deployments on test pass
```

### Deployment Options

| Tool | Complexity | Best For |
|------|-----------|----------|
| **AWS SAM** | Low | Quick Lambda + API Gateway setup |
| **AWS CDK (Python)** | Medium | Full infrastructure as code |
| **Terraform** | Medium | Multi-cloud, team standard |
| **Serverless Framework** | Low | Fast iteration, good DX |

---

## Alternative: Single Lambda (Simpler)

If managing 7 Lambdas feels complex, you can deploy the **entire FastAPI app as a single Lambda** using Mangum (which is already in your code):

```
API Gateway (HTTP API)
    |
    +-- ANY /{proxy+} --> Single Lambda (FastAPI + Mangum)
```

**Pros:** Simpler deployment, one package, one set of env vars
**Cons:** Cold starts affect all routes, can't independently scale AI vs admin

**Recommendation:** Start with a single Lambda, split into multiple when you need to optimize cold starts or scale specific functions independently.

---

## Security Architecture

```
+------------------------------------------+
|              CloudFront                   |
|  - HTTPS only (TLS 1.2+)               |
|  - Custom domain + ACM certificate      |
|  - WAF integration (optional)           |
+------------------------------------------+
              |
              v
+------------------------------------------+
|           API Gateway                     |
|  - CORS configured per origin            |
|  - Rate limiting (throttling)            |
|  - Request validation                    |
+------------------------------------------+
              |
              v
+------------------------------------------+
|            Lambda                         |
|  - JWT verification (HS256)              |
|  - Role-based access (admin/editor)      |
|  - IP hashing (SHA256 + salt)            |
|  - No PII stored (IP hashed, no login)   |
|  - Audio never persisted (transcribe-only)|
+------------------------------------------+
              |
              v
+------------------------------------------+
|           DynamoDB                         |
|  - Encryption at rest (AWS managed)       |
|  - VPC endpoint (optional)                |
|  - IAM role-based access                  |
|  - Point-in-time recovery (enable)        |
|  - On-demand backup (enable)              |
+------------------------------------------+
```
