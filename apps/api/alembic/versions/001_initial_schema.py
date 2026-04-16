"""Full schema including experience rating and events

Revision ID: 001
Revises: None
Create Date: 2026-04-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cohorts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("course_name", sa.String(255), nullable=False),
        sa.Column("survey_config", JSONB, nullable=True),
        sa.Column("active_version", sa.String(20), nullable=True),
        sa.Column("max_submissions_per_ip", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), server_default="started"),
        sa.Column("time_to_complete_sec", sa.Integer, nullable=True),
        sa.Column("consent_version", sa.String(20), server_default="1.0"),
        sa.Column("survey_version", sa.String(20), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("client_metadata", JSONB, nullable=True),
        sa.Column("jotform_synced_at", sa.DateTime, nullable=True),
        sa.Column("qualtrics_synced_at", sa.DateTime, nullable=True),
        sa.Column("experience_rating", sa.Integer, nullable=True),
        sa.Column("experience_feedback", sa.Text, nullable=True),
        sa.Column("response_source", sa.String(20), nullable=True, server_default="web"),
    )

    op.create_table(
        "answers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("question_id", sa.String(50), nullable=False),
        sa.Column("question_type", sa.String(20), nullable=False),
        sa.Column("answer_raw", sa.Text, nullable=True),
        sa.Column("input_mode", sa.String(10), server_default="none"),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("is_vague", sa.Boolean, nullable=True),
        sa.Column("followups_asked", sa.Integer, server_default="0"),
        sa.Column("followup_1", sa.Text, nullable=True),
        sa.Column("followup_1_answer", sa.Text, nullable=True),
        sa.Column("followup_2", sa.Text, nullable=True),
        sa.Column("followup_2_answer", sa.Text, nullable=True),
    )

    op.create_table(
        "extractions",
        sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("submissions.id"), primary_key=True),
        sa.Column("what_was_tried", sa.Text, nullable=True),
        sa.Column("planned_task_or_workflow", sa.Text, nullable=True),
        sa.Column("outcome_or_expected_outcome", sa.Text, nullable=True),
        sa.Column("barriers", JSONB, nullable=True),
        sa.Column("enablers", JSONB, nullable=True),
        sa.Column("public_benefit", sa.Text, nullable=True),
        sa.Column("top_themes", JSONB, nullable=True),
        sa.Column("success_story_candidate", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "survey_config_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id"), nullable=False),
        sa.Column("version_label", sa.String(20), nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(50), server_default="editor"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_token", sa.String(128), nullable=False),
        sa.Column("cohort_id", sa.String(64), nullable=True),
        sa.Column("submission_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_data", JSONB, nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_index("ix_submissions_cohort_id", "submissions", ["cohort_id"])
    op.create_index("ix_submissions_ip_hash", "submissions", ["ip_hash"])
    op.create_index("ix_answers_submission_id", "answers", ["submission_id"])
    op.create_index("ix_events_session_token", "events", ["session_token"])
    op.create_index("ix_events_cohort_id", "events", ["cohort_id"])

    # Seed default cohort
    op.execute(
        "INSERT INTO cohorts (id, name, course_name, active_version, max_submissions_per_ip) "
        "VALUES ('00000000-0000-0000-0000-000000000001', "
        "'Using Generative AI at Work', 'Using Generative AI at Work', 'v1', 1) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("survey_config_versions")
    op.drop_table("extractions")
    op.drop_table("answers")
    op.drop_table("submissions")
    op.drop_table("cohorts")
