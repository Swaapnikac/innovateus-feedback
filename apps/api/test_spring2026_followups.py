"""
End-to-end backend test for Spring AI Training 2026.

Exercises all voice/text combinations across initial open-ended answers and
follow-up answers, then verifies the data is visible in both:
  - Manager dashboard (/v1/admin/metrics, /v1/admin/responses)
  - User-testing dashboard (/v1/admin/user-testing-analytics)

Scenarios (each is one submission against Spring 2026):
  1. VOICE initial  + VOICE follow-up         ("V/V")
  2. VOICE initial  + TEXT  follow-up         ("V/T")
  3. TEXT  initial  + VOICE follow-up         ("T/V")
  4. TEXT  initial  + TEXT  follow-up         ("T/T")

Each submission answers every survey question (closed + open), runs the
vagueness detector on the open-ended answers, fetches AI-generated follow-up
questions when appropriate, and submits follow-up answers in the scenario's
input mode. The script ends by logging in as admin and dumping the relevant
dashboard numbers so you can eyeball that the runs landed.

Run:

    cd apps/api
    .\\venv\\Scripts\\python.exe test_spring2026_followups.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

API_BASE = os.environ.get("API_BASE", "http://localhost:8002")
SPRING_COHORT_ID = "2c73b4fc-765f-4279-98fa-9a0df4e6a25e"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
CYAN = "\x1b[36m"
DIM = "\x1b[2m"


def ok(msg: str) -> None:
    print(f"  {GREEN}[OK]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}[!!]{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}[XX]{RESET} {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}== {title} =={RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario definitions
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Scenario:
    label: str
    initial_mode: str          # "voice" | "text"
    followup_mode: str         # "voice" | "text"
    vague_answer: str          # short, intentionally vague -> triggers follow-ups
    good_followup: str         # detailed follow-up answer
    rich_answer: str           # detailed initial answer (for the last open question)


SCENARIOS: list[Scenario] = [
    Scenario(
        label="V/V (voice initial + voice follow-up)",
        initial_mode="voice",
        followup_mode="voice",
        vague_answer="I used it sometimes for writing.",
        good_followup=(
            "I used ChatGPT to draft outreach emails for our community program. "
            "I pasted my bullet points and asked it to rewrite them in a friendly "
            "tone. It cut my drafting time from about 30 minutes to 8 minutes per "
            "message, and my manager said the final version sounded clearer."
        ),
        rich_answer=(
            "I used a generative AI assistant to help summarize long policy memos "
            "into a one-page briefing for my team. I uploaded the PDF, asked for "
            "a plain-language summary with three bullet recommendations, and then "
            "I refined the tone. It saved me about two hours per memo and my team "
            "said the briefings were easier to act on."
        ),
    ),
    Scenario(
        label="V/T (voice initial + text follow-up)",
        initial_mode="voice",
        followup_mode="text",
        vague_answer="It helps me with emails.",
        good_followup=(
            "Specifically, I use it to soften the tone of reply emails to citizens "
            "who are frustrated. I paste the draft, ask for a warmer but still "
            "factual rewrite, and then I edit one or two lines. It reduced "
            "escalations that come back to my supervisor."
        ),
        rich_answer=(
            "One concrete workflow I now feel prepared to do is translating dense "
            "legal text into a plain-language FAQ for constituents. I use the model "
            "to draft a first pass, then I compare it against the original to catch "
            "anything it softened too much. That cross-check step was the biggest "
            "thing the course taught me."
        ),
    ),
    Scenario(
        label="T/V (text initial + voice follow-up)",
        initial_mode="text",
        followup_mode="voice",
        vague_answer="Useful stuff.",
        good_followup=(
            "The most useful thing was learning when NOT to use generative AI. "
            "For example I stopped using it for anything that involves personally "
            "identifiable information from case files, and I now always disclose "
            "when a draft was AI-assisted before I send it to my director."
        ),
        rich_answer=(
            "A specific task I feel better prepared to do is running short "
            "brainstorming sessions where the AI acts as a 'devil's advocate' on "
            "policy proposals. I learned to ask for counterarguments grounded in "
            "specific evidence rather than generic critique, and that is what I "
            "will bring back to my unit."
        ),
    ),
    Scenario(
        label="T/T (text initial + text follow-up)",
        initial_mode="text",
        followup_mode="text",
        vague_answer="Good course.",
        good_followup=(
            "What stuck with me was the lesson on prompt specificity — giving the "
            "model the role, the audience, and the format up front. I tried this "
            "the day after class on a briefing memo and the first draft was "
            "dramatically closer to what I needed."
        ),
        rich_answer=(
            "I plan to use generative AI for drafting internal training materials. "
            "I will start by outlining learning objectives, then ask the model to "
            "generate scenarios, quiz questions, and a facilitator guide. The "
            "course gave me the language to QA those outputs before sharing."
        ),
    ),
]


# Canned answers for the closed-ended / rating questions, aligned to the default
# survey-en.json that Spring 2026 uses.
CLOSED_ANSWERS: dict[str, dict[str, Any]] = {
    "q1_recommend": {"type": "rating", "answer": "9"},
    "q2_confidence": {"type": "mcq", "answer": "Somewhat confident"},
    "q3_clarity": {"type": "mcq", "answer": "Yes"},
    "q4_likely_uses": {
        "type": "multi",
        "answer": json.dumps(
            [
                "Create content (for example, text, images, audio, video)",
                "Summarize or synthesize text",
                "Conduct research",
            ]
        ),
    },
    "q5_impact": {"type": "mcq", "answer": "Easier"},
    "q8_exercises": {"type": "mcq", "answer": "Yes, I completed some of the exercises"},
}

OPEN_QUESTIONS_ORDER = ["q6_most_impactful", "q7_prepared_task", "q9_feedback"]


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────


class ApiClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        # Each scenario needs a unique IP so max_submissions_per_ip doesn't
        # block repeat runs on cohorts that have a cap. Spring 2026 is 0
        # (unlimited) but we still set a unique X-Forwarded-For for cleaner
        # dedup counts.
        self.headers: dict[str, str] = {}
        self._client = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self._client.aclose()

    def with_ip(self, ip: str) -> dict[str, str]:
        h = dict(self.headers)
        h["X-Forwarded-For"] = ip
        return h

    async def post(self, path: str, json_body: dict | None = None, headers: dict | None = None) -> dict:
        r = await self._client.post(f"{self.base}{path}", json=json_body, headers=headers or self.headers)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:400]}")
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return {"raw": r.text}

    async def get(self, path: str, params: dict | None = None, headers: dict | None = None) -> dict:
        r = await self._client.get(f"{self.base}{path}", params=params, headers=headers or self.headers)
        if r.status_code >= 400:
            raise RuntimeError(f"GET {path} -> {r.status_code}: {r.text[:400]}")
        return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Scenario runner
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    scenario: Scenario
    submission_id: str
    open_answer_modes: dict[str, str] = field(default_factory=dict)
    followup_modes: dict[str, str] = field(default_factory=dict)
    followups_shown: int = 0
    followups_answered: int = 0
    extraction: Optional[dict] = None


async def run_scenario(api: ApiClient, scenario: Scenario, run_index: int) -> RunResult:
    fake_ip = f"203.0.113.{10 + run_index}"  # TEST-NET-3; guarantees uniqueness
    ip_headers = api.with_ip(fake_ip)

    section(f"Scenario #{run_index + 1}: {scenario.label}")

    # 1) Fetch survey to learn current question order
    survey = await api.get(f"/v1/survey/{SPRING_COHORT_ID}", headers=ip_headers)
    questions = survey["survey"]["questions"]
    ok(f"Fetched survey ({len(questions)} questions)")

    # 2) Start submission
    started = await api.post(
        "/v1/submissions/start",
        {"cohort_id": SPRING_COHORT_ID, "consent_version": "1.0", "client_metadata": {"source": "test"}},
        headers=ip_headers,
    )
    submission_id = started["submission_id"]
    ok(f"Submission started: {submission_id}")

    # 3) Simulate client-env (H6 coverage)
    await api.post(
        f"/v1/submissions/{submission_id}/client-env",
        {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
            "screen_size": "1920x1080",
            "connection_type": "4g",
            "page_load_time_ms": 820,
            "voice_supported": True,
            "mic_permission_status": "granted" if "voice" in (scenario.initial_mode, scenario.followup_mode) else "prompt",
        },
        headers=ip_headers,
    )
    ok("client-env saved")

    result = RunResult(scenario=scenario, submission_id=submission_id)
    open_answers_seen = 0

    # 4) Answer every question in order
    for q in questions:
        qid = q["id"]
        qtype = q["type"]

        # ── Closed-ended ──
        if qid in CLOSED_ANSWERS:
            meta = CLOSED_ANSWERS[qid]
            await api.post(
                f"/v1/submissions/{submission_id}/answer",
                {
                    "question_id": qid,
                    "question_type": meta["type"],
                    "answer_raw": meta["answer"],
                    "input_mode": "none",
                },
                headers=ip_headers,
            )
            continue

        # ── Open-ended ──
        open_answers_seen += 1

        # Last open question gets a rich, non-vague answer for variety;
        # earlier open questions get a vague answer so we can exercise
        # follow-ups.
        is_last_open = open_answers_seen == len(
            [o for o in questions if o["type"] == "open"]
        )
        initial_text = scenario.rich_answer if is_last_open else scenario.vague_answer

        input_mode = scenario.initial_mode
        transcript_raw = initial_text if input_mode == "voice" else None
        voice_duration = 18 if input_mode == "voice" else None

        # 4a. Ask the combined vagueness + follow-ups endpoint (matches what the
        # live frontend does right after a voice answer is finalized).
        check = await api.post(
            "/v1/ai/check",
            {"question_text": q["text"], "answer_text": initial_text},
            headers=ip_headers,
        )
        is_vague = bool(check.get("is_vague"))
        followups_suggested: list[str] = check.get("followups") or []

        # 4b. Save the initial answer
        payload: dict[str, Any] = {
            "question_id": qid,
            "question_type": qtype,
            "answer_raw": initial_text,
            "input_mode": input_mode,
            "is_vague": is_vague,
        }
        if transcript_raw:
            payload["transcript_raw"] = transcript_raw
            payload["transcript"] = transcript_raw
        if voice_duration is not None:
            payload["voice_duration_sec"] = voice_duration
        await api.post(
            f"/v1/submissions/{submission_id}/answer", payload, headers=ip_headers
        )

        result.open_answer_modes[qid] = input_mode

        # 4c. If vague, answer up to two follow-ups in the scenario's follow-up mode
        if is_vague and followups_suggested:
            followups_to_use = followups_suggested[:2]
            fu_payload = dict(payload)
            fu_payload["followups_asked"] = len(followups_to_use)
            fu_payload["followup_1"] = followups_to_use[0]
            fu_payload["followup_1_answer"] = scenario.good_followup
            fu_payload["followup_1_input_mode"] = scenario.followup_mode
            if len(followups_to_use) > 1:
                fu_payload["followup_2"] = followups_to_use[1]
                fu_payload["followup_2_answer"] = scenario.good_followup
                fu_payload["followup_2_input_mode"] = scenario.followup_mode
            await api.post(
                f"/v1/submissions/{submission_id}/answer", fu_payload, headers=ip_headers
            )
            result.followups_shown += len(followups_to_use)
            result.followups_answered += len(followups_to_use)
            result.followup_modes[qid] = scenario.followup_mode
            ok(
                f"{qid}: initial={input_mode} vague=True  "
                f"followups={len(followups_to_use)} answered in {scenario.followup_mode}"
            )
        else:
            ok(f"{qid}: initial={input_mode} vague={is_vague} (no follow-ups)")

    # 5) Preview extraction (what the review page shows)
    preview = await api.post(
        f"/v1/submissions/{submission_id}/preview-extraction", None, headers=ip_headers
    )
    ok(f"Preview extraction: themes={preview.get('extraction', {}).get('top_themes')}")

    # 6) Save experience rating so the user-testing dashboard has data
    await api.post(
        f"/v1/submissions/{submission_id}/experience-rating",
        {
            "rating": 5 if scenario.followup_mode == "voice" else 4,
            "feedback_text": f"Scenario {scenario.label} — dashboards should see this.",
            "voice_experience_rating": 5 if scenario.initial_mode == "voice" or scenario.followup_mode == "voice" else None,
            "voice_experience_text": "Voice was fast and accurate." if scenario.initial_mode == "voice" else None,
            "would_use_again": True,
            "preferred_mode_next_time": "voice" if scenario.followup_mode == "voice" else "text",
            "confusion_flag": False,
            "reported_issue_flag": False,
        },
        headers=ip_headers,
    )
    ok("experience rating saved")

    # 7) Complete submission
    completed = await api.post(
        f"/v1/submissions/{submission_id}/complete", None, headers=ip_headers
    )
    result.extraction = completed.get("extraction")
    ok(f"Submission completed: status={completed.get('status')}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard verification
# ─────────────────────────────────────────────────────────────────────────────


async def admin_login(api: ApiClient, password: str) -> str:
    data = await api.post("/v1/admin/login", {"password": password})
    return data["token"]


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "–"
    return f"{x * 100:.1f}%"


def _get(obj: dict, *keys, default: Any = None) -> Any:
    cur: Any = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


async def verify_dashboards(api: ApiClient, runs: list[RunResult]) -> bool:
    section("Admin login")
    token = await admin_login(api, ADMIN_PASSWORD)
    admin_headers = {"Authorization": f"Bearer {token}"}
    ok("Admin login succeeded")

    # ── Manager dashboard: /v1/admin/metrics + /v1/admin/responses ──
    section("Manager dashboard (/v1/admin/metrics)")
    metrics = await api.get(
        "/v1/admin/metrics",
        params={"cohort_id": SPRING_COHORT_ID},
        headers=admin_headers,
    )
    print(f"    {json.dumps(metrics, indent=2)}")
    if metrics.get("completed_submissions", 0) < len(runs):
        warn(
            f"Expected >= {len(runs)} completed submissions; "
            f"dashboard shows {metrics.get('completed_submissions')}"
        )
    else:
        ok(f"completed_submissions={metrics['completed_submissions']} (>= {len(runs)})")
    if metrics.get("vagueness_rate") is not None:
        ok(f"vagueness_rate={_fmt_pct(metrics['vagueness_rate'])}")

    section("Manager dashboard (/v1/admin/responses)")
    responses = await api.get(
        "/v1/admin/responses",
        params={"cohort_id": SPRING_COHORT_ID, "page": 1, "page_size": 20},
        headers=admin_headers,
    )
    submission_ids_in_dashboard = {item["id"] for item in responses.get("items", [])}
    for r in runs:
        if r.submission_id in submission_ids_in_dashboard:
            ok(f"Submission {r.submission_id} visible ({r.scenario.label})")
        else:
            fail(f"Submission {r.submission_id} missing from dashboard ({r.scenario.label})")

    # ── User-testing dashboard: /v1/admin/user-testing-analytics ──
    section("User-testing dashboard (/v1/admin/user-testing-analytics)")
    ut = await api.get(
        "/v1/admin/user-testing-analytics",
        params={"cohort_id": SPRING_COHORT_ID},
        headers=admin_headers,
    )

    totals = ut.get("totals", {})
    executive = ut.get("executive", {})
    voice_vs_text = ut.get("voice_vs_text", {})
    followup_effectiveness = ut.get("followup_effectiveness", {})
    voice_ux = ut.get("voice_ux", {})

    print(
        "    totals:             ",
        json.dumps(totals, indent=None),
    )
    print(
        "    executive:          ",
        json.dumps(
            {
                k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in executive.items()
            },
            indent=None,
        ),
    )
    print(
        "    voice_vs_text:      ",
        json.dumps(
            {
                k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in voice_vs_text.items()
            },
            indent=None,
        ),
    )
    print(
        "    followup_effect:    ",
        json.dumps(
            {
                k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in followup_effectiveness.items()
                if k != "top_followup_prompts"
            },
            indent=None,
        ),
    )
    print(
        "    voice_ux:           ",
        json.dumps(
            {
                k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in voice_ux.items()
                if k != "voice_duration_distribution"
            },
            indent=None,
        ),
    )

    success = True

    expected_completed = len(runs)
    if totals.get("completed", 0) < expected_completed:
        fail(
            f"user-testing totals.completed = {totals.get('completed')} "
            f"(expected >= {expected_completed})"
        )
        success = False
    else:
        ok(f"totals.completed = {totals.get('completed')}")

    voice_adoption = executive.get("voice_adoption_rate")
    if voice_adoption is None or voice_adoption <= 0:
        warn(f"voice_adoption_rate = {voice_adoption} (expected > 0 because V/V and V/T used voice)")
    else:
        ok(f"voice_adoption_rate = {_fmt_pct(voice_adoption)}")

    if (voice_vs_text.get("voice_open_answer_count") or 0) <= 0:
        fail("voice_vs_text.voice_open_answer_count is 0 — voice answers did not land")
        success = False
    else:
        ok(
            f"voice_open_answer_count={voice_vs_text['voice_open_answer_count']} "
            f"text_open_answer_count={voice_vs_text.get('text_open_answer_count')}"
        )

    shown = followup_effectiveness.get("followups_shown_total") or 0
    answered = followup_effectiveness.get("followups_answered_total") or 0
    if shown <= 0:
        fail("followups_shown_total = 0 — no follow-ups were captured")
        success = False
    else:
        ok(f"followups_shown_total={shown}  followups_answered_total={answered}")

    engagement = followup_effectiveness.get("followup_engagement_rate")
    if engagement is not None:
        ok(f"followup_engagement_rate = {_fmt_pct(engagement)}")

    started_in_voice = voice_ux.get("started_in_voice_count") or 0
    if started_in_voice <= 0:
        warn("voice_ux.started_in_voice_count = 0 (V/V and V/T should have set started_in_voice)")
    else:
        ok(f"started_in_voice_count = {started_in_voice}")

    return success


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


async def main() -> int:
    print(f"{BOLD}Spring AI Training 2026 — backend follow-up test suite{RESET}")
    print(f"{DIM}API base:   {API_BASE}{RESET}")
    print(f"{DIM}Cohort id:  {SPRING_COHORT_ID}{RESET}")

    api = ApiClient(API_BASE)
    try:
        # Sanity check the backend is reachable
        try:
            await api.get("/health")
            ok("Backend /health is reachable")
        except Exception as e:
            fail(f"Cannot reach backend at {API_BASE}: {e}")
            return 2

        # Run the four scenarios
        runs: list[RunResult] = []
        for i, scenario in enumerate(SCENARIOS):
            t0 = time.time()
            try:
                r = await run_scenario(api, scenario, i)
                runs.append(r)
                dt = time.time() - t0
                ok(f"Scenario finished in {dt:.1f}s")
            except Exception as e:
                fail(f"Scenario {scenario.label} failed: {e}")

        # Verify dashboards reflect the submissions
        success = await verify_dashboards(api, runs)

        section("Summary")
        for r in runs:
            print(
                f"  {BOLD}{r.scenario.label}{RESET}\n"
                f"    submission_id   = {r.submission_id}\n"
                f"    open-ended modes= {r.open_answer_modes}\n"
                f"    follow-up modes = {r.followup_modes}\n"
                f"    follow-ups      = shown={r.followups_shown} answered={r.followups_answered}\n"
                f"    extraction      = {json.dumps(r.extraction, default=str) if r.extraction else 'n/a'}"
            )

        print()
        if success:
            print(f"{GREEN}{BOLD}All dashboard checks passed.{RESET}")
            return 0
        print(f"{RED}{BOLD}Some dashboard checks failed — see [XX] lines above.{RESET}")
        return 1
    finally:
        await api.close()


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
