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


class SurveyConfig(BaseModel):
    version: str
    title: str
    questions: list[SurveyQuestion]


class StartSubmissionRequest(BaseModel):
    cohort_id: uuid.UUID
    consent_version: str = "1.0"
    client_metadata: Optional[dict] = None


class StartSubmissionResponse(BaseModel):
    submission_id: uuid.UUID


class AnswerRequest(BaseModel):
    question_id: str
    question_type: str
    answer_raw: Optional[str] = None
    input_mode: str = "none"
    transcript: Optional[str] = None
    is_vague: Optional[bool] = None
    followups_asked: int = 0
    followup_1: Optional[str] = None
    followup_1_answer: Optional[str] = None
    followup_2: Optional[str] = None
    followup_2_answer: Optional[str] = None


class AnswerResponse(BaseModel):
    id: uuid.UUID
    question_id: str


class VaguenessRequest(BaseModel):
    question_text: str
    answer_text: str


class VaguenessResponse(BaseModel):
    is_vague: bool
    reason: str
    missing_info_types: list[str]


class FollowUpRequest(BaseModel):
    question_text: str
    answer_text: str
    missing_info_types: list[str]


class FollowUpResponse(BaseModel):
    followups: list[str]


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
    answers: list[dict] = []
    extraction: Optional[dict] = None

    model_config = {"from_attributes": True}


class PaginatedResponses(BaseModel):
    items: list[SubmissionSummary]
    total: int
    page: int
    page_size: int


class CohortResponse(BaseModel):
    id: uuid.UUID
    name: str
    course_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
