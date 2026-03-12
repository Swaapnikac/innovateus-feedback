const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export interface SurveyQuestion {
  id: string;
  type: "rating" | "mcq" | "multi" | "open";
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
}

export interface SurveyConfig {
  cohort_id: string;
  survey: {
    version: string;
    title: string;
    questions: SurveyQuestion[];
  };
}

export interface VaguenessResult {
  is_vague: boolean;
  reason: string;
  missing_info_types: string[];
}

export interface FollowUpResult {
  followups: string[];
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
    request<SurveyConfig>(`/v1/survey/${cohortId}`),

  startSubmission: (cohortId: string, consentVersion = "1.0") =>
    request<{ submission_id: string }>("/v1/submissions/start", {
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
      followup_2?: string;
      followup_2_answer?: string;
    }
  ) =>
    request<{ id: string; question_id: string }>(
      `/v1/submissions/${submissionId}/answer`,
      { method: "POST", body: JSON.stringify(data) }
    ),

  completeSubmission: (submissionId: string) =>
    request<{ status: string; extraction: ExtractionResult | null }>(
      `/v1/submissions/${submissionId}/complete`,
      { method: "POST" }
    ),

  transcribe: async (audioBlob: Blob): Promise<{ transcript: string }> => {
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");
    const res = await fetch(`${API_URL}/v1/transcribe`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Transcription failed");
    return res.json();
  },

  checkVagueness: (questionText: string, answerText: string) =>
    request<VaguenessResult>("/v1/ai/vagueness", {
      method: "POST",
      body: JSON.stringify({
        question_text: questionText,
        answer_text: answerText,
      }),
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
    request<{ token: string }>("/v1/admin/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  getMetrics: (params?: { cohort_id?: string; start?: string; end?: string }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
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
    page?: number;
    page_size?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
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
        answers: Array<Record<string, unknown>>;
        extraction: ExtractionResult | null;
      }>;
      total: number;
      page: number;
      page_size: number;
    }>(`/v1/admin/responses?${query}`);
  },

  getCohorts: () =>
    request<Array<{ id: string; name: string; course_name: string; created_at: string }>>(
      "/v1/admin/cohorts"
    ),

  editorLogin: (password: string) =>
    request<{ token: string }>("/v1/admin/editor/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  getEditorSurvey: (cohortId: string) =>
    request<SurveyConfig>(`/v1/admin/editor/survey/${cohortId}`),

  saveEditorSurvey: (cohortId: string, config: { version: string; title: string; questions: SurveyQuestion[] }) =>
    request<{ status: string; cohort_id: string }>(`/v1/admin/editor/survey/${cohortId}`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  exportUrl: (type: "raw.csv" | "structured.csv" | "summary.pdf" | "summary.pptx", params?: {
    cohort_id?: string; start?: string; end?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.cohort_id) query.set("cohort_id", params.cohort_id);
    if (params?.start) query.set("start", params.start);
    if (params?.end) query.set("end", params.end);
    return `${API_URL}/v1/admin/export/${type}?${query}`;
  },
};
