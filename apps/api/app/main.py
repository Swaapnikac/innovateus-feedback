from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import survey, submissions, transcribe, ai, admin

settings = get_settings()

app = FastAPI(title="InnovateUS Feedback API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(survey.router, prefix="/v1", tags=["survey"])
app.include_router(submissions.router, prefix="/v1", tags=["submissions"])
app.include_router(transcribe.router, prefix="/v1", tags=["transcribe"])
app.include_router(ai.router, prefix="/v1", tags=["ai"])
app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])


@app.get("/health")
async def health():
    return {"status": "ok"}
