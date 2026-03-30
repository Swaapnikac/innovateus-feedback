"""Add Qualtrics sync tracking

Revision ID: 005
Revises: 004
Create Date: 2026-03-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("qualtrics_synced_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "qualtrics_synced_at")
