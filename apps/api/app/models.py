import uuid
from typing import Optional
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.db import Base
import enum


class SubmissionStatus(str, enum.Enum):
    started = "started"
    completed = "completed"
    abandoned = "abandoned"


class InputMode(str, enum.Enum):
    none = "none"
    text = "text"
    voice = "voice"


class Cohort(Base):
    __tablename__ = "cohorts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Optional human-friendly identifier for sharing survey URLs
    # (``/c/generative-ai``). Unique when set; falls back to UUID otherwise.
    slug: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, unique=True, index=True)
    # Historical slugs kept as redirect aliases so old QR codes / printed
    # links never break after a rename. ``resolve_cohort`` matches against
    # either ``slug`` or any element of this array.
    previous_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)),
        nullable=False,
        default=list,
        server_default="{}",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    program_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    survey_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    active_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    max_submissions_per_ip: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    # Launch / facilitator metadata (user-testing)
    launch_phase: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="soft_launch")
    facilitator_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    facilitator_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_channel: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    facilitator_feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    facilitator_feedback_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    facilitator_reported_issue_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    facilitator_issue_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    facilitator_issue_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Qualtrics sync target — NULL falls back to settings.qualtrics_default_target.
    # Allowed: "production" | "test" | "none".
    qualtrics_target: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    submissions: Mapped[list["Submission"]] = relationship(back_populates="cohort")
    versions: Mapped[list["SurveyConfigVersion"]] = relationship(back_populates="cohort", order_by="SurveyConfigVersion.created_at.desc()")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cohorts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=SubmissionStatus.started.value)
    time_to_complete_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    consent_version: Mapped[str] = mapped_column(String(20), default="1.0")
    survey_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    client_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    jotform_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    qualtrics_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    experience_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    experience_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="web")

    # ── Device / technical environment ──
    browser_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    browser_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    os_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screen_size: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    connection_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    page_load_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Voice session summary ──
    mic_permission_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    mic_permission_prompted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    voice_supported_in_browser: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    speech_recognition_provider_used: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    started_in_voice: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ended_in_voice: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    switched_voice_to_text_any: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    switched_text_to_voice_any: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)

    # ── Reliability ──
    avg_api_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_api_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_api_calls: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    total_api_failures: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    timeout_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    critical_error_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    sentry_error_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    client_error_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

    # ── Abandonment ──
    abandoned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    abandonment_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # ── Qualtrics sync tracking ──
    qualtrics_sync_attempt_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    qualtrics_sync_first_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    qualtrics_sync_last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    qualtrics_sync_last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qualtrics_sync_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    qualtrics_response_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # ── Optional participant feedback ──
    voice_experience_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    voice_experience_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confusion_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    confusion_step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    would_use_again_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    preferred_mode_next_time: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reported_issue_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    reported_issue_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Governance ──
    pii_detected_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    pii_redaction_applied_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    pii_redaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pii_redaction_categories: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    privacy_notice_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="1.0")
    records_retention_tag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="standard")

    cohort: Mapped["Cohort"] = relationship(back_populates="submissions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="submission", cascade="all, delete-orphan")
    extraction: Mapped[Optional["Extraction"]] = relationship(back_populates="submission", uselist=False)
    review: Mapped[Optional["ExtractionReview"]] = relationship(back_populates="submission", uselist=False)


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("submissions.id"), nullable=False)
    question_id: Mapped[str] = mapped_column(String(50), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    answer_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_mode: Mapped[str] = mapped_column(String(10), default=InputMode.none.value)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_vague: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    followups_asked: Mapped[int] = mapped_column(Integer, default=0)
    followup_1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followup_1_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followup_2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followup_2_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Content metrics
    answer_word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Timing
    answer_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    answer_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    answer_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_skipped: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    skip_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    changed_answer_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    edited_after_transcription_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)

    # Vagueness detail
    vagueness_score_initial: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vagueness_reason_initial: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followup_1_is_vague: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    followup_1_vagueness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    followup_2_is_vague: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    followup_2_vagueness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    final_response_specific_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    specificity_improved_after_followups_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Voice detail
    voice_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transcript_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_final: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_edit_distance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_edited_transcript_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    silence_auto_stop_triggered_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    switched_from_voice_to_text_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    switched_from_text_to_voice_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    mic_denied_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    audio_capture_error_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)

    # Follow-up detail
    followup_1_input_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    followup_1_word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    followup_2_input_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    followup_2_word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    followup_1_skipped_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    followup_2_skipped_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)

    submission: Mapped["Submission"] = relationship(back_populates="answers")


class Extraction(Base):
    __tablename__ = "extractions"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id"), primary_key=True
    )
    what_was_tried: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    planned_task_or_workflow: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome_or_expected_outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    barriers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    enablers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    public_benefit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    top_themes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    success_story_candidate: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    # Model / prompt metadata
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    success_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sentiment: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    submission: Mapped["Submission"] = relationship(back_populates="extraction")


class ExtractionReview(Base):
    """Human review of an extraction — filled in by managers (H4)."""

    __tablename__ = "extraction_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    reviewed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    accuracy_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usefulness_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    useful_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    accuracy_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usefulness_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submission: Mapped["Submission"] = relationship(back_populates="review")


class SurveyConfigVersion(Base):
    __tablename__ = "survey_config_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cohorts.id"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), default="editor")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    cohort: Mapped["Cohort"] = relationship(back_populates="versions")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_token: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cohort_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    submission_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
