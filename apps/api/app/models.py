import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db import Base
import enum


class SubmissionStatus(str, enum.Enum):
    started = "started"
    completed = "completed"
    abandoned = "abandoned"


class QuestionType(str, enum.Enum):
    rating = "rating"
    mcq = "mcq"
    multi = "multi"
    open = "open"


class InputMode(str, enum.Enum):
    none = "none"
    text = "text"
    voice = "voice"


class Cohort(Base):
    __tablename__ = "cohorts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    survey_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    submissions: Mapped[list["Submission"]] = relationship(back_populates="cohort")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cohorts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=SubmissionStatus.started.value)
    time_to_complete_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    consent_version: Mapped[str] = mapped_column(String(20), default="1.0")
    client_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    cohort: Mapped["Cohort"] = relationship(back_populates="submissions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="submission", cascade="all, delete-orphan")
    extraction: Mapped[Optional["Extraction"]] = relationship(back_populates="submission", uselist=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    submission: Mapped["Submission"] = relationship(back_populates="extraction")
