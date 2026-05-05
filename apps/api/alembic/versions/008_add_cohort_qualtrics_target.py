"""Add qualtrics_target column to cohorts.

Allows a cohort to override the global Qualtrics sync target — useful when
running a smoke-test cohort against the test survey while live cohorts go to
production. NULL falls back to ``settings.qualtrics_default_target``.

Revision ID: 008
Revises: 007
Create Date: 2026-05-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cohorts",
        sa.Column("qualtrics_target", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cohorts", "qualtrics_target")
