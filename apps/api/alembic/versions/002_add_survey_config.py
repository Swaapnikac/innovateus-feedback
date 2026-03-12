"""Add survey_config JSONB column to cohorts

Revision ID: 002
Revises: 001
Create Date: 2026-03-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cohorts", sa.Column("survey_config", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("cohorts", "survey_config")
