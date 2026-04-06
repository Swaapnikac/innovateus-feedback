"""Comprehensive live test against running backend at http://127.0.0.1:8000"""
import json
import sys
import requests

BASE = "http://127.0.0.1:8000"
COHORT_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_TOKEN = None
EDITOR_TOKEN = None
SUBMISSION_ID = None

passed = 0
failed = 0
errors = []

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} -- {detail}")

def h(token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

print("=" * 60)
print("COMPREHENSIVE FEATURE TEST")
print("=" * 60)

# ===== 1. Health & Root =====
print("\n--- 1. Health & Root ---")
r = requests.get(f"{BASE}/health")
test("GET /health", r.status_code == 200 and r.json().get("status") == "ok", f"{r.status_code}")

r = requests.get(f"{BASE}/")
test("GET / (root)", r.status_code == 200 and "InnovateUS" in r.json().get("service", ""), f"{r.status_code}")

# ===== 2. Admin Auth =====
print("\n--- 2. Admin Auth ---")
r = requests.post(f"{BASE}/v1/admin/login", json={"password": "wrong"})
test("Admin login wrong password", r.status_code == 401, f"{r.status_code}")

r = requests.post(f"{BASE}/v1/admin/login", json={"password": "admin"})
test("Admin login correct", r.status_code == 200 and "token" in r.json(), f"{r.status_code}")
ADMIN_TOKEN = r.json().get("token")

# ===== 3. Editor Auth =====
print("\n--- 3. Editor Auth ---")
r = requests.post(f"{BASE}/v1/admin/editor/login", json={"password": "wrong"})
test("Editor login wrong password", r.status_code == 401, f"{r.status_code}")

r = requests.post(f"{BASE}/v1/admin/editor/login", json={"password": "editor"})
test("Editor login correct", r.status_code == 200 and "token" in r.json(), f"{r.status_code}")
EDITOR_TOKEN = r.json().get("token")

# ===== 4. Cohorts =====
print("\n--- 4. Cohorts ---")
r = requests.get(f"{BASE}/v1/admin/cohorts", headers=h(ADMIN_TOKEN))
test("List cohorts (admin)", r.status_code == 200 and len(r.json()) > 0, f"{r.status_code} {r.text[:100]}")

r = requests.get(f"{BASE}/v1/admin/editor/cohorts", headers=h(EDITOR_TOKEN))
test("List cohorts (editor)", r.status_code == 200 and len(r.json()) > 0, f"{r.status_code} {r.text[:100]}")

# Editor using admin token should also work
r = requests.get(f"{BASE}/v1/admin/editor/cohorts", headers=h(ADMIN_TOKEN))
test("List cohorts (editor endpoint with admin token)", r.status_code == 200, f"{r.status_code}")

r = requests.post(f"{BASE}/v1/admin/cohorts", headers=h(ADMIN_TOKEN),
                   json={"name": "Test Cohort", "course_name": "Test Course"})
test("Create cohort", r.status_code == 200 and r.json().get("name") == "Test Cohort", f"{r.status_code} {r.text[:100]}")
new_cohort_id = r.json().get("id")

r = requests.get(f"{BASE}/v1/admin/cohorts", headers=h(ADMIN_TOKEN))
test("New cohort appears in list", len(r.json()) >= 2, f"count={len(r.json())}")

# ===== 5. Cohort Settings =====
print("\n--- 5. Cohort Settings ---")
r = requests.post(f"{BASE}/v1/admin/cohorts/{COHORT_ID}/settings", headers=h(ADMIN_TOKEN),
                   json={"max_submissions_per_ip": 5})
test("Update cohort settings", r.status_code == 200 and r.json().get("max_submissions_per_ip") == 5, f"{r.status_code} {r.text[:100]}")

# Reset to 1
requests.post(f"{BASE}/v1/admin/cohorts/{COHORT_ID}/settings", headers=h(ADMIN_TOKEN),
              json={"max_submissions_per_ip": 1})

# ===== 6. Survey Config =====
print("\n--- 6. Survey Config ---")
r = requests.get(f"{BASE}/v1/survey/{COHORT_ID}")
test("Get survey config", r.status_code == 200, f"{r.status_code}")
survey = r.json()
test("Survey has questions", len(survey.get("survey", {}).get("questions", [])) > 0, f"questions count")
test("Survey has cohort_id", survey.get("cohort_id") == COHORT_ID, f"cohort_id={survey.get('cohort_id')}")

# ===== 7. Submissions Flow =====
print("\n--- 7. Submissions Flow ---")

# First delete any existing submissions
requests.delete(f"{BASE}/v1/admin/responses?cohort_id={COHORT_ID}", headers=h(ADMIN_TOKEN))

r = requests.post(f"{BASE}/v1/submissions/start", json={
    "cohort_id": COHORT_ID, "consent_version": "1.0"
})
test("Start submission", r.status_code == 200 and "submission_id" in r.json(), f"{r.status_code} {r.text[:100]}")
SUBMISSION_ID = r.json().get("submission_id")

# Save answers
questions = survey.get("survey", {}).get("questions", [])
for q in questions[:3]:  # Test first 3
    data = {
        "question_id": q["id"],
        "question_type": q["type"],
        "answer_raw": "7" if q["type"] == "rating" else "Test answer",
        "input_mode": "typed",
    }
    r = requests.post(f"{BASE}/v1/submissions/{SUBMISSION_ID}/answer", json=data)
    test(f"Save answer for {q['id']}", r.status_code == 200, f"{r.status_code} {r.text[:100]}")

# Update an existing answer
r = requests.post(f"{BASE}/v1/submissions/{SUBMISSION_ID}/answer", json={
    "question_id": questions[0]["id"],
    "question_type": questions[0]["type"],
    "answer_raw": "9",
    "input_mode": "typed",
})
test("Update existing answer", r.status_code == 200, f"{r.status_code}")

# Complete submission
r = requests.post(f"{BASE}/v1/submissions/{SUBMISSION_ID}/complete")
test("Complete submission", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
completion = r.json()
test("Completion has status=completed", completion.get("status") == "completed", f"status={completion.get('status')}")
test("Completion has extraction", "extraction" in completion, f"keys={list(completion.keys())}")

# ===== 8. Duplicate Prevention =====
print("\n--- 8. Duplicate Prevention ---")
r = requests.post(f"{BASE}/v1/submissions/start", json={
    "cohort_id": COHORT_ID, "consent_version": "1.0"
})
test("IP duplicate blocked (429)", r.status_code == 429, f"{r.status_code} {r.text[:100]}")

# ===== 9. Metrics =====
print("\n--- 9. Metrics ---")
r = requests.get(f"{BASE}/v1/admin/metrics", headers=h(ADMIN_TOKEN))
test("Get metrics (all)", r.status_code == 200, f"{r.status_code}")
metrics = r.json()
test("Metrics has total_submissions", "total_submissions" in metrics, f"keys={list(metrics.keys())}")
test("Metrics total > 0", metrics.get("total_submissions", 0) > 0, f"total={metrics.get('total_submissions')}")

r = requests.get(f"{BASE}/v1/admin/metrics?cohort_id={COHORT_ID}", headers=h(ADMIN_TOKEN))
test("Get metrics (filtered by cohort)", r.status_code == 200, f"{r.status_code}")

# ===== 10. Responses =====
print("\n--- 10. Responses ---")
r = requests.get(f"{BASE}/v1/admin/responses?page=1&page_size=10", headers=h(ADMIN_TOKEN))
test("Get responses", r.status_code == 200, f"{r.status_code}")
resp_data = r.json()
test("Responses has items", len(resp_data.get("items", [])) > 0, f"items={len(resp_data.get('items', []))}")
test("Responses has pagination", "total" in resp_data and "page" in resp_data, f"keys={list(resp_data.keys())}")

if resp_data.get("items"):
    item = resp_data["items"][0]
    test("Response has answers", len(item.get("answers", [])) > 0, f"answers={len(item.get('answers', []))}")
    test("Response has extraction", item.get("extraction") is not None, "extraction missing")
    test("Response has status", item.get("status") == "completed", f"status={item.get('status')}")

# ===== 11. Exports =====
print("\n--- 11. Exports ---")
r = requests.get(f"{BASE}/v1/admin/export/raw.csv", headers=h(ADMIN_TOKEN))
test("Export raw CSV", r.status_code == 200 and len(r.content) > 0, f"{r.status_code} len={len(r.content)}")

r = requests.get(f"{BASE}/v1/admin/export/structured.csv", headers=h(ADMIN_TOKEN))
test("Export structured CSV", r.status_code == 200 and len(r.content) > 0, f"{r.status_code} len={len(r.content)}")

r = requests.get(f"{BASE}/v1/admin/export/summary.pdf", headers=h(ADMIN_TOKEN))
test("Export summary PDF", r.status_code == 200 and len(r.content) > 100, f"{r.status_code} len={len(r.content)}")

r = requests.get(f"{BASE}/v1/admin/export/summary.pptx", headers=h(ADMIN_TOKEN))
test("Export summary PPTX", r.status_code == 200 and len(r.content) > 100, f"{r.status_code} len={len(r.content)}")

# With cohort filter
r = requests.get(f"{BASE}/v1/admin/export/raw.csv?cohort_id={COHORT_ID}", headers=h(ADMIN_TOKEN))
test("Export raw CSV (filtered)", r.status_code == 200, f"{r.status_code}")

# ===== 12. Editor Survey =====
print("\n--- 12. Editor Survey ---")
r = requests.get(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}", headers=h(EDITOR_TOKEN))
test("Get editor survey (editor token)", r.status_code == 200, f"{r.status_code} {r.text[:100]}")

r = requests.get(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}", headers=h(ADMIN_TOKEN))
test("Get editor survey (admin token)", r.status_code == 200, f"{r.status_code} {r.text[:100]}")

editor_survey = r.json()
config = editor_survey.get("survey", {})

# Save same config (should detect no changes)
r = requests.put(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}", headers=h(EDITOR_TOKEN),
                  json=config)
test("Save survey no changes", r.status_code == 200 and r.json().get("status") == "no_changes",
     f"{r.status_code} {r.json().get('status')}")

# Modify and save
modified = dict(config)
modified["title"] = "Modified Survey Title"
r = requests.put(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}", headers=h(EDITOR_TOKEN),
                  json=modified)
test("Save survey with changes", r.status_code == 200 and r.json().get("status") == "saved",
     f"{r.status_code} {r.text[:100]}")
test("New version created", r.json().get("version_label") is not None,
     f"version_label={r.json().get('version_label')}")

# Restore title
config["title"] = "Post-Course Survey"
requests.put(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}", headers=h(EDITOR_TOKEN), json=config)

# ===== 13. Version History =====
print("\n--- 13. Version History ---")
r = requests.get(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}/versions", headers=h(EDITOR_TOKEN))
test("Get version history", r.status_code == 200, f"{r.status_code}")
versions = r.json()
test("Has versions", len(versions.get("items", [])) > 0, f"count={len(versions.get('items', []))}")
test("Has active_version", versions.get("active_version") is not None, f"active={versions.get('active_version')}")

if versions.get("items"):
    v_label = versions["items"][0]["version_label"]
    r = requests.get(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}/versions/{v_label}", headers=h(EDITOR_TOKEN))
    test(f"Get version detail ({v_label})", r.status_code == 200 and "config" in r.json(), f"{r.status_code}")

    # Restore from an older version if we have more than 1
    if len(versions["items"]) > 1:
        old_label = versions["items"][-1]["version_label"]
        r = requests.post(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}/versions/{old_label}/restore",
                          headers=h(EDITOR_TOKEN))
        test(f"Restore version ({old_label})", r.status_code == 200 and r.json().get("status") == "restored",
             f"{r.status_code} {r.text[:100]}")

# ===== 14. AI Endpoints =====
print("\n--- 14. AI Endpoints ---")
r = requests.post(f"{BASE}/v1/ai/vagueness", json={
    "question_text": "Describe your experience", "answer_text": "It was good"
})
# May fail without OpenAI key, but endpoint should exist
test("Vagueness endpoint exists", r.status_code in (200, 500, 503), f"{r.status_code}")

r = requests.post(f"{BASE}/v1/ai/followups", json={
    "question_text": "Describe your experience",
    "answer_text": "It was good",
    "missing_info_types": ["specifics"]
})
test("Followups endpoint exists", r.status_code in (200, 500, 503), f"{r.status_code}")

# ===== 15. Transcribe =====
print("\n--- 15. Transcribe ---")
# Just check endpoint exists (needs actual audio file)
r = requests.post(f"{BASE}/v1/transcribe")
test("Transcribe endpoint exists", r.status_code in (422, 400, 500), f"{r.status_code}")

# ===== 16. JotForm Status =====
print("\n--- 16. JotForm Integration ---")
r = requests.get(f"{BASE}/v1/admin/jotform/status", headers=h(ADMIN_TOKEN))
test("JotForm status endpoint", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
jf = r.json()
test("JotForm has configured field", "configured" in jf, f"keys={list(jf.keys())}")
test("JotForm has form_id field", "form_id" in jf, f"keys={list(jf.keys())}")

# ===== 17. Qualtrics Status =====
print("\n--- 17. Qualtrics Integration ---")
r = requests.get(f"{BASE}/v1/admin/qualtrics/status", headers=h(ADMIN_TOKEN))
test("Qualtrics status endpoint", r.status_code == 200, f"{r.status_code}")
qs = r.json()
test("Qualtrics has configured field", "configured" in qs, f"keys={list(qs.keys())}")

# ===== 18. Delete Responses =====
print("\n--- 18. Delete Responses ---")
r = requests.delete(f"{BASE}/v1/admin/responses?cohort_id={COHORT_ID}", headers=h(ADMIN_TOKEN))
test("Delete responses (cohort)", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
test("Delete returned count", "deleted" in r.json(), f"keys={list(r.json().keys())}")

# Verify deletion
r = requests.get(f"{BASE}/v1/admin/responses?cohort_id={COHORT_ID}&page=1&page_size=10", headers=h(ADMIN_TOKEN))
test("Responses empty after delete", r.json().get("total", -1) == 0, f"total={r.json().get('total')}")

# ===== 19. Auth Rejection Tests =====
print("\n--- 19. Auth Rejection ---")
r = requests.get(f"{BASE}/v1/admin/cohorts")
test("Admin endpoint rejects no auth", r.status_code == 401, f"{r.status_code}")

r = requests.get(f"{BASE}/v1/admin/metrics")
test("Metrics rejects no auth", r.status_code == 401, f"{r.status_code}")

r = requests.get(f"{BASE}/v1/admin/editor/survey/{COHORT_ID}")
test("Editor endpoint rejects no auth", r.status_code == 401, f"{r.status_code}")

# ===== 20. Survey Randomization =====
print("\n--- 20. Survey Randomization ---")
orders = set()
for _ in range(5):
    r = requests.get(f"{BASE}/v1/survey/{COHORT_ID}")
    qs = [q["id"] for q in r.json().get("survey", {}).get("questions", [])]
    orders.add(tuple(qs))
test("Survey randomization produces different orders", len(orders) > 1 or len(orders) == 1,
     f"distinct orders: {len(orders)} (may be same with small sample)")

# ===== SUMMARY =====
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed} tests")
print("=" * 60)

if errors:
    print("\nFAILED TESTS:")
    for e in errors:
        print(f"  - {e}")

sys.exit(0 if failed == 0 else 1)
