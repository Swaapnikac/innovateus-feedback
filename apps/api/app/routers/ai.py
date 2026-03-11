from fastapi import APIRouter
from app.schemas import VaguenessRequest, VaguenessResponse, FollowUpRequest, FollowUpResponse
from app.services.ai_service import detect_vagueness, generate_followups

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
