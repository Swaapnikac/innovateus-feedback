"""Add nullable, unique slug column to cohorts.

Lets admins share friendly survey URLs like ``/c/generative-ai`` instead of
the internal UUID. Existing rows keep working because every cohort lookup
now resolves either the UUID primary key OR the slug. Backfills the default
Generative AI cohort with the slug ``generative-ai`` so the launch URL works
without a manual edit.

Revision ID: 006
Revises: 005
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cohorts",
        sa.Column("slug", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_cohorts_slug",
        "cohorts",
        ["slug"],
        unique=True,
    )
    # Backfill the default cohort row created by migration 001 so the live
    # launch URL ``/c/generative-ai`` resolves out-of-the-box. Other cohorts
    # keep ``slug = NULL`` until an admin sets one.
    op.execute(
        "UPDATE cohorts SET slug = 'generative-ai' "
        "WHERE id = '00000000-0000-0000-0000-000000000001' AND slug IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_cohorts_slug", table_name="cohorts")
    op.drop_column("cohorts", "slug")
