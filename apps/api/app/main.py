from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from app.config import get_settings
from app.rate_limit import limiter
from app.routers import survey, submissions, transcribe, ai, admin, editor, jotform, events

settings = get_settings()

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

# Disable interactive API docs and the OpenAPI schema in production. These
# expose the full endpoint inventory and request/response shapes to anyone
# who hits the URL. They remain available in development and staging.
_is_prod = settings.environment == "production"
app = FastAPI(
    title="InnovateUS Feedback API",
    version="2.0.0",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    # X-Submission-Token is the HMAC the survey client echoes on every
    # mutation under /v1/submissions/{id}/* and on /v1/events when a
    # submission_id is set. Must be in the allow-list or the browser
    # will fail the preflight OPTIONS check in production.
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-Submission-Token",
    ],
)

# Per-IP rate limiting on AI / transcribe endpoints. The limiter is shared
# across the app so we expose the state on app.state and register the
# default 429 handler. Individual routes opt in via @limiter.limit(...).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(survey.router, prefix="/v1", tags=["survey"])
app.include_router(submissions.router, prefix="/v1", tags=["submissions"])
app.include_router(transcribe.router, prefix="/v1", tags=["transcribe"])
app.include_router(ai.router, prefix="/v1", tags=["ai"])
app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])
app.include_router(editor.router, prefix="/v1/admin", tags=["editor"])
app.include_router(jotform.router, prefix="/v1/admin", tags=["jotform"])
app.include_router(events.router, prefix="/v1", tags=["events"])


@app.get("/")
def root():
    info = {"service": "InnovateUS Feedback API", "version": "2.0.0", "database": "PostgreSQL"}
    if not _is_prod:
        info["docs"] = "/docs"
    return info


@app.get("/health")
def health():
    return {"status": "ok"}
