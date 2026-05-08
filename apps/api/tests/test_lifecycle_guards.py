"""Tests for the post-token lifecycle guards on submission mutations.

The HMAC submission token proves identity. ``_ensure_started`` is the
second gate: a row that has reached ``completed`` (or ``abandoned``) is
sealed even if the caller still holds a valid token. These tests pin
down the exact statuses we accept and reject.

The CSV-formula-injection helper (``_csv_safe``) is here too so we keep
all "data we hand to admins downstream" guards in one place.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.submissions import _ensure_started
from app.services.export_service import _csv_safe, _csv_safe_row


class _StubSubmission:
    """Stand-in for a `Submission` ORM row — only ``status`` matters here."""

    def __init__(self, status: str):
        self.status = status


def test_ensure_started_accepts_in_progress():
    _ensure_started(_StubSubmission("started"))


@pytest.mark.parametrize("status", ["completed", "abandoned", "expired", "", "started "])
def test_ensure_started_rejects_non_started(status: str):
    with pytest.raises(HTTPException) as excinfo:
        _ensure_started(_StubSubmission(status))
    assert excinfo.value.status_code == 409


def test_csv_safe_passes_through_safe_strings():
    for value in ("hello", "user said yes", "", "123 main st"):
        assert _csv_safe(value) == value


@pytest.mark.parametrize(
    "raw",
    [
        "=cmd|'/c calc'!A1",
        "+1 to that",
        "-bad data",
        "@SUM(A1:A10)",
        "\tleading tab",
        "\rcarriage return",
    ],
)
def test_csv_safe_defuses_formula_prefixes(raw: str):
    out = _csv_safe(raw)
    assert out.startswith("'")
    assert out[1:] == raw


def test_csv_safe_leaves_non_strings_alone():
    for value in (None, 42, 3.14, True, False):
        assert _csv_safe(value) == value


def test_csv_safe_row_applies_to_each_cell():
    row = ["clean", "=BAD()", 7, None, "+also bad"]
    out = _csv_safe_row(row)
    assert out == ["clean", "'=BAD()", 7, None, "'+also bad"]
