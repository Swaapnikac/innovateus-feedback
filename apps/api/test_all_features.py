"""
Comprehensive test of ALL InnovateUS features on DynamoDB.

Uses moto to mock DynamoDB in-memory (no AWS account needed).
Tests every user-facing and admin endpoint end-to-end.
"""
import os
import json
import uuid

# Must set env vars BEFORE importing app modules
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["DYNAMODB_ENDPOINT_URL"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_PASSWORD_HASH"] = "$2b$12$LJ3m4ys3Lz0YHGsEhGQJ2u6VZ3P7QX5X8X5X8X5X8X5X8X5X8X5X8"
os.environ["EDITOR_PASSWORD_HASH"] = "$2b$12$LJ3m4ys3Lz0YHGsEhGQJ2u6VZ3P7QX5X8X5X8X5X8X5X8X5X8X5X8"

import boto3
from moto import mock_aws
from fastapi.testclient import TestClient

# ── Results tracking ──────────────────────────────────────────────────
results = []
def log_test(feature: str, endpoint: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append((feature, endpoint, status, detail))
    icon = "+" if passed else "X"
    print(f"  {icon} {status}: {feature}")
    if detail and not passed:
        print(f"         {detail}")


# ── Start moto mock ──────────────────────────────────────────────────
@mock_aws
def run_all_tests():
    # Create DynamoDB tables
    dynamodb = boto3.client("dynamodb", region_name="us-east-1")

    dynamodb.create_table(
        TableName="innovateus-surveys",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    dynamodb.create_table(
        TableName="innovateus-submissions",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "ip_hash", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "IpHashIndex",
                "KeySchema": [
                    {"AttributeName": "ip_hash", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    print("DynamoDB tables created.\n")

    # Import app AFTER moto is active
    from app.main import app
    client = TestClient(app)

    # ══════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("SECTION 1: HEALTH & ROOT ENDPOINTS")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 1.1: Health check
    r = client.get("/health")
    log_test("Health check", "GET /health", r.status_code == 200 and r.json()["status"] == "ok")

    # Test 1.2: Root endpoint
    r = client.get("/")
    data = r.json()
    log_test("Root endpoint", "GET /", r.status_code == 200 and data.get("database") == "DynamoDB")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 2: ADMIN AUTH")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 2.1: Admin login with wrong password
    r = client.post("/v1/admin/login", json={"password": "wrong"})
    log_test("Admin login - wrong password", "POST /v1/admin/login", r.status_code == 401)

    # Test 2.2: We need a real hash. Generate one.
    import bcrypt
    real_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
    editor_hash = bcrypt.hashpw(b"editor123", bcrypt.gensalt()).decode()

    # Patch settings
    from app.config import get_settings
    settings = get_settings()
    settings.admin_password_hash = real_hash
    settings.editor_password_hash = editor_hash

    r = client.post("/v1/admin/login", json={"password": "admin123"})
    log_test("Admin login - correct password", "POST /v1/admin/login", r.status_code == 200 and "token" in r.json())
    admin_token = r.json().get("token", "")

    # Test 2.3: Editor login
    r = client.post("/v1/admin/editor/login", json={"password": "editor123"})
    log_test("Editor login - correct password", "POST /v1/admin/editor/login", r.status_code == 200 and "token" in r.json())
    editor_token = r.json().get("token", "")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    editor_headers = {"Authorization": f"Bearer {editor_token}"}

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 3: COHORT MANAGEMENT (Admin)")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 3.1: List cohorts (empty)
    r = client.get("/v1/admin/cohorts", headers=admin_headers)
    log_test("List cohorts - empty", "GET /v1/admin/cohorts", r.status_code == 200 and len(r.json()) == 0)

    # Test 3.2: Create cohort
    r = client.post("/v1/admin/cohorts", json={"name": "Spring 2026", "course_name": "AI for Government"}, headers=admin_headers)
    log_test("Create cohort", "POST /v1/admin/cohorts", r.status_code == 200 and r.json().get("name") == "Spring 2026")
    cohort_id = r.json().get("id")

    # Test 3.3: Create second cohort
    r = client.post("/v1/admin/cohorts", json={"name": "Fall 2026", "course_name": "Data Science Basics"}, headers=admin_headers)
    log_test("Create second cohort", "POST /v1/admin/cohorts", r.status_code == 200)
    cohort_id_2 = r.json().get("id")

    # Test 3.4: List cohorts (should have 2)
    r = client.get("/v1/admin/cohorts", headers=admin_headers)
    log_test("List cohorts - has 2", "GET /v1/admin/cohorts", r.status_code == 200 and len(r.json()) == 2)

    # Test 3.5: Update cohort settings
    r = client.post(f"/v1/admin/cohorts/{cohort_id}/settings", json={"max_submissions_per_ip": 3}, headers=admin_headers)
    log_test("Update cohort settings", f"POST /v1/admin/cohorts/.../settings", r.status_code == 200 and r.json().get("max_submissions_per_ip") == 3)

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 4: SURVEY CONFIG (Public + Editor)")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 4.1: Get survey config (public)
    r = client.get(f"/v1/survey/{cohort_id}")
    log_test("Get survey config (public)", f"GET /v1/survey/{{cohort_id}}", r.status_code == 200 and "survey" in r.json())
    survey_data = r.json().get("survey", {})
    has_questions = len(survey_data.get("questions", [])) > 0
    log_test("Survey has questions", "survey.questions", has_questions, f"Got {len(survey_data.get('questions', []))} questions")

    # Test 4.2: Get survey via editor
    r = client.get(f"/v1/admin/editor/survey/{cohort_id}", headers=editor_headers)
    log_test("Get editor survey", f"GET /v1/admin/editor/survey/{{cohort_id}}", r.status_code == 200 and r.json().get("active_version") == "v1")

    # Test 4.3: Save survey (update title)
    survey_config = r.json()["survey"]
    survey_config["title"] = "Updated Survey Title"
    r = client.put(f"/v1/admin/editor/survey/{cohort_id}", json=survey_config, headers=editor_headers)
    log_test("Save survey config", f"PUT /v1/admin/editor/survey/{{cohort_id}}", r.status_code == 200 and r.json().get("version_label") == "v2")

    # Test 4.4: Save same config again (no changes)
    r = client.put(f"/v1/admin/editor/survey/{cohort_id}", json=survey_config, headers=editor_headers)
    log_test("Save survey - no changes detected", "PUT (no changes)", r.status_code == 200 and r.json().get("status") == "no_changes")

    # Test 4.5: List versions
    r = client.get(f"/v1/admin/editor/survey/{cohort_id}/versions", headers=editor_headers)
    log_test("List survey versions", f"GET .../versions", r.status_code == 200 and r.json().get("total") == 2)

    # Test 4.6: Get specific version
    r = client.get(f"/v1/admin/editor/survey/{cohort_id}/versions/v1", headers=editor_headers)
    log_test("Get specific version (v1)", "GET .../versions/v1", r.status_code == 200 and "config" in r.json())

    # Test 4.7: Restore version
    r = client.post(f"/v1/admin/editor/survey/{cohort_id}/versions/v1/restore", headers=editor_headers)
    log_test("Restore version v1", "POST .../v1/restore", r.status_code == 200 and r.json().get("version_label") == "v3")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 5: FEEDBACK SUBMISSION FLOW (User-Facing)")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 5.1: Start submission
    r = client.post("/v1/submissions/start", json={
        "cohort_id": cohort_id,
        "consent_version": "1.0",
        "client_metadata": {"browser": "Chrome", "os": "Windows"}
    })
    log_test("Start submission", "POST /v1/submissions/start", r.status_code == 200 and "submission_id" in r.json())
    submission_id = r.json().get("submission_id")

    # Test 5.2: Resume same submission (same IP)
    r = client.post("/v1/submissions/start", json={"cohort_id": cohort_id, "consent_version": "1.0"})
    log_test("Resume existing submission (same IP)", "POST /v1/submissions/start", r.status_code == 200 and r.json().get("submission_id") == submission_id)

    # Test 5.3: Save rating answer
    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q1_recommend",
        "question_type": "rating",
        "answer_raw": "8",
        "input_mode": "text",
    })
    log_test("Save answer - rating (q1)", f"POST .../answer", r.status_code == 200 and r.json().get("question_id") == "q1_recommend")

    # Test 5.4: Save MCQ answer
    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q2_confidence",
        "question_type": "mcq",
        "answer_raw": "Very confident",
        "input_mode": "text",
    })
    log_test("Save answer - MCQ (q2)", f"POST .../answer", r.status_code == 200)

    # Test 5.5: Save multi-select answer
    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q4_likely_uses",
        "question_type": "multi",
        "answer_raw": json.dumps(["Create content", "Conduct research"]),
        "input_mode": "text",
    })
    log_test("Save answer - multi-select (q4)", f"POST .../answer", r.status_code == 200)

    # Test 5.6: Save open-ended answer with vagueness + followup
    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q6_most_impactful",
        "question_type": "open",
        "answer_raw": "I learned about AI tools and how to use them effectively in my daily work.",
        "input_mode": "voice",
        "transcript": "I learned about AI tools and how to use them effectively in my daily work.",
        "is_vague": True,
        "followups_asked": 1,
        "followup_1": "Can you give a specific example of an AI tool you plan to use?",
        "followup_1_answer": "I plan to use ChatGPT to draft policy memos faster.",
    })
    log_test("Save answer - open-ended with followup (q6)", f"POST .../answer", r.status_code == 200)

    # Test 5.7: Save another open-ended answer
    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q7_prepared_task",
        "question_type": "open",
        "answer_raw": "Writing weekly status reports using AI assistance",
        "input_mode": "text",
    })
    log_test("Save answer - open (q7)", f"POST .../answer", r.status_code == 200)

    # Test 5.8: Save MCQ answers for remaining questions
    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q3_clarity",
        "question_type": "mcq",
        "answer_raw": "Yes",
        "input_mode": "text",
    })
    log_test("Save answer - MCQ (q3)", f"POST .../answer", r.status_code == 200)

    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q5_impact",
        "question_type": "mcq",
        "answer_raw": "Easier",
        "input_mode": "text",
    })
    log_test("Save answer - MCQ (q5)", f"POST .../answer", r.status_code == 200)

    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q8_exercises",
        "question_type": "mcq",
        "answer_raw": "Yes, I completed all of the exercises",
        "input_mode": "text",
    })
    log_test("Save answer - MCQ (q8)", f"POST .../answer", r.status_code == 200)

    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q9_feedback",
        "question_type": "open",
        "answer_raw": "Great course, very well structured. Would recommend to colleagues.",
        "input_mode": "text",
    })
    log_test("Save answer - open (q9)", f"POST .../answer", r.status_code == 200)

    # Test 5.9: Update an existing answer (go back and change)
    r = client.post(f"/v1/submissions/{submission_id}/answer", json={
        "question_id": "q1_recommend",
        "question_type": "rating",
        "answer_raw": "9",
        "input_mode": "text",
    })
    log_test("Update existing answer (q1: 8->9)", f"POST .../answer", r.status_code == 200)

    # Test 5.10: Complete submission
    r = client.post(f"/v1/submissions/{submission_id}/complete")
    log_test("Complete submission", f"POST .../complete",
             r.status_code == 200 and r.json().get("status") == "completed")
    extraction = r.json().get("extraction")
    log_test("Extraction returned on completion", "extraction in response",
             extraction is not None,
             f"Keys: {list(extraction.keys()) if extraction else 'None'}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 6: SECOND SUBMISSION (Different user)")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Simulate different IP by using X-Forwarded-For
    r = client.post("/v1/submissions/start",
        json={"cohort_id": cohort_id, "consent_version": "1.0"},
        headers={"X-Forwarded-For": "10.0.0.2"}
    )
    log_test("Start 2nd submission (different IP)", "POST /v1/submissions/start", r.status_code == 200)
    sub2_id = r.json().get("submission_id")

    # Quick answers
    for q_id, q_type, answer in [
        ("q1_recommend", "rating", "7"),
        ("q2_confidence", "mcq", "Somewhat confident"),
        ("q3_clarity", "mcq", "Somewhat"),
        ("q5_impact", "mcq", "Easier"),
        ("q6_most_impactful", "open", "The hands-on exercises were great"),
        ("q7_prepared_task", "open", "Automating data entry"),
        ("q9_feedback", "open", "Could use more examples"),
    ]:
        client.post(f"/v1/submissions/{sub2_id}/answer", json={
            "question_id": q_id, "question_type": q_type,
            "answer_raw": answer, "input_mode": "text",
        })

    r = client.post(f"/v1/submissions/{sub2_id}/complete")
    log_test("Complete 2nd submission", "POST .../complete", r.status_code == 200 and r.json().get("status") == "completed")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 7: SUBMISSION FOR 2nd COHORT")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    r = client.post("/v1/submissions/start",
        json={"cohort_id": cohort_id_2, "consent_version": "1.0"},
        headers={"X-Forwarded-For": "10.0.0.3"}
    )
    log_test("Start submission for 2nd cohort", "POST /v1/submissions/start", r.status_code == 200)
    sub3_id = r.json().get("submission_id")

    for q_id, q_type, answer in [
        ("q1_recommend", "rating", "6"),
        ("q2_confidence", "mcq", "A little confident"),
        ("q9_feedback", "open", "Needs improvement in pacing"),
    ]:
        client.post(f"/v1/submissions/{sub3_id}/answer", json={
            "question_id": q_id, "question_type": q_type,
            "answer_raw": answer, "input_mode": "text",
        })

    r = client.post(f"/v1/submissions/{sub3_id}/complete")
    log_test("Complete 3rd submission (2nd cohort)", "POST .../complete", r.status_code == 200)

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 8: DUPLICATE SUBMISSION PROTECTION")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # cohort_id_2 has max_submissions_per_ip=1 (default)
    r = client.post("/v1/submissions/start",
        json={"cohort_id": cohort_id_2, "consent_version": "1.0"},
        headers={"X-Forwarded-For": "10.0.0.3"}  # Same IP as sub3
    )
    log_test("Duplicate blocked (same IP, same cohort)", "POST /v1/submissions/start",
             r.status_code == 429,
             f"Got status {r.status_code}: {r.json().get('detail', '')}")

    # cohort_id has max_submissions_per_ip=3, so same IP can submit again
    r = client.post("/v1/submissions/start",
        json={"cohort_id": cohort_id, "consent_version": "1.0"},
        headers={"X-Forwarded-For": "10.0.0.2"}  # Same IP as sub2, but limit=3
    )
    log_test("Allowed (same IP, limit=3, only 1 completed)", "POST /v1/submissions/start",
             r.status_code == 200)

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 9: ADMIN DASHBOARD - METRICS")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 9.1: Metrics for all cohorts
    r = client.get("/v1/admin/metrics", headers=admin_headers)
    data = r.json()
    log_test("Metrics - all cohorts", "GET /v1/admin/metrics",
             r.status_code == 200 and data.get("total_submissions") == 3,
             f"total={data.get('total_submissions')}, completed={data.get('completed_submissions')}")

    log_test("Metrics - completion rate", "completion_rate",
             data.get("completed_submissions") == 3 and data.get("completion_rate") > 0)

    log_test("Metrics - avg recommend score", "avg_recommend_score",
             data.get("avg_recommend_score") is not None,
             f"Score: {data.get('avg_recommend_score')}")

    log_test("Metrics - confidence distribution", "confidence_distribution",
             len(data.get("confidence_distribution", {})) > 0,
             f"Distribution: {data.get('confidence_distribution')}")

    log_test("Metrics - vagueness rate", "vagueness_rate",
             data.get("vagueness_rate") is not None,
             f"Rate: {data.get('vagueness_rate')}")

    # Test 9.2: Metrics filtered by cohort
    r = client.get(f"/v1/admin/metrics?cohort_id={cohort_id}", headers=admin_headers)
    data = r.json()
    log_test("Metrics - filtered by cohort 1", "GET /v1/admin/metrics?cohort_id=...",
             r.status_code == 200 and data.get("total_submissions") == 2,
             f"total={data.get('total_submissions')}")

    # Test 9.3: Metrics for cohort 2
    r = client.get(f"/v1/admin/metrics?cohort_id={cohort_id_2}", headers=admin_headers)
    data = r.json()
    log_test("Metrics - filtered by cohort 2", "GET /v1/admin/metrics?cohort_id=...",
             r.status_code == 200 and data.get("total_submissions") == 1,
             f"total={data.get('total_submissions')}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 10: ADMIN DASHBOARD - PAGINATED RESPONSES")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 10.1: Get all responses
    r = client.get("/v1/admin/responses", headers=admin_headers)
    data = r.json()
    log_test("Paginated responses - all", "GET /v1/admin/responses",
             r.status_code == 200 and data.get("total") == 3,
             f"total={data.get('total')}, page_items={len(data.get('items', []))}")

    # Test 10.2: Check response has embedded answers
    if data.get("items"):
        first_item = data["items"][0]
        has_answers = len(first_item.get("answers", [])) > 0
        has_extraction = first_item.get("extraction") is not None
        log_test("Response has embedded answers", "items[0].answers",
                 has_answers, f"answer_count={len(first_item.get('answers', []))}")
        log_test("Response has extraction", "items[0].extraction", has_extraction)

    # Test 10.3: Paginated responses filtered by cohort
    r = client.get(f"/v1/admin/responses?cohort_id={cohort_id}", headers=admin_headers)
    data = r.json()
    log_test("Responses - filtered by cohort", "GET /v1/admin/responses?cohort_id=...",
             r.status_code == 200 and data.get("total") == 2,
             f"total={data.get('total')}")

    # Test 10.4: Pagination
    r = client.get(f"/v1/admin/responses?page=1&page_size=1", headers=admin_headers)
    data = r.json()
    log_test("Responses - pagination (page_size=1)", "page_size=1",
             r.status_code == 200 and len(data.get("items", [])) == 1 and data.get("total") == 3,
             f"items={len(data.get('items', []))}, total={data.get('total')}")

    r = client.get(f"/v1/admin/responses?page=2&page_size=1", headers=admin_headers)
    data = r.json()
    log_test("Responses - pagination (page 2)", "page=2",
             r.status_code == 200 and len(data.get("items", [])) == 1)

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 11: EXPORTS")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 11.1: Raw CSV export
    r = client.get(f"/v1/admin/export/raw.csv?cohort_id={cohort_id}", headers=admin_headers)
    log_test("Export - Raw CSV", "GET /v1/admin/export/raw.csv",
             r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""),
             f"Size: {len(r.content)} bytes")
    csv_content = r.content.decode()
    csv_lines = csv_content.strip().split("\n")
    log_test("Raw CSV - has header + data rows", "csv rows",
             len(csv_lines) >= 3,  # header + 2 submissions
             f"Lines: {len(csv_lines)}")

    # Test 11.2: Structured CSV export
    r = client.get(f"/v1/admin/export/structured.csv?cohort_id={cohort_id}", headers=admin_headers)
    log_test("Export - Structured CSV", "GET /v1/admin/export/structured.csv",
             r.status_code == 200 and len(r.content) > 100,
             f"Size: {len(r.content)} bytes")

    # Test 11.3: PDF export
    r = client.get(f"/v1/admin/export/summary.pdf?cohort_id={cohort_id}", headers=admin_headers)
    log_test("Export - PDF", "GET /v1/admin/export/summary.pdf",
             r.status_code == 200 and r.content[:4] == b"%PDF",
             f"Size: {len(r.content)} bytes, starts with: {r.content[:4]}")

    # Test 11.4: PPTX export
    r = client.get(f"/v1/admin/export/summary.pptx?cohort_id={cohort_id}", headers=admin_headers)
    log_test("Export - PPTX", "GET /v1/admin/export/summary.pptx",
             r.status_code == 200 and len(r.content) > 1000,
             f"Size: {len(r.content)} bytes")

    # Test 11.5: Export all cohorts (no filter)
    r = client.get("/v1/admin/export/raw.csv", headers=admin_headers)
    csv_lines = r.content.decode().strip().split("\n")
    log_test("Export - Raw CSV (all cohorts)", "GET /v1/admin/export/raw.csv",
             r.status_code == 200 and len(csv_lines) >= 4,  # header + 3 submissions
             f"Lines: {len(csv_lines)}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 12: AI FEATURES (No OpenAI key = graceful fallback)")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 12.1: Vagueness detection (no API key - should return graceful fallback)
    r = client.post("/v1/ai/vagueness", json={
        "question_text": "What did you learn?",
        "answer_text": "It was good"
    })
    log_test("AI vagueness check (no key - fallback)", "POST /v1/ai/vagueness",
             r.status_code == 200 and "is_vague" in r.json(),
             f"Result: {r.json()}")

    # Test 12.2: Follow-up generation (no API key - should return empty)
    r = client.post("/v1/ai/followups", json={
        "question_text": "What did you learn?",
        "answer_text": "It was good",
        "missing_info_types": ["specificity"]
    })
    log_test("AI followups (no key - fallback)", "POST /v1/ai/followups",
             r.status_code == 200 and "followups" in r.json(),
             f"Result: {r.json()}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 13: QUALTRICS STATUS")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    r = client.get("/v1/admin/qualtrics/status", headers=admin_headers)
    log_test("Qualtrics status (not configured)", "GET /v1/admin/qualtrics/status",
             r.status_code == 200 and r.json().get("configured") is False)

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 14: DELETE RESPONSES")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 14.1: Delete responses for cohort 2 only
    r = client.delete(f"/v1/admin/responses?cohort_id={cohort_id_2}", headers=admin_headers)
    log_test("Delete responses - cohort 2", "DELETE /v1/admin/responses?cohort_id=...",
             r.status_code == 200 and r.json().get("deleted") == 1,
             f"deleted={r.json().get('deleted')}")

    # Test 14.2: Verify cohort 1 still has data
    r = client.get(f"/v1/admin/metrics?cohort_id={cohort_id}", headers=admin_headers)
    log_test("Cohort 1 data intact after cohort 2 delete", "GET /v1/admin/metrics",
             r.status_code == 200 and r.json().get("total_submissions") == 2)

    # Test 14.3: Verify cohort 2 is empty
    r = client.get(f"/v1/admin/metrics?cohort_id={cohort_id_2}", headers=admin_headers)
    log_test("Cohort 2 empty after delete", "GET /v1/admin/metrics",
             r.status_code == 200 and r.json().get("total_submissions") == 0)

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 15: AUTH PROTECTION")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Clear cookies from prior login so auth tests work correctly
    client.cookies.clear()

    # Test 15.1: Admin endpoints without token
    r = client.get("/v1/admin/cohorts")
    log_test("Admin endpoint without token -> 401", "GET /v1/admin/cohorts (no auth)", r.status_code == 401)

    # Test 15.2: Editor endpoints without token
    r = client.get(f"/v1/admin/editor/survey/{cohort_id}")
    log_test("Editor endpoint without token -> 401", "GET .../editor/survey (no auth)", r.status_code == 401)

    # Test 15.3: Invalid token
    r = client.get("/v1/admin/cohorts", headers={"Authorization": "Bearer invalid-token"})
    log_test("Invalid token -> 401", "GET /v1/admin/cohorts (bad token)", r.status_code == 401)

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SECTION 16: EDGE CASES")
    print("=" * 60)
    # ══════════════════════════════════════════════════════════════════

    # Test 16.1: Non-existent cohort
    fake_id = str(uuid.uuid4())
    r = client.get(f"/v1/survey/{fake_id}")
    log_test("Non-existent cohort -> fallback to default survey", f"GET /v1/survey/{{fake_id}}",
             r.status_code == 200)  # Falls back to default survey

    # Test 16.2: Non-existent submission
    r = client.post(f"/v1/submissions/{fake_id}/answer", json={
        "question_id": "q1", "question_type": "rating", "answer_raw": "5", "input_mode": "text"
    })
    log_test("Non-existent submission -> 404", "POST .../answer (fake id)", r.status_code == 404)

    # Test 16.3: Non-existent cohort settings update
    r = client.post(f"/v1/admin/cohorts/{fake_id}/settings", json={"max_submissions_per_ip": 1}, headers=admin_headers)
    log_test("Non-existent cohort settings -> 404", "POST .../settings (fake id)", r.status_code == 404)

    # Test 16.4: Non-existent version
    r = client.get(f"/v1/admin/editor/survey/{cohort_id}/versions/v99", headers=editor_headers)
    log_test("Non-existent version -> 404", "GET .../versions/v99", r.status_code == 404)

    # ══════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    total_tests = len(results)
    passed = sum(1 for _, _, s, _ in results if s == "PASS")
    failed = sum(1 for _, _, s, _ in results if s == "FAIL")

    print(f"\n  Total tests:  {total_tests}")
    print(f"  Passed:       {passed}")
    print(f"  Failed:       {failed}")

    if failed > 0:
        print(f"\n  FAILED TESTS:")
        for feature, endpoint, status, detail in results:
            if status == "FAIL":
                print(f"    X {feature} ({endpoint})")
                if detail:
                    print(f"      -> {detail}")

    print(f"\n  Result: {'ALL TESTS PASSED!' if failed == 0 else f'{failed} TESTS FAILED'}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
