"""Add previous_slugs alias array to cohorts.

Lets admins rename a cohort's slug without breaking already-shared QR codes
or links. When the slug changes the old value is appended to
``previous_slugs`` and the resolver matches against either the current slug
or any historical alias, so legacy URLs keep redirecting to the same cohort
forever.

Stores the aliases as a Postgres ``ARRAY(String(80))`` on the cohort row
itself (no separate table) so reads stay one query and writes stay atomic
with the slug change. A GIN index keeps ``ANY()`` lookups fast even after
many renames.

Revision ID: 007
Revises: 006
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cohorts",
        sa.Column(
            "previous_slugs",
            sa.ARRAY(sa.String(length=80)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_cohorts_previous_slugs",
        "cohorts",
        ["previous_slugs"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_cohorts_previous_slugs", table_name="cohorts")
    op.drop_column("cohorts", "previous_slugs")
