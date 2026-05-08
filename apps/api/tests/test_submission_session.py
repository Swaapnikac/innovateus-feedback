"""Tests for the per-submission HMAC token used to prevent IDOR.

The token is the only thing standing between a leaked submission UUID
and an attacker mutating that submission, so we want the round-trip,
mismatch, and tampering paths covered explicitly.
"""

from __future__ import annotations

import uuid

import pytest

from app import config
from app.submission_session import (
    mint_submission_token,
    verify_submission_token,
)


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    """Force a fresh Settings() per test so env-var overrides are honoured."""
    monkeypatch.setattr(config, "_settings_instance", None)
    yield
    monkeypatch.setattr(config, "_settings_instance", None)


def test_mint_then_verify_round_trip():
    sid = uuid.uuid4()
    token = mint_submission_token(sid)
    assert token.startswith("v1.")
    assert verify_submission_token(sid, token) is True


def test_verify_rejects_other_submissions_token():
    """Token for sid_a must NOT validate against sid_b."""
    sid_a = uuid.uuid4()
    sid_b = uuid.uuid4()
    token_a = mint_submission_token(sid_a)
    assert verify_submission_token(sid_b, token_a) is False


def test_verify_rejects_missing_or_blank_token():
    sid = uuid.uuid4()
    assert verify_submission_token(sid, None) is False
    assert verify_submission_token(sid, "") is False
    # Plausible-looking but unsigned values must also fail.
    assert verify_submission_token(sid, "not-a-token") is False
    assert verify_submission_token(sid, "v1.deadbeef") is False


def test_verify_rejects_truncated_token():
    sid = uuid.uuid4()
    token = mint_submission_token(sid)
    # Strip a single hex character — any tampering should invalidate.
    assert verify_submission_token(sid, token[:-1]) is False


def test_token_changes_when_secret_rotates(monkeypatch):
    """Rotating ``submission_token_secret`` must invalidate old tokens."""
    sid = uuid.uuid4()

    monkeypatch.setenv("SUBMISSION_TOKEN_SECRET", "secret-one")
    monkeypatch.setattr(config, "_settings_instance", None)
    token_old = mint_submission_token(sid)

    monkeypatch.setenv("SUBMISSION_TOKEN_SECRET", "secret-two")
    monkeypatch.setattr(config, "_settings_instance", None)
    token_new = mint_submission_token(sid)

    assert token_old != token_new
    assert verify_submission_token(sid, token_new) is True
    assert verify_submission_token(sid, token_old) is False


def test_falls_back_to_jwt_secret_when_unset(monkeypatch):
    """Backward-compat: if the dedicated secret is empty, jwt_secret is used."""
    sid = uuid.uuid4()

    monkeypatch.setenv("SUBMISSION_TOKEN_SECRET", "")
    monkeypatch.setenv("JWT_SECRET", "shared-jwt")
    monkeypatch.setattr(config, "_settings_instance", None)
    token = mint_submission_token(sid)
    assert verify_submission_token(sid, token) is True

    # Now flip JWT_SECRET — the old token should fail to verify.
    monkeypatch.setenv("JWT_SECRET", "rotated-jwt")
    monkeypatch.setattr(config, "_settings_instance", None)
    assert verify_submission_token(sid, token) is False
