"""Convert naive timestamp columns to TIMESTAMPTZ.

The ORM models declare ``DateTime(timezone=True)`` for all created_at /
completed_at / synced_at / timestamp columns, and the application stores
``datetime.now(timezone.utc)`` values.  Several of these columns, however,
were created as ``timestamp without time zone`` in earlier migrations.

When asyncpg writes a tz-aware UTC value into a naive column, it converts
the value to the database session's local timezone and drops the offset.
So rows inserted so far are stored as *local wall-clock* time (not UTC).
On machines where the DB session timezone is not UTC (e.g. IST / UTC+5:30
or America/New_York / UTC-4..5), this causes ``time_to_complete_sec`` and
any other duration computed from ``created_at`` to be off by the local
offset.

This migration rewrites the affected columns to ``timestamp with time
zone``.  For the cast we reinterpret the existing naive values using the
database session's current TimeZone (which is the same zone asyncpg used
when writing the values), so the stored instants are preserved and
correct regardless of where the migration is run.

Revision ID: 004
Revises: 003
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NAIVE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("cohorts", "created_at"),
    ("submissions", "created_at"),
    ("submissions", "completed_at"),
    ("submissions", "jotform_synced_at"),
    ("submissions", "qualtrics_synced_at"),
    ("survey_config_versions", "created_at"),
    ("extractions", "created_at"),
    ("events", "timestamp"),
)


def upgrade() -> None:
    for table, column in _NAIVE_COLUMNS:
        op.execute(
            f"""
            ALTER TABLE {table}
            ALTER COLUMN {column}
            TYPE TIMESTAMP WITH TIME ZONE
            USING {column} AT TIME ZONE current_setting('TimeZone')
            """
        )


def downgrade() -> None:
    for table, column in _NAIVE_COLUMNS:
        op.execute(
            f"""
            ALTER TABLE {table}
            ALTER COLUMN {column}
            TYPE TIMESTAMP WITHOUT TIME ZONE
            USING {column} AT TIME ZONE current_setting('TimeZone')
            """
        )
