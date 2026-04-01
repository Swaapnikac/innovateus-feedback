"""Add Qualtrics sync tracking

Revision ID: 007
Revises: 006
Create Date: 2026-03-31
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'submissions' AND column_name = 'qualtrics_synced_at'"
    ))
    if result.fetchone() is None:
        op.add_column("submissions", sa.Column("qualtrics_synced_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "qualtrics_synced_at")
