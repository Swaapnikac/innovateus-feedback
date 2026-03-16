"""Add survey version control

Revision ID: 003
Revises: 002
Create Date: 2026-03-16
"""
import json
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "survey_config_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id"), nullable=False),
        sa.Column("version_label", sa.String(20), nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(50), server_default="editor"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_survey_config_versions_cohort_id",
        "survey_config_versions",
        ["cohort_id"],
    )

    op.add_column("submissions", sa.Column("survey_version", sa.String(20), nullable=True))
    op.add_column("cohorts", sa.Column("active_version", sa.String(20), nullable=True))

    # Backfill: create v1 for every cohort that already has a survey_config
    conn = op.get_bind()
    cohorts = conn.execute(
        sa.text("SELECT id, survey_config FROM cohorts WHERE survey_config IS NOT NULL")
    ).fetchall()
    for row in cohorts:
        cfg_json = json.dumps(row[1]) if isinstance(row[1], dict) else row[1]
        conn.execute(
            sa.text(
                "INSERT INTO survey_config_versions (id, cohort_id, version_label, config, change_summary, created_by) "
                "VALUES (gen_random_uuid(), :cid, 'v1', CAST(:cfg AS jsonb), 'Initial version', 'system')"
            ),
            {"cid": row[0], "cfg": cfg_json},
        )
        conn.execute(
            sa.text("UPDATE cohorts SET active_version = 'v1' WHERE id = :cid"),
            {"cid": row[0]},
        )


def downgrade() -> None:
    op.drop_column("cohorts", "active_version")
    op.drop_column("submissions", "survey_version")
    op.drop_table("survey_config_versions")
