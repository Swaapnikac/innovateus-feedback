"""Initial schema

Revision ID: 001
Revises: None
Create Date: 2026-02-26
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
        sa.Column("language_default", sa.String(5), server_default="en"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), server_default="started"),
        sa.Column("language", sa.String(5), server_default="en"),
        sa.Column("time_to_complete_sec", sa.Integer, nullable=True),
        sa.Column("consent_version", sa.String(20), server_default="1.0"),
        sa.Column("client_metadata", JSONB, nullable=True),
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

    op.create_index("ix_submissions_cohort_id", "submissions", ["cohort_id"])
    op.create_index("ix_answers_submission_id", "answers", ["submission_id"])
    op.create_index("ix_answers_question_id", "answers", ["question_id"])


def downgrade() -> None:
    op.drop_table("extractions")
    op.drop_table("answers")
    op.drop_table("submissions")
    op.drop_table("cohorts")
