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
    answer_raw: Optional[str] = Field(None, max_length=5000)
    input_mode: str = "none"
    transcript: Optional[str] = Field(None, max_length=5000)
    is_vague: Optional[bool] = None
    followups_asked: int = 0
    followup_1: Optional[str] = Field(None, max_length=500)
    followup_1_answer: Optional[str] = Field(None, max_length=5000)
    followup_2: Optional[str] = Field(None, max_length=500)
    followup_2_answer: Optional[str] = Field(None, max_length=5000)


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


class CleanupRequest(BaseModel):
    raw_text: str = Field(..., max_length=5000)


class CleanupResponse(BaseModel):
    cleaned: str
    changed: bool


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
    max_submissions_per_ip: int = 1
    created_at: datetime


class CreateCohortRequest(BaseModel):
    name: str
    course_name: str


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
