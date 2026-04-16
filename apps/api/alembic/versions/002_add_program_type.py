"""Add program_type to cohorts

Revision ID: 002
Revises: 001
Create Date: 2026-04-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cohorts", sa.Column("program_type", sa.String(20), nullable=True))
    # Backfill existing cohorts to "course"
    op.execute("UPDATE cohorts SET program_type = 'course' WHERE program_type IS NULL")
    # Rename the default cohort
    op.execute(
        "UPDATE cohorts SET name = 'Using Generative AI at Work', course_name = 'Using Generative AI at Work' "
        "WHERE id = '00000000-0000-0000-0000-000000000001'"
    )


def downgrade() -> None:
    op.drop_column("cohorts", "program_type")
