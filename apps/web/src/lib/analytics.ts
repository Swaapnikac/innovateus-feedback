/**
 * Lightweight analytics module for InnovateUS Feedback Tool.
 *
 * Responsibilities:
 *   - Maintain an anonymous session token.
 *   - Queue events and flush in small batches to POST /v1/events.
 *   - Expose strongly-typed helpers for the user-testing event taxonomy:
 *     question_started, mic_permission_result, voice_recording_started,
 *     voice_recording_stopped, transcript_edited, input_mode_switched,
 *     audio_capture_error, api_latency, client_error, survey_start,
 *     followup_triggered/answered, review_edit, etc.
 *   - Send a one-time `client-env` payload (UA/screen/connection/voice
 *     support) to POST /v1/submissions/{id}/client-env so the backend can
 *     denormalize browser/OS/device onto the submission for H6 analysis.
 *   - Install lightweight global handlers for runtime errors and unhandled
 *     promise rejections so we capture client_error events.
 *
 * Fire-and-forget semantics — all network calls use keepalive so events
 * survive navigation and unload. Failures are intentionally swallowed.
 */

// Mirrors the resolution in ``lib/api.ts``. Empty NEXT_PUBLIC_API_URL means
// we're behind the Next.js rewrite proxy in production — fall back to
// same-origin ``/api`` so cookies and the X-Submission-Token round-trip
// land on the right host.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
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
let _clientEnvSent = false;
let _globalHandlersInstalled = false;

export function initSession(): string {
  if (typeof window === "undefined") return "";

  let token = sessionStorage.getItem("analytics_session");
  if (!token) {
    token = crypto.randomUUID();
    sessionStorage.setItem("analytics_session", token);
  }
  _sessionToken = token;
  installGlobalErrorHandlers();
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

// HMAC token returned by /submissions/start. Required by the API on every
// event/mutation tied to a submission_id. Returns {} when no token exists
// (e.g. cohort-level events fired before the user clicks Start).
function _submissionTokenHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const token = sessionStorage.getItem("submission_token");
    return token ? { "X-Submission-Token": token } : {};
  } catch {
    return {};
  }
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
      headers: { "Content-Type": "application/json", ..._submissionTokenHeader() },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // ignore
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

// ─────────────────────────────────────────────────────────────────────────────
// Typed event helpers for the user-testing taxonomy
// ─────────────────────────────────────────────────────────────────────────────

export function trackQuestionStarted(
  questionId: string,
  questionIndex: number,
  questionType: string,
) {
  trackEvent("question_started", {
    question_id: questionId,
    question_index: questionIndex,
    question_type: questionType,
  });
}

export function trackMicPermission(
  status: "granted" | "denied" | "prompt" | "unknown" | "unsupported",
  extra: Record<string, unknown> = {},
) {
  trackEvent("mic_permission_result", { status, ...extra });
}

export function trackVoiceRecordingStarted(questionId: string) {
  trackEvent("voice_recording_started", { question_id: questionId });
}

export function trackVoiceRecordingStopped(
  questionId: string,
  durationSec: number,
  reason:
    | "user_stop"
    | "silence_timeout"
    | "max_duration"
    | "error"
    | "unmount" = "user_stop",
) {
  trackEvent("voice_recording_stopped", {
    question_id: questionId,
    duration_sec: Math.max(0, Math.round(durationSec)),
    reason,
  });
}

export function trackTranscriptEdited(
  questionId: string,
  originalLength: number,
  finalLength: number,
  editDistance?: number,
) {
  trackEvent("transcript_edited", {
    question_id: questionId,
    original_length: originalLength,
    final_length: finalLength,
    edit_distance: editDistance ?? null,
  });
}

export function trackInputModeSwitched(
  questionId: string,
  from: "voice" | "text",
  to: "voice" | "text",
  stage?: string,
  reason?: string,
) {
  trackEvent("input_mode_switched", {
    question_id: questionId,
    from,
    to,
    stage: stage ?? null,
    reason: reason ?? null,
  });
}

export function trackAudioCaptureError(
  questionId: string,
  errorType: string,
  message?: string,
) {
  trackEvent("audio_capture_error", {
    question_id: questionId,
    error_type: errorType,
    // Hard cap to avoid persisting large error blobs that could contain
    // copy/pasted user content or DOM snippets.
    message: message?.slice(0, 200) ?? null,
  });
}

export function trackApiLatency(
  path: string,
  status: number,
  durationMs: number,
  ok: boolean,
) {
  trackEvent("api_latency", {
    path,
    status,
    duration_ms: Math.max(0, Math.round(durationMs)),
    ok,
  });
}

export function trackClientError(
  kind: "error" | "unhandledrejection" | "manual",
  message: string,
  source?: string,
  stack?: string,
) {
  // Caps are deliberately tight: error messages and stacks can occasionally
  // include user input or response bodies. We want enough context to
  // diagnose recurring bugs but not enough to be a leakage surface if an
  // event row is shared.
  trackEvent("client_error", {
    kind,
    message: message.slice(0, 200),
    source: source?.slice(0, 200) ?? null,
    stack: stack?.slice(0, 500) ?? null,
  });
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

  // sendBeacon does not support custom headers — when we have a
  // submission token we must use fetch+keepalive instead so the
  // X-Submission-Token header rides along. Beacon is only used for the
  // pre-submission case (cohort-only dropout) where no token is needed.
  const tokenHeader = _submissionTokenHeader();
  if (navigator.sendBeacon && Object.keys(tokenHeader).length === 0) {
    const blob = new Blob([body], { type: "application/json" });
    navigator.sendBeacon(`${API_URL}/v1/events/dropout`, blob);
  } else {
    fetch(`${API_URL}/v1/events/dropout`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...tokenHeader },
      body,
      keepalive: true,
    }).catch(() => {});
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Client environment: sent once per submission so backend can populate
// browser/OS/device fields on the Submission row (H6).
// ─────────────────────────────────────────────────────────────────────────────

export async function sendClientEnv(submissionId: string): Promise<void> {
  if (typeof window === "undefined") return;
  if (_clientEnvSent) return;
  _clientEnvSent = true;

  const nav = navigator as Navigator & {
    connection?: { effectiveType?: string; type?: string };
  };
  const conn = nav.connection || {};
  const effective = typeof conn.effectiveType === "string" ? conn.effectiveType : undefined;
  const connType = typeof conn.type === "string" ? conn.type : effective;

  // Probe speech-recognition support (not guaranteed to match mic state).
  const w = window as unknown as {
    SpeechRecognition?: unknown;
    webkitSpeechRecognition?: unknown;
  };
  const voiceSupported = Boolean(
    w.SpeechRecognition || w.webkitSpeechRecognition ||
    (typeof navigator.mediaDevices !== "undefined" && typeof navigator.mediaDevices.getUserMedia === "function"),
  );

  let pageLoadMs: number | null = null;
  try {
    const nav0 = performance?.getEntriesByType?.("navigation")?.[0] as PerformanceNavigationTiming | undefined;
    if (nav0 && nav0.duration) pageLoadMs = Math.round(nav0.duration);
  } catch {
    pageLoadMs = null;
  }

  let micStatus: string | undefined;
  try {
    const perms = (navigator as Navigator & { permissions?: { query: (q: { name: string }) => Promise<{ state: string }> } }).permissions;
    if (perms && typeof perms.query === "function") {
      const p = await perms.query({ name: "microphone" });
      micStatus = p.state;
    }
  } catch {
    micStatus = undefined;
  }

  const payload = {
    user_agent: navigator.userAgent || null,
    screen_size:
      typeof window.screen !== "undefined" && window.screen.width && window.screen.height
        ? `${window.screen.width}x${window.screen.height}`
        : null,
    connection_type: connType || null,
    page_load_time_ms: pageLoadMs,
    voice_supported: voiceSupported,
    mic_permission_status: micStatus || null,
  };

  try {
    await fetch(`${API_URL}/v1/submissions/${submissionId}/client-env`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ..._submissionTokenHeader() },
      body: JSON.stringify(payload),
      keepalive: true,
    });
  } catch {
    // ignore
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Global runtime error handlers — capture client_error events
// ─────────────────────────────────────────────────────────────────────────────

function installGlobalErrorHandlers() {
  if (_globalHandlersInstalled || typeof window === "undefined") return;
  _globalHandlersInstalled = true;

  window.addEventListener("error", (ev: ErrorEvent) => {
    try {
      trackClientError(
        "error",
        ev.message || String(ev.error || "unknown"),
        ev.filename ? `${ev.filename}:${ev.lineno ?? ""}:${ev.colno ?? ""}` : undefined,
        ev.error?.stack,
      );
    } catch {
      // ignore
    }
  });

  window.addEventListener("unhandledrejection", (ev: PromiseRejectionEvent) => {
    try {
      const reason = ev.reason;
      const message =
        (reason && typeof reason === "object" && "message" in reason && typeof (reason as { message?: unknown }).message === "string")
          ? (reason as { message: string }).message
          : String(reason || "unhandled rejection");
      const stack =
        reason && typeof reason === "object" && "stack" in reason && typeof (reason as { stack?: unknown }).stack === "string"
          ? (reason as { stack: string }).stack
          : undefined;
      trackClientError("unhandledrejection", message, undefined, stack);
    } catch {
      // ignore
    }
  });
}

// Flush any remaining events before the page unloads
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", flush);
  installGlobalErrorHandlers();
}
