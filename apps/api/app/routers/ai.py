from fastapi import APIRouter
from app.schemas import (
    VaguenessRequest, VaguenessResponse,
    FollowUpRequest, FollowUpResponse,
    VaguenessWithFollowupsResponse,
    FollowUpCheckRequest,
    CleanupRequest, CleanupResponse,
)
from app.services.ai_service import (
    detect_vagueness,
    generate_followups,
    cleanup_transcript,
    detect_vagueness_with_followups,
    detect_followup_needs_clarification,
)

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


@router.post("/ai/check-followup", response_model=VaguenessWithFollowupsResponse)
async def check_followup_vagueness(req: FollowUpCheckRequest):
    """Decide whether a follow-up answer needs one more clarifying question.

    Differs from ``/ai/check`` in that it receives the original question +
    answer as context, so the model can apply a stricter bar than the initial
    vagueness check (the participant already had one clarification chance).
    """
    result = await detect_followup_needs_clarification(
        req.original_question,
        req.original_answer,
        req.followup_question,
        req.followup_answer,
    )
    return VaguenessWithFollowupsResponse(**result)


@router.post("/ai/cleanup", response_model=CleanupResponse)
async def cleanup(req: CleanupRequest):
    result = await cleanup_transcript(req.raw_text)
    return CleanupResponse(**result)
