import json
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import uuid


# Hard cap on client-supplied metadata blobs and similar dicts. 8KB is more
# than enough for legitimate payloads (UA hints, screen size, locale, etc.)
# and stops oversized blobs from reaching the DB or downstream parsers.
_MAX_METADATA_BYTES = 8 * 1024

# Per-event payload cap. Analytics events (question_started, mode_switched,
# api_latency, etc.) are tiny structured dicts — anything larger is either
# a buggy client or someone abusing the unauthenticated /v1/events surface
# to fill the JSONB column.
_MAX_EVENT_DATA_BYTES = 4 * 1024


def _validate_metadata_size(value):
    if value is None:
        return value
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError):
        raise ValueError("client_metadata must be JSON-serialisable")
    if len(encoded.encode("utf-8")) > _MAX_METADATA_BYTES:
        raise ValueError(f"client_metadata exceeds {_MAX_METADATA_BYTES} byte limit")
    return value


def _validate_event_data_size(value):
    if value is None:
        return {}
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError):
        raise ValueError("event_data must be JSON-serialisable")
    if len(encoded.encode("utf-8")) > _MAX_EVENT_DATA_BYTES:
        raise ValueError(f"event_data exceeds {_MAX_EVENT_DATA_BYTES} byte limit")
    return value


class SurveyQuestion(BaseModel):
    id: str = Field(..., max_length=128)
    type: str = Field(..., max_length=32)
    text: str = Field(..., max_length=1000)
    description: Optional[str] = Field(None, max_length=2000)
    options: Optional[list] = Field(None, max_length=40)
    required: bool = True
    voice_eligible: bool = False
    condition: Optional[dict] = None
    group: Optional[str] = Field(None, max_length=64)
    # Slider-specific
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    scale_step: Optional[float] = None
    # Matrix-specific — rows rated against `options` (columns)
    rows: Optional[list[str]] = Field(None, max_length=40)
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
    # Accepts either the UUID primary key or the cohort slug
    # (``generative-ai``). The submissions router resolves the value before
    # using it, so legacy clients passing UUIDs continue to work unchanged.
    cohort_id: str = Field(..., max_length=128)
    consent_version: str = Field("1.0", max_length=32)
    client_metadata: Optional[dict] = None

    @field_validator("client_metadata")
    @classmethod
    def _cap_metadata(cls, v):
        return _validate_metadata_size(v)


class StartSubmissionResponse(BaseModel):
    submission_id: uuid.UUID
    # HMAC token the client must echo on every subsequent mutation as the
    # ``X-Submission-Token`` header. Closes the IDOR gap: knowing the
    # submission UUID alone is not enough to PATCH/answer/complete it.
    submission_token: str


class AnswerRequest(BaseModel):
    # Bounds match the Answer DB columns (question_id String(50),
    # question_type String(50)) so an oversized value yields a clean 422
    # rather than a downstream DB error.
    question_id: str = Field(..., max_length=50)
    question_type: str = Field(..., max_length=50)
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
    missing_info_types: list[str] = Field(default_factory=list, max_length=20)


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


class SavedAnswer(BaseModel):
    """Single previously-saved answer, in a shape the survey UI can map
    straight onto its in-memory ``AnswerState`` when resuming a submission.

    ``multi_values`` is pre-parsed server-side for ``multi``/``ranking``
    questions whose ``answer_raw`` was stored as a JSON-stringified array,
    so the client doesn't have to repeat that fragile string parsing.
    """

    question_id: str
    question_type: str
    value: str = ""
    multi_values: list[str] = []
    input_mode: str = "voice"
    transcript: Optional[str] = None
    is_vague: Optional[bool] = None
    followups: list[str] = []
    followup_1_answer: Optional[str] = None
    followup_2_answer: Optional[str] = None


class SubmissionAnswersResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    answers: list[SavedAnswer]


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
    # bcrypt has a 72-byte input limit and is intentionally slow. A 256
    # char cap blocks a trivial DoS where someone submits a 1MB password
    # and ties up a worker on the hash function.
    password: str = Field(..., max_length=256)


class AdminLoginResponse(BaseModel):
    # Login state is carried by the httpOnly admin_token / editor_token
    # cookie. We deliberately do not return the token in the response body
    # — that copy would be readable by JS and was being mirrored into
    # localStorage, which is an XSS-stealable surface.
    status: str = "ok"


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
    slug: Optional[str] = None
    name: str
    course_name: str
    program_type: Optional[str] = None
    max_submissions_per_ip: int = 1
    created_at: datetime


class CreateCohortRequest(BaseModel):
    # DB columns cap these at 255 chars; mirroring here gives clean 422s.
    name: str = Field(..., max_length=255)
    course_name: str = Field("", max_length=255)
    program_type: str = Field(..., max_length=64)
    # Optional human-friendly slug for the survey URL (``/c/<slug>``).
    # When omitted the cohort is reachable via its UUID only, which matches
    # legacy behaviour. When provided it must be lowercase alphanumeric +
    # hyphen, 2-60 chars; admin endpoint validates and rejects collisions.
    slug: Optional[str] = Field(None, max_length=80)


class GenerateSurveyRequest(BaseModel):
    goal_description: str = Field(..., min_length=10, max_length=4000)
    program_type: Optional[str] = None
    question_count: int = Field(8, ge=3, le=14)


class CohortSettingsRequest(BaseModel):
    # Existing setting; defaults preserve current behaviour for callers that
    # only want to update the IP cap.
    max_submissions_per_ip: int = 1
    # Optional rename / first-time assignment of the public survey slug.
    # When provided and different from the current slug, the admin endpoint
    # validates format, checks union uniqueness against every cohort's
    # current and historical slugs, and appends the old slug to
    # ``previous_slugs`` so old links still resolve.
    slug: Optional[str] = Field(None, max_length=80)


class EditorLoginRequest(BaseModel):
    password: str = Field(..., max_length=256)


class SaveSurveyRequest(BaseModel):
    version: str = Field("1.0", max_length=32)
    title: str = Field(..., max_length=300)
    questions: list[SurveyQuestion] = Field(..., max_length=80)
    question_groups: list[QuestionGroup] = Field(default_factory=list, max_length=40)


class SurveyVersionSummary(BaseModel):
    version_label: str
    change_summary: Optional[str] = None
    created_at: datetime
    created_by: str



class SurveyVersionDetail(SurveyVersionSummary):
    config: dict


# ── Analytics Events ──

class EventPayload(BaseModel):
    # Bounds mirror the ``Event`` DB columns
    # (event_type String(50), session_token String(128)) so we can rely
    # on Pydantic to reject oversized values before they hit the DB.
    event_type: str = Field(..., max_length=50)
    event_data: dict = {}
    timestamp: Optional[str] = Field(None, max_length=64)

    @field_validator("event_data")
    @classmethod
    def _cap_event_data(cls, v):
        return _validate_event_data_size(v)


class TrackEventsRequest(BaseModel):
    session_token: str = Field(..., max_length=128)
    cohort_id: Optional[str] = Field(None, max_length=128)
    submission_id: Optional[str] = Field(None, max_length=64)
    events: list[EventPayload] = Field(..., max_length=10)


class DropoutRequest(BaseModel):
    session_token: str = Field(..., max_length=128)
    cohort_id: str = Field(..., max_length=128)
    submission_id: Optional[str] = Field(None, max_length=64)
    last_question_id: str = Field(..., max_length=50)
    questions_answered: int = Field(..., ge=0, le=10_000)


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
