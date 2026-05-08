// Base URL for backend calls.
//
// - When ``NEXT_PUBLIC_API_URL`` is set (local dev: ``http://localhost:8009``),
//   we hit the backend directly. The browser pays one CORS preflight per
//   route but the dev experience is straightforward.
// - When it's empty (production behind the Next.js rewrite proxy), we use
//   the same-origin path ``/api`` so requests stay on
//   ``publicvoice.innovate-us.org`` and the API's Set-Cookie gets bound
//   to the frontend's domain. ``next.config.ts`` rewrites
//   ``/api/v1/:path*`` to ``${API_PROXY_TARGET}/v1/:path*`` server-side.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

// Paths we don't want to emit api_latency for (avoids feedback loops and
// dashboard-admin noise — dashboard metrics paths include /admin/).
const _LATENCY_IGNORE_PATTERNS = [
  "/v1/events",
  "/v1/admin/",
  "/v1/submissions/",
];

async function _trackLatency(path: string, status: number, ok: boolean, durationMs: number) {
  if (typeof window === "undefined") return;
  for (const p of _LATENCY_IGNORE_PATTERNS) {
    if (path.startsWith(p)) {
      // still track submission-side calls (non-admin); filter only admin+events
      if (p === "/v1/admin/" || p === "/v1/events") return;
    }
  }
  try {
    const mod = await import("./analytics");
    mod.trackApiLatency(path, status, durationMs, ok);
  } catch {
    // ignore
  }
}

// Read the per-submission HMAC token the API minted at /submissions/start.
// Submission-mutating endpoints require this on every call as the
// X-Submission-Token header. Stored in sessionStorage so it dies with
// the tab and never crosses an origin.
function _getSubmissionToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem("submission_token");
  } catch {
    return null;
  }
}

function _submissionAuthHeader(): Record<string, string> {
  const token = _getSubmissionToken();
  return token ? { "X-Submission-Token": token } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  // Auth is carried by the httpOnly admin_token / editor_token cookies set
  // by the API on login. They are sent automatically via credentials:
  // "include". We deliberately do NOT read tokens from localStorage — that
  // copy would be readable by any script and is an XSS escalation surface.
  const started = typeof performance !== "undefined" ? performance.now() : Date.now();
  let status = 0;
  let ok = false;
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      credentials: "include",
    });
    status = res.status;
    ok = res.ok;
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  } finally {
    const ended = typeof performance !== "undefined" ? performance.now() : Date.now();
    void _trackLatency(path, status, ok, ended - started);
  }
}

export type QuestionType =
  | "rating"
  | "mcq"
  | "multi"
  | "open"
  | "nps"
  | "slider"
  | "matrix"
  | "ranking"
  | "yesno"
  | "dropdown"
  | "short_text"
  | "date";

export interface SurveyQuestion {
  id: string;
  type: QuestionType;
  text: string;
  description?: string;
  options?: (string | number)[];
  required: boolean;
  voice_eligible: boolean;
  condition?: {
    question_id: string;
    operator: string;
    value: string;
  };
  group?: string;
  // Slider-specific
  scale_min?: number;
  scale_max?: number;
  scale_step?: number;
  // Matrix-specific — rows rated against `options` (columns)
  rows?: string[];
  // NPS / scale endpoint labels
  labels?: {
    low?: string;
    high?: string;
  };
}

export interface QuestionGroup {
  id: string;
  label: string;
  randomize: boolean;
}

export interface SurveyConfig {
  cohort_id: string;
  // Returned by GET /v1/survey/{key} when the cohort has a friendly slug.
  // Frontend uses ``slug || cohort_id`` to build shareable URLs.
  slug?: string | null;
  survey: {
    version: string;
    title: string;
    questions: SurveyQuestion[];
    question_groups?: QuestionGroup[];
  };
  active_version?: string | null;
}

export interface SurveyVersionSummary {
  version_label: string;
  change_summary: string | null;
  created_at: string;
  created_by: string;
}

export interface SurveyVersionDetail extends SurveyVersionSummary {
  config: Record<string, unknown>;
}

export interface AiAnswerInsight {
  submission_id: string;
  question_id: string;
  question_text?: string;
  answer_text?: string;
  sentiment: "positive" | "neutral" | "negative" | "mixed" | string;
  quality_score: number;
  quality_reason?: string;
}

export interface AiTopic {
  label: string;
  count: number;
  summary: string;
}

export interface AiInsights {
  ai_available: boolean;
  total_open_responses: number;
  sentiment_distribution: Record<string, number>;
  average_quality_score: number | null;
  topics: AiTopic[];
  answer_insights: AiAnswerInsight[];
  summary: string;
  recommendations: string[];
}

export interface CompareInsights {
  ai_available: boolean;
  summary: string;
  wins: string[];
  risks: string[];
  recommendations: string[];
  primary: { id: string; name: string; completed_count: number };
  comparison: { id: string; name: string; completed_count: number };
}

export interface VaguenessResult {
  is_vague: boolean;
  is_irrelevant: boolean;
  reason: string;
  missing_info_types: string[];
  vagueness_score?: number | null;
  /** True when the backend AI call failed and the response is a safe fallback
   * (never silently advance the user when this is set). */
  error?: boolean;
}

export interface FollowUpResult {
  followups: string[];
  /** Set by /ai/check and /ai/check-followup when the user declined to
   * elaborate (e.g. "nothing", "not sure"). No follow-up should be shown. */
  declined?: boolean;
}

export interface UserTestingAnalytics {
  generated_at: string;
  targets: Record<string, number>;
  totals: {
    total_submissions: number;
    started: number;
    completed: number;
    abandoned: number;
    in_progress: number;
  };
  executive: {
    completion_rate: number | null;
    voice_adoption_rate: number | null;
    avg_time_to_complete_sec: number | null;
    median_time_to_complete_sec: number | null;
    follow_up_engagement_rate: number | null;
    extraction_usefulness_rate: number | null;
    qualtrics_sync_success_rate: number | null;
    critical_error_count: number;
    mode_switch_rate: number | null;
  };
  funnel: Array<{ stage: string; count: number }>;
  voice_vs_text: {
    avg_voice_word_count: number | null;
    avg_text_word_count: number | null;
    median_voice_word_count: number | null;
    median_text_word_count: number | null;
    voice_open_answer_count: number;
    text_open_answer_count: number;
    voice_vague_rate: number | null;
    text_vague_rate: number | null;
    mode_switch_rate: number | null;
  };
  followup_effectiveness: {
    followups_shown_total: number;
    followups_answered_total: number;
    followup_engagement_rate: number | null;
    initial_vague_count: number;
    vague_after_followups_count: number;
    post_followup_vagueness_rate: number | null;
    specificity_improvement_count: number;
    specificity_improvement_rate: number | null;
    top_followup_prompts: Array<{
      prompt: string;
      shown: number;
      answered: number;
      improved: number;
      improvement_rate: number | null;
    }>;
  };
  survey_friction: {
    abandonment_by_step: Array<{ question_id: string; count: number }>;
    avg_time_to_complete_sec: number | null;
    median_time_to_complete_sec: number | null;
  };
  voice_ux: {
    started_in_voice_count: number;
    voice_conversation_completed_count: number;
    voice_conversation_completion_rate: number | null;
    transcript_edit_rate: number | null;
    mic_permission_failure_rate: number | null;
    voice_duration_distribution: Array<{ bucket: string; count: number }>;
  };
  technical_health: {
    browser_breakdown: Array<{ label: string; count: number }>;
    os_breakdown: Array<{ label: string; count: number }>;
    device_breakdown: Array<{ label: string; count: number }>;
    browser_error_rate: Record<string, number | null>;
    avg_api_latency_ms: number | null;
    max_api_latency_ms: number | null;
    total_timeouts: number;
    total_api_failures: number;
    client_error_count: number;
    critical_error_count: number;
    critical_error_rate: number | null;
  };
  extraction_quality: {
    extraction_success_rate: number | null;
    extractions_total: number;
    reviews_total: number;
    reviews_with_useful_flag: number;
    review_coverage_rate: number | null;
    extraction_usefulness_rate: number | null;
    avg_accuracy_rating: number | null;
    avg_usefulness_rating: number | null;
  };
  qualtrics_sync: {
    completed_count: number;
    attempted_count: number;
    succeeded_count: number;
    failed_count: number;
    success_rate: number | null;
    avg_latency_ms: number | null;
    recent_failures: Array<{
      submission_id: string;
      attempts: number;
      last_attempt_at: string | null;
      error: string;
    }>;
  };
  participant_feedback: {
    experience_rating_count: number;
    avg_experience_rating: number | null;
    voice_experience_rating_count: number;
    avg_voice_experience_rating: number | null;
    would_use_again_yes: number;
    would_use_again_total: number;
    confusion_flag_count: number;
    reported_issue_count: number;
  };
  facilitator_feedback: Array<{
    cohort_id: string;
    cohort_name: string;
    facilitator_name: string | null;
    launch_phase: string | null;
    feedback_text: string | null;
    reported_issue: boolean;
    issue_type: string | null;
    issue_notes: string | null;
    received_at: string | null;
  }>;
  hypothesis_totals: Record<
    "h1" | "h2" | "h3" | "h4" | "h5" | "h6",
    { true: number; false: number; null: number }
  >;
}

export interface FacilitatorFeedbackPayload {
  cohort_id: string;
  facilitator_name: string | null;
  facilitator_email: string | null;
  source_channel: string | null;
  launch_phase: string | null;
  facilitator_feedback_text: string | null;
  facilitator_feedback_received_at?: string | null;
  facilitator_reported_issue_flag: boolean | null;
  facilitator_issue_type: string | null;
  facilitator_issue_notes: string | null;
}

export interface ExtractionResult {
  what_was_tried: string | null;
  planned_task_or_workflow: string | null;
  outcome_or_expected_outcome: string | null;
  barriers: string[];
  enablers: string[];
  public_benefit: string | null;
  top_themes: string[];
  success_story_candidate: string | null;
}

export const api = {
  getSurvey: (cohortId: string) =>
    request<SurveyConfig>(`/v1/survey/${cohortId}?_t=${Date.now()}`, { cache: "no-store" }),

  startSubmission: (cohortId: string, consentVersion = "1.0") =>
    request<{ submission_id: string; submission_token: string }>("/v1/submissions/start", {
      method: "POST",
      body: JSON.stringify({
        cohort_id: cohortId,
        consent_version: consentVersion,
      }),
    }),

  saveAnswer: (
    submissionId: string,
    data: {
      question_id: string;
      question_type: string;
      answer_raw?: string;
      input_mode?: string;
      transcript?: string;
      is_vague?: boolean;
      followups_asked?: number;
      followup_1?: string;
      followup_1_answer?: string;
      followup_1_input_mode?: string;
      followup_2?: string;
      followup_2_answer?: string;
      followup_2_input_mode?: string;
    }
  ) =>
    request<{ id: string; question_id: string }>(
      `/v1/submissions/${submissionId}/answer`,
      {
        method: "POST",
        body: JSON.stringify(data),
        headers: _submissionAuthHeader(),
      }
    ),

  completeSubmission: (submissionId: string) =>
    request<{ status: string; extraction: ExtractionResult | null }>(
      `/v1/submissions/${submissionId}/complete`,
      { method: "POST", headers: _submissionAuthHeader() }
    ),

  submitExperienceRating: (submissionId: string, rating: number, feedbackText?: string) =>
    request<{ status: string; rating: number }>(`/v1/submissions/${submissionId}/experience-rating`, {
      method: "POST",
      body: JSON.stringify({ rating, feedback_text: feedbackText || undefined }),
      headers: _submissionAuthHeader(),
    }),

  previewExtraction: (submissionId: string) =>
    request<{ status: string; extraction: ExtractionResult | null }>(
      `/v1/submissions/${submissionId}/preview-extraction`,
      { method: "POST", headers: _submissionAuthHeader() }
    ),

  // Returns every answer the server already has for an in-progress
  // submission so the survey UI can rehydrate state after a tab close.
  // Without this, sessionStorage is empty on resume, the form looks blank,
  // but the DB still has the answers — and the review-page summary (which
  // reads from the DB) shows them, contradicting the form.
  getSubmissionAnswers: (submissionId: string) =>
    request<{
      submission_id: string;
      status: string;
      answers: Array<{
        question_id: string;
        question_type: string;
        value: string;
        multi_values: string[];
        input_mode: string;
        transcript: string | null;
        is_vague: boolean | null;
        followups: string[];
        followup_1_answer: string | null;
        followup_2_answer: string | null;
      }>;
    }>(`/v1/submissions/${submissionId}/answers`, {
      headers: _submissionAuthHeader(),
    }),

  transcribe: async (
    audioBlob: Blob,
  ): Promise<{ transcript: string; pii_redaction_applied?: boolean; pii_redaction_categories?: string[] }> => {
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");
    // C6: hard timeout so a stuck upload (flaky wifi, backend slow) does
    // not hang the recorder UI indefinitely. 30s is generous for Whisper.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30_000);
    try {
      const res = await fetch(`${API_URL}/v1/transcribe`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      if (!res.ok) {
        throw new Error(`Transcription failed (${res.status})`);
      }
      return res.json();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new Error("Transcription timed out after 30 seconds");
      }
      throw err;
    } finally {
      clearTimeout(timeoutId);
    }
  },

  cleanupTranscript: (rawText: string) =>
    request<{ cleaned: string; changed: boolean }>("/v1/ai/cleanup", {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText }),
    }),

  checkVagueness: (questionText: string, answerText: string) =>
    request<VaguenessResult>("/v1/ai/vagueness", {
      method: "POST",
      body: JSON.stringify({
        question_text: questionText,
        answer_text: answerText,
      }),
    }),

  // Combined single round-trip: vagueness check + followup generation
  checkWithFollowups: (questionText: string, answerText: string) =>
    request<VaguenessResult & FollowUpResult>("/v1/ai/check", {
      method: "POST",
      body: JSON.stringify({
        question_text: questionText,
        answer_text: answerText,
      }),
    }),

  // Regex + GPT-5-mini PII scan. Returns metadata only — no redacted text.
  // Used by the survey Next click to catch categories (names, soft
  // addresses) that client-side regex cannot pick up on its own.
  checkPii: (text: string) =>
    request<{ found: boolean; count: number; categories: string[] }>(
      "/v1/ai/pii-check",
      {
        method: "POST",
        body: JSON.stringify({ text }),
      },
    ),

  // Context-aware check used AFTER follow-up 1 has been answered, to decide
  // whether a follow-up 2 is genuinely needed. The backend uses a stricter,
  // follow-up-level prompt that knows the participant already had one chance.
  checkFollowupForClarification: (data: {
    original_question: string;
    original_answer: string;
    followup_question: string;
    followup_answer: string;
  }) =>
    request<VaguenessResult & FollowUpResult>("/v1/ai/check-followup", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getFollowups: (
    questionText: string,
    answerText: string,
    missingInfoTypes: string[],
  ) =>
    request<FollowUpResult>("/v1/ai/followups", {
      method: "POST",
      body: JSON.stringify({
        question_text: questionText,
        answer_text: answerText,
        missing_info_types: missingInfoTypes,
      }),
    }),

  adminLogin: (password: string) =>
    // Login state is in the httpOnly cookie set by the API; the response
    // body is just an ack.
    request<{ status: string }>("/v1/admin/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  adminLogout: () =>
    request<{ status: string }>("/v1/admin/logout", { method: "POST" }),

  editorLogout: () =>
    request<{ status: string }>("/v1/admin/editor/logout", { method: "POST" }),

  getMetrics: (params?: { cohort_id?: string; start?: string; end?: string; survey_version?: string; segment_q?: string; segment_v?: string }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    if (params?.survey_version) query.set("survey_version", params.survey_version);
    if (params?.segment_q) query.set("segment_q", params.segment_q);
    if (params?.segment_v) query.set("segment_v", params.segment_v);
    return request<{
      total_submissions: number;
      completed_submissions: number;
      completion_rate: number;
      avg_time_to_complete_sec: number | null;
      avg_recommend_score: number | null;
      confidence_distribution: Record<string, number>;
      vagueness_rate: number | null;
    }>(`/v1/admin/metrics?${query}`);
  },

  getResponses: (params?: {
    cohort_id?: string;
    start?: string;
    end?: string;
    survey_version?: string;
    segment_q?: string;
    segment_v?: string;
    page?: number;
    page_size?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    if (params?.survey_version) query.set("survey_version", params.survey_version);
    if (params?.segment_q) query.set("segment_q", params.segment_q);
    if (params?.segment_v) query.set("segment_v", params.segment_v);
    if (params?.page) query.set("page", String(params.page));
    if (params?.page_size) query.set("page_size", String(params.page_size));
    return request<{
      items: Array<{
        id: string;
        cohort_id: string;
        created_at: string;
        completed_at: string | null;
        status: string;
        time_to_complete_sec: number | null;
        survey_version: string | null;
        ip_hash: string | null;
        answers: Array<Record<string, unknown>>;
        extraction: ExtractionResult | null;
      }>;
      total: number;
      page: number;
      page_size: number;
    }>(`/v1/admin/responses?${query}`);
  },

  getCohorts: () =>
    request<Array<{ id: string; slug: string | null; name: string; course_name: string; program_type: string | null; max_submissions_per_ip: number; created_at: string }>>(
      "/v1/admin/cohorts"
    ),

  createCohort: (name: string, programType: string, slug?: string) =>
    request<{ id: string; slug: string | null; name: string; course_name: string; program_type: string | null; max_submissions_per_ip: number; created_at: string }>("/v1/admin/cohorts", {
      method: "POST",
      body: JSON.stringify({
        name,
        program_type: programType,
        ...(slug ? { slug } : {}),
      }),
    }),

  deleteAllResponses: (cohortId?: string) => {
    const query = cohortId ? `?cohort_id=${cohortId}` : "";
    return request<{ status: string; deleted: number }>(`/v1/admin/responses${query}`, {
      method: "DELETE",
    });
  },

  deleteCohort: (cohortId: string) =>
    request<{ status: string; cohort_id: string }>(`/v1/admin/cohorts/${cohortId}`, {
      method: "DELETE",
    }),

  duplicateCohort: (cohortId: string) =>
    request<{ id: string; slug: string | null; name: string; course_name: string; program_type: string | null; max_submissions_per_ip: number; created_at: string }>(
      `/v1/admin/cohorts/${cohortId}/duplicate`,
      { method: "POST" }
    ),

  updateCohortSettings: (
    cohortId: string,
    settings: { max_submissions_per_ip: number; slug?: string }
  ) =>
    request<{
      status: string;
      max_submissions_per_ip: number;
      slug: string | null;
      slug_changed: boolean;
      previous_slugs: string[];
    }>(`/v1/admin/cohorts/${cohortId}/settings`, {
      method: "POST",
      body: JSON.stringify(settings),
    }),

  editorLogin: (password: string) =>
    request<{ status: string }>("/v1/admin/editor/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  getEditorCohorts: () =>
    request<Array<{ id: string; slug: string | null; name: string; course_name: string; program_type: string | null; max_submissions_per_ip: number; created_at: string }>>(
      "/v1/admin/editor/cohorts"
    ),

  getEditorSurvey: (cohortId: string) =>
    request<SurveyConfig>(`/v1/admin/editor/survey/${cohortId}`),

  saveEditorSurvey: (cohortId: string, config: { version: string; title: string; questions: SurveyQuestion[]; question_groups?: QuestionGroup[] }) =>
    request<{ status: string; cohort_id: string; version_label?: string; change_summary?: string }>(`/v1/admin/editor/survey/${cohortId}`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  getVersionHistory: (cohortId: string) =>
    request<{ items: SurveyVersionSummary[]; total: number; active_version: string | null }>(
      `/v1/admin/editor/survey/${cohortId}/versions`
    ),

  getVersion: (cohortId: string, versionLabel: string) =>
    request<SurveyVersionDetail>(`/v1/admin/editor/survey/${cohortId}/versions/${versionLabel}`),

  restoreVersion: (cohortId: string, versionLabel: string) =>
    request<{ status: string; cohort_id: string; version_label: string; restored_from: string }>(
      `/v1/admin/editor/survey/${cohortId}/versions/${versionLabel}/restore`,
      { method: "POST" }
    ),

  generateSurvey: (data: { goal_description: string; program_type?: string; question_count?: number }) =>
    request<{ survey: { version: string; title: string; questions: SurveyQuestion[]; question_groups?: QuestionGroup[] } }>(
      "/v1/admin/editor/generate-survey",
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    ),

  getAnalytics: (params?: { cohort_id?: string; start?: string; end?: string; segment_q?: string; segment_v?: string }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    if (params?.segment_q) query.set("segment_q", params.segment_q);
    if (params?.segment_v) query.set("segment_v", params.segment_v);
    return request<{
      funnel: { page_views_landing: number; page_views_consent: number; survey_starts: number; survey_in_progress: number; survey_completed: number; dropout_rate: number };
      per_question_dropout: Array<{ question_id: string; reached: number; answered: number; dropout_count: number }>;
      voice_vs_text: { total_open_answers: number; voice_count: number; text_count: number; voice_percentage: number; per_question: Array<{ question_id: string; voice: number; text: number }> };
      followup_effectiveness: { total_vague_detected: number; followups_shown: number; followups_answered: number; followups_skipped: number; answer_rate: number };
      voice_vs_text_quality: { voice_vague_rate: number; text_vague_rate: number; voice_avg_length: number; text_avg_length: number };
      review_edits: { total_reviews: number; reviews_with_edits: number; edit_rate: number; edits_per_question: Array<{ question_id: string; edit_count: number }> };
      experience_rating: { total_ratings: number; avg_rating: number | null; distribution: Record<string, number>; response_rate: number };
      time_metrics: { avg_total_sec: number | null; median_total_sec: number | null; total_question_answers: number };
      per_question_stats: Array<{
        question_id: string;
        question_type: string;
        question_text: string;
        total_responses: number;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        stats: Record<string, any>;
      }>;
      submissions_by_date: Array<{ date: string; count: number }>;
    }>(`/v1/admin/analytics?${query}`);
  },

  getCrosstab: (params: { cohort_id: string; q1: string; q2: string; start?: string; end?: string; survey_version?: string }) => {
    const query = new URLSearchParams();
    query.set("cohort_id", params.cohort_id);
    query.set("q1", params.q1);
    query.set("q2", params.q2);
    if (params.start) query.set("start", params.start);
    if (params.end) query.set("end", params.end);
    if (params.survey_version) query.set("survey_version", params.survey_version);
    return request<{
      q1_values: string[];
      q2_values: string[];
      matrix: Record<string, Record<string, number>>;
      total: number;
    }>(`/v1/admin/crosstab?${query}`);
  },

  getAiInsights: (params: {
    cohort_id: string;
    start?: string;
    end?: string;
    survey_version?: string;
    segment_q?: string;
    segment_v?: string;
  }) => {
    const query = new URLSearchParams();
    query.set("cohort_id", params.cohort_id);
    if (params.start) query.set("start", params.start);
    if (params.end) query.set("end", params.end);
    if (params.survey_version) query.set("survey_version", params.survey_version);
    if (params.segment_q) query.set("segment_q", params.segment_q);
    if (params.segment_v) query.set("segment_v", params.segment_v);
    return request<AiInsights>(`/v1/admin/ai-insights?${query}`);
  },

  getCompareInsights: (params: { cohort_id: string; compare_cohort_id: string; start?: string; end?: string }) => {
    const query = new URLSearchParams();
    query.set("cohort_id", params.cohort_id);
    query.set("compare_cohort_id", params.compare_cohort_id);
    if (params.start) query.set("start", params.start);
    if (params.end) query.set("end", params.end);
    return request<CompareInsights>(`/v1/admin/compare-insights?${query}`);
  },

  exportUrl: (
    type: "raw.csv" | "structured.csv" | "summary.pdf" | "summary.pptx" | "user-testing.csv" | "qualtrics.csv",
    params?: { cohort_id?: string; start?: string; end?: string; target?: string },
  ) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    if (params?.target) query.set("target", params.target);
    return `${API_URL}/v1/admin/export/${type}?${query}`;
  },

  getJotformStatus: () =>
    request<{ configured: boolean; form_id: string | null; api_url: string | null }>(
      "/v1/admin/jotform/status"
    ),

  syncJotform: (submissionId: string) =>
    request<{ status: string; submission_id: string }>(
      `/v1/admin/jotform/sync/${submissionId}`,
      { method: "POST" }
    ),

  getQualtricsStatus: () =>
    request<{
      configured: boolean;
      default_target: string;
      production: { configured: boolean; survey_id: string | null; datacenter_id: string | null };
      test: { configured: boolean; survey_id: string | null; datacenter_id: string | null };
    }>("/v1/admin/qualtrics/status"),

  validateQualtrics: (params?: { cohort_id?: string; target?: string }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.target) query.set("target", params.target);
    return request<{
      ok: boolean;
      target: string | null;
      survey_id: string | null;
      datacenter_id: string | null;
      errors: string[];
      warnings: string[];
    }>(`/v1/admin/qualtrics/validate?${query}`);
  },

  syncQualtrics: (submissionId: string) =>
    request<{ status: string; submission_id: string; error: string | null }>(
      `/v1/admin/qualtrics/sync/${submissionId}`,
      { method: "POST" }
    ),

  getUserTestingAnalytics: (params?: { cohort_id?: string; start?: string; end?: string }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    return request<UserTestingAnalytics>(`/v1/admin/user-testing-analytics?${query}`);
  },

  listReviews: (cohortId?: string) => {
    const query = new URLSearchParams();
    if (cohortId) query.set("cohort_id", cohortId);
    return request<{
      items: Array<{
        submission_id: string;
        cohort_id: string;
        reviewed_by: string;
        reviewed_at: string | null;
        useful_flag: boolean | null;
        accuracy_rating: number | null;
        usefulness_rating: number | null;
        accuracy_notes: string | null;
        usefulness_notes: string | null;
      }>;
      total: number;
    }>(`/v1/admin/reviews?${query}`);
  },

  upsertReview: (
    submissionId: string,
    data: {
      reviewed_by: string;
      useful_flag?: boolean;
      accuracy_rating?: number;
      usefulness_rating?: number;
      accuracy_notes?: string;
      usefulness_notes?: string;
    },
  ) =>
    request<{
      submission_id: string;
      reviewed_by: string;
      reviewed_at: string;
      useful_flag: boolean | null;
      accuracy_rating: number | null;
      usefulness_rating: number | null;
      accuracy_notes: string | null;
      usefulness_notes: string | null;
    }>(`/v1/admin/reviews/${submissionId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getFacilitatorFeedback: (cohortId: string) =>
    request<FacilitatorFeedbackPayload>(
      `/v1/admin/cohorts/${cohortId}/facilitator-feedback`,
    ),

  saveFacilitatorFeedback: (cohortId: string, data: Partial<FacilitatorFeedbackPayload>) =>
    request<FacilitatorFeedbackPayload>(
      `/v1/admin/cohorts/${cohortId}/facilitator-feedback`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  syncAllQualtrics: (params?: { cohortId?: string; force?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.cohortId) query.set("cohort_id", params.cohortId);
    if (params?.force) query.set("force", "true");
    return request<{ total: number; synced: number; failed: number; errors: Array<{ submission_id: string; error: string }> }>(
      `/v1/admin/qualtrics/sync-all?${query}`,
      { method: "POST" }
    );
  },
};
