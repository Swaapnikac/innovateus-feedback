"""Add pii_redaction_count and pii_redaction_categories to submissions.

Tracks how many PII patterns were stripped from a participant's answers
(and which categories fired) so admins can review privacy health without
ever seeing the actual PII.

Revision ID: 005
Revises: 004
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column(
            "pii_redaction_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "submissions",
        sa.Column(
            "pii_redaction_categories",
            sa.JSON(),
            nullable=True,
        ),
    )
    # The existing pii_redaction_applied_flag defaulted to True for every row
    # regardless of whether anything was actually redacted. Reset it to False
    # so historic rows start from a clean baseline; the app will mark True
    # only when strip_pii actually changes something from now on.
    op.execute("UPDATE submissions SET pii_redaction_applied_flag = FALSE WHERE pii_redaction_applied_flag IS NULL OR pii_redaction_applied_flag = TRUE")


def downgrade() -> None:
    op.drop_column("submissions", "pii_redaction_categories")
    op.drop_column("submissions", "pii_redaction_count")
