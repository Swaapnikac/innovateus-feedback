from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from app.config import get_settings
from app.routers import survey, submissions, transcribe, ai, admin, editor, jotform

settings = get_settings()

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app = FastAPI(title="InnovateUS Feedback API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(survey.router, prefix="/v1", tags=["survey"])
app.include_router(submissions.router, prefix="/v1", tags=["submissions"])
app.include_router(transcribe.router, prefix="/v1", tags=["transcribe"])
app.include_router(ai.router, prefix="/v1", tags=["ai"])
app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])
app.include_router(editor.router, prefix="/v1/admin", tags=["editor"])
app.include_router(jotform.router, prefix="/v1/admin", tags=["jotform"])


@app.get("/")
def root():
    return {"service": "InnovateUS Feedback API", "version": "2.0.0", "database": "DynamoDB", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


# AWS Lambda handler via Mangum
handler = Mangum(app)
