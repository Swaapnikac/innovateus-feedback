"""Add ballot-box stuffing protection

Revision ID: 004
Revises: 003
Create Date: 2026-03-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("ip_hash", sa.String(64), nullable=True))
    op.add_column("cohorts", sa.Column("max_submissions_per_ip", sa.Integer, server_default="1"))

    op.create_index(
        "ix_submissions_cohort_ip_hash",
        "submissions",
        ["cohort_id", "ip_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_cohort_ip_hash", table_name="submissions")
    op.drop_column("cohorts", "max_submissions_per_ip")
    op.drop_column("submissions", "ip_hash")
