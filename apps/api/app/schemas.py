from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class SurveyQuestion(BaseModel):
    id: str
    type: str
    text: str
    description: Optional[str] = None
    options: Optional[list] = None
    required: bool = True
    voice_eligible: bool = False
    condition: Optional[dict] = None
    group: Optional[str] = None
    # Slider-specific
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    scale_step: Optional[float] = None
    # Matrix-specific — rows rated against `options` (columns)
    rows: Optional[list[str]] = None
    # NPS / scale endpoint labels
    labels: Optional[dict] = None


class QuestionGroup(BaseModel):
    id: str
    label: str
    randomize: bool = False


class SurveyConfig(BaseModel):
    version: str
    title: str
    questions: list[SurveyQuestion]
    question_groups: list[QuestionGroup] = []


class StartSubmissionRequest(BaseModel):
    cohort_id: uuid.UUID
    consent_version: str = "1.0"
    client_metadata: Optional[dict] = None


class StartSubmissionResponse(BaseModel):
    submission_id: uuid.UUID


class AnswerRequest(BaseModel):
    question_id: str
    question_type: str
    question_text: Optional[str] = Field(None, max_length=1000)
    answer_raw: Optional[str] = Field(None, max_length=5000)
    input_mode: str = "none"
    transcript: Optional[str] = Field(None, max_length=5000)
    is_vague: Optional[bool] = None
    followups_asked: int = 0
    followup_1: Optional[str] = Field(None, max_length=500)
    followup_1_answer: Optional[str] = Field(None, max_length=5000)
    followup_2: Optional[str] = Field(None, max_length=500)
    followup_2_answer: Optional[str] = Field(None, max_length=5000)
    # Voice/transcript detail
    transcript_raw: Optional[str] = Field(None, max_length=5000)
    voice_duration_sec: Optional[int] = Field(None, ge=0, le=3600)
    followup_1_input_mode: Optional[str] = Field(None, max_length=10)
    followup_2_input_mode: Optional[str] = Field(None, max_length=10)
    answer_skipped: Optional[bool] = None


class ClientEnvRequest(BaseModel):
    user_agent: Optional[str] = Field(None, max_length=1024)
    screen_size: Optional[str] = Field(None, max_length=32)
    connection_type: Optional[str] = Field(None, max_length=32)
    page_load_time_ms: Optional[int] = Field(None, ge=0, le=600000)
    voice_supported: Optional[bool] = None
    mic_permission_status: Optional[str] = Field(None, max_length=16)


class AnswerResponse(BaseModel):
    id: uuid.UUID
    question_id: str


class VaguenessRequest(BaseModel):
    question_text: str = Field(..., max_length=500)
    answer_text: str = Field(..., max_length=5000)


class VaguenessResponse(BaseModel):
    is_vague: bool
    is_irrelevant: bool = False
    reason: str
    missing_info_types: list[str]
    vagueness_score: Optional[float] = None
    error: bool = False


class FollowUpRequest(BaseModel):
    question_text: str = Field(..., max_length=500)
    answer_text: str = Field(..., max_length=5000)
    missing_info_types: list[str]


class FollowUpResponse(BaseModel):
    followups: list[str]


class VaguenessWithFollowupsResponse(BaseModel):
    is_vague: bool
    is_irrelevant: bool = False
    reason: str
    missing_info_types: list[str]
    followups: list[str]
    vagueness_score: Optional[float] = None
    declined: bool = False
    error: bool = False


class FollowUpCheckRequest(BaseModel):
    """Payload for evaluating whether a follow-up answer needs one more
    clarification. Includes the original question + answer as context so the
    model can tell this isn't a fresh main-question response."""

    original_question: str = Field(..., max_length=500)
    original_answer: str = Field(..., max_length=5000)
    followup_question: str = Field(..., max_length=500)
    followup_answer: str = Field(..., max_length=5000)


class CleanupRequest(BaseModel):
    raw_text: str = Field(..., max_length=5000)


class CleanupResponse(BaseModel):
    cleaned: str
    changed: bool


class PiiCheckRequest(BaseModel):
    text: str = Field(..., max_length=5000)


class PiiCheckResponse(BaseModel):
    found: bool
    count: int
    categories: list[str]


class CompleteSubmissionResponse(BaseModel):
    status: str
    extraction: Optional[dict] = None


class ExtractionResponse(BaseModel):
    what_was_tried: Optional[str] = None
    planned_task_or_workflow: Optional[str] = None
    outcome_or_expected_outcome: Optional[str] = None
    barriers: Optional[list[str]] = None
    enablers: Optional[list[str]] = None
    public_benefit: Optional[str] = None
    top_themes: Optional[list[str]] = None
    success_story_candidate: Optional[str] = None


class TranscriptResponse(BaseModel):
    transcript: str
    pii_redaction_applied: bool = False
    pii_redaction_categories: list[str] = []


class AdminLoginRequest(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    token: str


class MetricsResponse(BaseModel):
    total_submissions: int
    completed_submissions: int
    completion_rate: float
    avg_time_to_complete_sec: Optional[float] = None
    avg_recommend_score: Optional[float] = None
    confidence_distribution: dict
    vagueness_rate: Optional[float] = None


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    cohort_id: uuid.UUID
    created_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    time_to_complete_sec: Optional[int] = None
    survey_version: Optional[str] = None
    ip_hash: Optional[str] = None
    answers: list[dict] = []
    extraction: Optional[dict] = None



class PaginatedResponses(BaseModel):
    items: list[SubmissionSummary]
    total: int
    page: int
    page_size: int


class CohortResponse(BaseModel):
    id: uuid.UUID
    name: str
    course_name: str
    program_type: Optional[str] = None
    max_submissions_per_ip: int = 1
    created_at: datetime


class CreateCohortRequest(BaseModel):
    name: str
    course_name: str = ""
    program_type: str


class GenerateSurveyRequest(BaseModel):
    goal_description: str = Field(..., min_length=10, max_length=4000)
    program_type: Optional[str] = None
    question_count: int = Field(8, ge=3, le=14)


class CohortSettingsRequest(BaseModel):
    max_submissions_per_ip: int = 1


class EditorLoginRequest(BaseModel):
    password: str


class SaveSurveyRequest(BaseModel):
    version: str = "1.0"
    title: str
    questions: list[SurveyQuestion]
    question_groups: list[QuestionGroup] = []


class SurveyVersionSummary(BaseModel):
    version_label: str
    change_summary: Optional[str] = None
    created_at: datetime
    created_by: str



class SurveyVersionDetail(SurveyVersionSummary):
    config: dict


# ── Analytics Events ──

class EventPayload(BaseModel):
    event_type: str
    event_data: dict = {}
    timestamp: Optional[str] = None


class TrackEventsRequest(BaseModel):
    session_token: str
    cohort_id: Optional[str] = None
    submission_id: Optional[str] = None
    events: list[EventPayload] = Field(..., max_length=10)


class DropoutRequest(BaseModel):
    session_token: str
    cohort_id: str
    submission_id: Optional[str] = None
    last_question_id: str
    questions_answered: int


# ── Experience Rating ──

class ExperienceRatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    feedback_text: Optional[str] = Field(None, max_length=500)
    voice_experience_rating: Optional[int] = Field(None, ge=1, le=5)
    voice_experience_text: Optional[str] = Field(None, max_length=500)
    would_use_again: Optional[bool] = None
    preferred_mode_next_time: Optional[str] = Field(None, max_length=16)
    confusion_flag: Optional[bool] = None
    confusion_step: Optional[str] = Field(None, max_length=64)
    reported_issue_flag: Optional[bool] = None
    reported_issue_text: Optional[str] = Field(None, max_length=500)


# ── Extraction review (H4) ──


class ReviewRequest(BaseModel):
    reviewed_by: str = Field(..., min_length=1, max_length=128)
    useful_flag: Optional[bool] = None
    accuracy_rating: Optional[int] = Field(None, ge=1, le=5)
    usefulness_rating: Optional[int] = Field(None, ge=1, le=5)
    accuracy_notes: Optional[str] = Field(None, max_length=2000)
    usefulness_notes: Optional[str] = Field(None, max_length=2000)


class ReviewResponse(BaseModel):
    submission_id: uuid.UUID
    reviewed_by: str
    reviewed_at: datetime
    useful_flag: Optional[bool] = None
    accuracy_rating: Optional[int] = None
    usefulness_rating: Optional[int] = None
    accuracy_notes: Optional[str] = None
    usefulness_notes: Optional[str] = None


# ── Facilitator feedback ──


class FacilitatorFeedbackRequest(BaseModel):
    facilitator_name: Optional[str] = Field(None, max_length=255)
    facilitator_email: Optional[str] = Field(None, max_length=255)
    source_channel: Optional[str] = Field(None, max_length=64)
    launch_phase: Optional[str] = Field(None, max_length=32)
    facilitator_feedback_text: Optional[str] = Field(None, max_length=5000)
    facilitator_reported_issue_flag: Optional[bool] = None
    facilitator_issue_type: Optional[str] = Field(None, max_length=64)
    facilitator_issue_notes: Optional[str] = Field(None, max_length=2000)
