"""Per-submission HMAC tokens — mitigates IDOR on submission mutations.

The submission ID is a UUID and effectively unguessable, but it can leak
through logs, the browser address bar, exception traces, third-party
analytics, etc. Anyone who learns one could PATCH the submission, append
answers, or mark it complete.

To close that gap we mint an HMAC over ``submission_id`` at
``/v1/submissions/start`` time and require the same token on every
subsequent mutation. The token is sent as the ``X-Submission-Token``
header. The server is the only party that holds the signing secret, so
a leaked submission ID alone is not enough to mutate the row.

Notes:

- We use a dedicated secret (``submission_token_secret``) that defaults
  to ``jwt_secret`` for backward-compat. Operators can rotate the
  submission secret independently of admin auth tokens.
- ``hmac.compare_digest`` is used for constant-time comparison.
- Tokens are unbounded in lifetime by design — the survey takes a couple
  of minutes and we already enforce a TTL on the submission row itself.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Optional

from fastapi import HTTPException, Request

from app.config import get_settings


_SCHEME = b"submission-v1"


def _signing_key() -> bytes:
    settings = get_settings()
    secret = (
        getattr(settings, "submission_token_secret", "")
        or settings.jwt_secret
    )
    return secret.encode("utf-8")


def mint_submission_token(submission_id: uuid.UUID | str) -> str:
    """Return an HMAC-SHA256 token for ``submission_id``.

    Format is ``"v1.<hex>"`` so we can roll the scheme later without
    breaking existing clients still in flight.
    """
    sid = str(submission_id).encode("utf-8")
    digest = hmac.new(
        _signing_key(),
        _SCHEME + b":" + sid,
        hashlib.sha256,
    ).hexdigest()
    return f"v1.{digest}"


def verify_submission_token(
    submission_id: uuid.UUID | str,
    token: Optional[str],
) -> bool:
    """Constant-time check that ``token`` is a valid mint for ``submission_id``."""
    if not token or not token.startswith("v1."):
        return False
    expected = mint_submission_token(submission_id)
    return hmac.compare_digest(expected, token)


def require_submission_token(request: Request, submission_id: uuid.UUID | str) -> None:
    """FastAPI helper — raise 401 if the header is missing/invalid.

    Header name is ``X-Submission-Token``. We deliberately don't reuse
    ``Authorization`` so admin/editor JWT cookies on the same domain
    can't accidentally satisfy this check.
    """
    token = request.headers.get("x-submission-token")
    if not verify_submission_token(submission_id, token):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing submission token",
        )
