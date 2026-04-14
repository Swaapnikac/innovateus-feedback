from fastapi import APIRouter
from app.schemas import (
    VaguenessRequest, VaguenessResponse,
    FollowUpRequest, FollowUpResponse,
    VaguenessWithFollowupsResponse,
    CleanupRequest, CleanupResponse,
)
from app.services.ai_service import detect_vagueness, generate_followups, cleanup_transcript, detect_vagueness_with_followups

router = APIRouter()


@router.post("/ai/vagueness", response_model=VaguenessResponse)
async def check_vagueness(req: VaguenessRequest):
    result = await detect_vagueness(req.question_text, req.answer_text)
    return VaguenessResponse(**result)


@router.post("/ai/followups", response_model=FollowUpResponse)
async def get_followups(req: FollowUpRequest):
    followups = await generate_followups(
        req.question_text, req.answer_text, req.missing_info_types
    )
    return FollowUpResponse(followups=followups)


@router.post("/ai/check", response_model=VaguenessWithFollowupsResponse)
async def check_vagueness_with_followups(req: VaguenessRequest):
    """Single LLM call: vagueness classification + follow-up generation together.
    ~1.5s vs ~3s for two sequential calls."""
    result = await detect_vagueness_with_followups(req.question_text, req.answer_text)
    return VaguenessWithFollowupsResponse(**result)


@router.post("/ai/cleanup", response_model=CleanupResponse)
async def cleanup(req: CleanupRequest):
    result = await cleanup_transcript(req.raw_text)
    return CleanupResponse(**result)
