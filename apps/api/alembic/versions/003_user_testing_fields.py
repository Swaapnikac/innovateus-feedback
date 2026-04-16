"""User-testing fields for the Apr 22 soft launch.

Adds fields needed to measure H1-H6 hypotheses and S1-S10 success criteria:
- cohorts: launch_phase, facilitator + deployment feedback
- submissions: device/browser/OS, mic permission, voice session summary,
  reliability (api latency, errors, timeouts), abandonment stage,
  Qualtrics sync tracking
- answers: timing, word/char counts, vagueness scoring, voice session detail,
  transcript raw/final + edit distance, mode-switch flags, follow-up
  vagueness re-classification
- extractions: model + prompt metadata, success flag, confidence, sentiment
- new table extraction_reviews for H4 manual usefulness/accuracy ratings

All new columns are nullable with safe defaults so existing rows keep working.

Revision ID: 003
Revises: 002
Create Date: 2026-04-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ─────────────────────────────────────────────────────────────────────────────
# cohorts: facilitator + launch phase
# ─────────────────────────────────────────────────────────────────────────────

COHORT_COLUMNS = [
    sa.Column("launch_phase", sa.String(32), nullable=True, server_default="soft_launch"),
    sa.Column("facilitator_name", sa.String(255), nullable=True),
    sa.Column("facilitator_email", sa.String(255), nullable=True),
    sa.Column("source_channel", sa.String(64), nullable=True),
    sa.Column("facilitator_feedback_text", sa.Text, nullable=True),
    sa.Column("facilitator_feedback_received_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("facilitator_reported_issue_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("facilitator_issue_type", sa.String(64), nullable=True),
    sa.Column("facilitator_issue_notes", sa.Text, nullable=True),
]


# ─────────────────────────────────────────────────────────────────────────────
# submissions
# ─────────────────────────────────────────────────────────────────────────────

SUBMISSION_COLUMNS = [
    # Device / technical environment
    sa.Column("browser_name", sa.String(64), nullable=True),
    sa.Column("browser_version", sa.String(32), nullable=True),
    sa.Column("os_name", sa.String(64), nullable=True),
    sa.Column("os_version", sa.String(32), nullable=True),
    sa.Column("device_type", sa.String(32), nullable=True),
    sa.Column("user_agent", sa.Text, nullable=True),
    sa.Column("screen_size", sa.String(32), nullable=True),
    sa.Column("connection_type", sa.String(32), nullable=True),
    sa.Column("page_load_time_ms", sa.Integer, nullable=True),
    # Voice session
    sa.Column("mic_permission_status", sa.String(16), nullable=True),
    sa.Column("mic_permission_prompted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("voice_supported_in_browser", sa.Boolean, nullable=True),
    sa.Column("speech_recognition_provider_used", sa.String(32), nullable=True),
    sa.Column("started_in_voice", sa.Boolean, nullable=True),
    sa.Column("ended_in_voice", sa.Boolean, nullable=True),
    sa.Column("switched_voice_to_text_any", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("switched_text_to_voice_any", sa.Boolean, nullable=True, server_default=sa.false()),
    # Reliability
    sa.Column("avg_api_latency_ms", sa.Integer, nullable=True),
    sa.Column("max_api_latency_ms", sa.Integer, nullable=True),
    sa.Column("total_api_calls", sa.Integer, nullable=True, server_default="0"),
    sa.Column("total_api_failures", sa.Integer, nullable=True, server_default="0"),
    sa.Column("timeout_count", sa.Integer, nullable=True, server_default="0"),
    sa.Column("critical_error_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("sentry_error_count", sa.Integer, nullable=True, server_default="0"),
    sa.Column("client_error_count", sa.Integer, nullable=True, server_default="0"),
    # Abandonment
    sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("abandonment_stage", sa.String(64), nullable=True),
    # Qualtrics sync tracking
    sa.Column("qualtrics_sync_attempt_count", sa.Integer, nullable=True, server_default="0"),
    sa.Column("qualtrics_sync_first_attempt_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("qualtrics_sync_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("qualtrics_sync_last_error", sa.Text, nullable=True),
    sa.Column("qualtrics_sync_latency_ms", sa.Integer, nullable=True),
    sa.Column("qualtrics_response_id", sa.String(128), nullable=True),
    # Participant optional feedback
    sa.Column("voice_experience_rating", sa.Integer, nullable=True),
    sa.Column("voice_experience_text", sa.Text, nullable=True),
    sa.Column("confusion_flag", sa.Boolean, nullable=True),
    sa.Column("confusion_step", sa.String(64), nullable=True),
    sa.Column("would_use_again_flag", sa.Boolean, nullable=True),
    sa.Column("preferred_mode_next_time", sa.String(16), nullable=True),
    sa.Column("reported_issue_flag", sa.Boolean, nullable=True),
    sa.Column("reported_issue_text", sa.Text, nullable=True),
    # Governance
    sa.Column("pii_detected_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("pii_redaction_applied_flag", sa.Boolean, nullable=True, server_default=sa.true()),
    sa.Column("privacy_notice_version", sa.String(20), nullable=True, server_default="1.0"),
    sa.Column("records_retention_tag", sa.String(32), nullable=True, server_default="standard"),
]


# ─────────────────────────────────────────────────────────────────────────────
# answers
# ─────────────────────────────────────────────────────────────────────────────

ANSWER_COLUMNS = [
    # Content metrics
    sa.Column("answer_word_count", sa.Integer, nullable=True),
    sa.Column("answer_char_count", sa.Integer, nullable=True),
    sa.Column("answer_language", sa.String(16), nullable=True),
    # Per-question timing
    sa.Column("answer_started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("answer_completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("answer_duration_sec", sa.Integer, nullable=True),
    sa.Column("answer_skipped", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("skip_reason", sa.String(64), nullable=True),
    sa.Column("changed_answer_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("edited_after_transcription_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    # Vagueness detail
    sa.Column("vagueness_score_initial", sa.Float, nullable=True),
    sa.Column("vagueness_reason_initial", sa.Text, nullable=True),
    sa.Column("followup_1_is_vague", sa.Boolean, nullable=True),
    sa.Column("followup_1_vagueness_score", sa.Float, nullable=True),
    sa.Column("followup_2_is_vague", sa.Boolean, nullable=True),
    sa.Column("followup_2_vagueness_score", sa.Float, nullable=True),
    sa.Column("final_response_specific_flag", sa.Boolean, nullable=True),
    sa.Column("specificity_improved_after_followups_flag", sa.Boolean, nullable=True),
    # Voice session detail
    sa.Column("voice_duration_sec", sa.Integer, nullable=True),
    sa.Column("transcript_raw", sa.Text, nullable=True),
    sa.Column("transcript_final", sa.Text, nullable=True),
    sa.Column("transcript_edit_distance", sa.Integer, nullable=True),
    sa.Column("user_edited_transcript_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("silence_auto_stop_triggered_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("switched_from_voice_to_text_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("switched_from_text_to_voice_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("mic_denied_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("audio_capture_error_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    # Follow-up input modes + word counts
    sa.Column("followup_1_input_mode", sa.String(10), nullable=True),
    sa.Column("followup_1_word_count", sa.Integer, nullable=True),
    sa.Column("followup_2_input_mode", sa.String(10), nullable=True),
    sa.Column("followup_2_word_count", sa.Integer, nullable=True),
    sa.Column("followup_1_skipped_flag", sa.Boolean, nullable=True, server_default=sa.false()),
    sa.Column("followup_2_skipped_flag", sa.Boolean, nullable=True, server_default=sa.false()),
]


# ─────────────────────────────────────────────────────────────────────────────
# extractions
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_COLUMNS = [
    sa.Column("model_name", sa.String(64), nullable=True),
    sa.Column("model_version", sa.String(32), nullable=True),
    sa.Column("prompt_version", sa.String(32), nullable=True),
    sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("success_flag", sa.Boolean, nullable=True),
    sa.Column("error_message", sa.Text, nullable=True),
    sa.Column("confidence", sa.Float, nullable=True),
    sa.Column("sentiment", sa.String(16), nullable=True),
]


def upgrade() -> None:
    # cohorts
    for col in COHORT_COLUMNS:
        op.add_column("cohorts", col)

    # submissions
    for col in SUBMISSION_COLUMNS:
        op.add_column("submissions", col)

    # answers
    for col in ANSWER_COLUMNS:
        op.add_column("answers", col)

    # extractions
    for col in EXTRACTION_COLUMNS:
        op.add_column("extractions", col)

    # Backfill answer_word_count / answer_char_count from existing answer_raw
    op.execute(
        "UPDATE answers SET "
        "answer_char_count = COALESCE(char_length(answer_raw), 0), "
        "answer_word_count = COALESCE(array_length(regexp_split_to_array(trim(coalesce(answer_raw, '')), '\\s+'), 1), 0) "
        "WHERE answer_word_count IS NULL"
    )
    # Backfill followup word counts
    op.execute(
        "UPDATE answers SET "
        "followup_1_word_count = CASE WHEN followup_1_answer IS NOT NULL AND length(trim(followup_1_answer)) > 0 "
        "  THEN array_length(regexp_split_to_array(trim(followup_1_answer), '\\s+'), 1) ELSE 0 END, "
        "followup_2_word_count = CASE WHEN followup_2_answer IS NOT NULL AND length(trim(followup_2_answer)) > 0 "
        "  THEN array_length(regexp_split_to_array(trim(followup_2_answer), '\\s+'), 1) ELSE 0 END "
        "WHERE followup_1_word_count IS NULL OR followup_2_word_count IS NULL"
    )

    # extraction_reviews table (H4 manual usefulness/accuracy review)
    op.create_table(
        "extraction_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "submission_id",
            UUID(as_uuid=True),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("reviewed_by", sa.String(128), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("accuracy_rating", sa.Integer, nullable=True),
        sa.Column("usefulness_rating", sa.Integer, nullable=True),
        sa.Column("useful_flag", sa.Boolean, nullable=True),
        sa.Column("accuracy_notes", sa.Text, nullable=True),
        sa.Column("usefulness_notes", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_extraction_reviews_submission_id",
        "extraction_reviews",
        ["submission_id"],
    )

    # Helpful indexes for event denormalization reads
    op.create_index("ix_answers_question_id", "answers", ["question_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_submission_id", "events", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_events_submission_id", table_name="events")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_index("ix_answers_question_id", table_name="answers")
    op.drop_index("ix_extraction_reviews_submission_id", table_name="extraction_reviews")
    op.drop_table("extraction_reviews")

    for col in reversed(EXTRACTION_COLUMNS):
        op.drop_column("extractions", col.name)
    for col in reversed(ANSWER_COLUMNS):
        op.drop_column("answers", col.name)
    for col in reversed(SUBMISSION_COLUMNS):
        op.drop_column("submissions", col.name)
    for col in reversed(COHORT_COLUMNS):
        op.drop_column("cohorts", col.name)
