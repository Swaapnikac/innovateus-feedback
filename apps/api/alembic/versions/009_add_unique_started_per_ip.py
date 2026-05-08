"""Partial unique index to close the per-IP submission-cap race.

Two concurrent ``POST /v1/submissions/start`` calls for the same
``(cohort_id, ip_hash)`` could both pass the application-level "completed
count < limit" check and both insert ``status='started'`` rows, ultimately
yielding two completed submissions when the cohort cap was 1.

Closing that with a partial unique index on ``(cohort_id, ip_hash) WHERE
status='started'`` makes Postgres atomically reject the second insert.
The router catches ``IntegrityError`` and returns the existing row
(resume) or 429 if the IP is already at the completed cap.

We deliberately scope the partial index to ``status='started'`` only — we
don't want to block multiple ``completed`` rows for cohorts that opt in
to ``max_submissions_per_ip > 1``; that completed-count cap is enforced
at the application layer where we know the cohort's setting.

Revision ID: 009
Revises: 008
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "uq_submissions_started_per_ip_cohort"


def upgrade() -> None:
    # Pre-clean any duplicate ``started`` rows that might exist from before
    # this constraint. Keeps only the most recently created started row
    # per (cohort_id, ip_hash) and marks the rest as ``abandoned`` so they
    # don't break the unique index. The data loss here is intentional —
    # they would have been abandoned anyway once the user finished the
    # newer submission.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY cohort_id, ip_hash
                       ORDER BY created_at DESC NULLS LAST, id DESC
                   ) AS rn
            FROM submissions
            WHERE status = 'started'
        )
        UPDATE submissions
        SET status = 'abandoned'
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
        """
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX_NAME}
        ON submissions (cohort_id, ip_hash)
        WHERE status = 'started';
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME};")
