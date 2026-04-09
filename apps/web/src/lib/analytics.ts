/**
 * Lightweight analytics module for InnovateUS Feedback Tool.
 *
 * Generates an anonymous session token, queues events, and flushes
 * them in batches to POST /v1/events. Uses fire-and-forget fetch
 * with keepalive so events survive page navigation.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const FLUSH_INTERVAL_MS = 2000;
const FLUSH_BATCH_SIZE = 5;

interface QueuedEvent {
  event_type: string;
  event_data: Record<string, unknown>;
  timestamp: string;
}

let _sessionToken: string | null = null;
let _eventQueue: QueuedEvent[] = [];
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
let _cohortId: string | null = null;
let _submissionId: string | null = null;

export function initSession(): string {
  if (typeof window === "undefined") return "";

  let token = sessionStorage.getItem("analytics_session");
  if (!token) {
    token = crypto.randomUUID();
    sessionStorage.setItem("analytics_session", token);
  }
  _sessionToken = token;
  return token;
}

function getSessionToken(): string {
  if (_sessionToken) return _sessionToken;
  return initSession();
}

export function setContext(cohortId?: string, submissionId?: string) {
  if (cohortId) _cohortId = cohortId;
  if (submissionId) _submissionId = submissionId;
}

function flush() {
  if (_eventQueue.length === 0) return;

  const events = [..._eventQueue];
  _eventQueue = [];

  const body = JSON.stringify({
    session_token: getSessionToken(),
    cohort_id: _cohortId || undefined,
    submission_id: _submissionId || undefined,
    events,
  });

  try {
    fetch(`${API_URL}/v1/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {}); // Fire and forget
  } catch {
    // Silently ignore
  }
}

function scheduleFlush() {
  if (_flushTimer) return;
  _flushTimer = setTimeout(() => {
    _flushTimer = null;
    flush();
  }, FLUSH_INTERVAL_MS);
}

export function trackEvent(
  eventType: string,
  eventData: Record<string, unknown> = {},
  cohortId?: string,
  submissionId?: string,
) {
  if (typeof window === "undefined") return;

  if (cohortId) _cohortId = cohortId;
  if (submissionId) _submissionId = submissionId;

  _eventQueue.push({
    event_type: eventType,
    event_data: eventData,
    timestamp: new Date().toISOString(),
  });

  if (_eventQueue.length >= FLUSH_BATCH_SIZE) {
    flush();
  } else {
    scheduleFlush();
  }
}

export function trackPageView(page: string, cohortId?: string) {
  trackEvent("page_view", { page }, cohortId);
}

export function trackDropout(
  cohortId: string,
  submissionId: string | null,
  lastQuestionId: string,
  questionsAnswered: number,
) {
  if (typeof window === "undefined") return;

  const body = JSON.stringify({
    session_token: getSessionToken(),
    cohort_id: cohortId,
    submission_id: submissionId || undefined,
    last_question_id: lastQuestionId,
    questions_answered: questionsAnswered,
  });

  // Use sendBeacon for reliable delivery during page unload
  if (navigator.sendBeacon) {
    const blob = new Blob([body], { type: "application/json" });
    navigator.sendBeacon(`${API_URL}/v1/events/dropout`, blob);
  } else {
    fetch(`${API_URL}/v1/events/dropout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  }
}

// Flush any remaining events before the page unloads
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", flush);
}
