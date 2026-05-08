"""Tiny helpers for keeping log lines safe to share / persist.

The goal is twofold:

1. Cap the length of any string we put into a log line. Exception messages
   from third-party SDKs (OpenAI, Qualtrics, httpx) can be very long and
   occasionally include the request body that caused the failure — which
   in our case can include user-supplied content.

2. Truncate long correlation IDs (submission UUIDs) when full IDs are not
   needed for the line in question. The full UUID is fine in structured
   logs, but ad-hoc messages don't need it.

Use ``safe_err(e)`` around any ``str(e)`` that ends up in ``logger.warning``
or ``logger.error``. Use ``short_id(uid)`` for ad-hoc human-facing log
lines that just need a recognisable prefix.
"""

from __future__ import annotations

from typing import Any
import uuid


# Hard cap on any error string we send to the logger. Big enough to
# preserve useful context, small enough that a multi-page traceback or
# pasted document body cannot dominate a single log line.
_MAX_ERR_CHARS = 300


def safe_err(exc: BaseException | str | None, *, limit: int = _MAX_ERR_CHARS) -> str:
    """Return a length-bounded representation of ``exc`` safe for log lines."""
    if exc is None:
        return ""
    text = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) > limit:
        return text[:limit] + "...(truncated)"
    return text


def short_id(value: Any, *, length: int = 8) -> str:
    """Return the first ``length`` characters of a UUID-ish value."""
    s = str(value or "").replace("-", "")
    return s[:length] if s else "?"
