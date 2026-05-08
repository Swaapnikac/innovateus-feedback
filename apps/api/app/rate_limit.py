"""Per-IP rate limiting for paid / heavy endpoints.

Anchored on the AI and transcription routes because they call OpenAI on
every request and are the obvious cost / DoS amplification surface. The
caps are generous for a real learner taking the survey (one question at a
time, a few seconds between actions) but tight enough that a script
hammering the endpoint hits a 429 within seconds.

We use ``slowapi``'s in-memory backend, which is fine for a single Render
instance. If we ever scale horizontally, swap the storage to Redis via
``Limiter(storage_uri="redis://...")``.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address


# Caps the limiter applies. Adjust here in one place if traffic patterns
# change — every router pulls the values through this module.
TRANSCRIBE_LIMIT = "30/minute"
AI_HEAVY_LIMIT = "30/minute"
AI_NORMAL_LIMIT = "60/minute"
# /v1/events is unauthenticated for cohort-only beacons (no submission_id)
# so it's the easiest endpoint to spam. Real surveys produce maybe 30-60
# events per minute per learner; 240/min leaves comfortable headroom for
# bursts (page_view rapid-fire, mode_switched scrolling) while shutting
# down anyone trying to fill the events table.
EVENTS_LIMIT = "240/minute"
EVENTS_DROPOUT_LIMIT = "30/minute"


def _key_func(request):
    """Pick the IP we limit on.

    Behind Render's proxy ``request.client.host`` is the proxy IP and
    ``X-Forwarded-For`` carries the real client. We prefer the leftmost
    XFF entry (original client) and fall back to slowapi's default.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return get_remote_address(request)


limiter = Limiter(key_func=_key_func, default_limits=[])
