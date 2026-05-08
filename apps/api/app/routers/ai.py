from fastapi import APIRouter, Request
from app.schemas import (
    VaguenessRequest, VaguenessResponse,
    FollowUpRequest, FollowUpResponse,
    VaguenessWithFollowupsResponse,
    FollowUpCheckRequest,
    CleanupRequest, CleanupResponse,
    PiiCheckRequest, PiiCheckResponse,
)
from app.services.ai_service import (
    detect_vagueness,
    generate_followups,
    cleanup_transcript,
    detect_vagueness_with_followups,
    detect_followup_needs_clarification,
    detect_and_redact_pii_with_ai,
)
from app.rate_limit import limiter, AI_HEAVY_LIMIT, AI_NORMAL_LIMIT

router = APIRouter()


@router.post("/ai/vagueness", response_model=VaguenessResponse)
@limiter.limit(AI_NORMAL_LIMIT)
async def check_vagueness(request: Request, req: VaguenessRequest):
    result = await detect_vagueness(req.question_text, req.answer_text)
    return VaguenessResponse(**result)


@router.post("/ai/followups", response_model=FollowUpResponse)
@limiter.limit(AI_HEAVY_LIMIT)
async def get_followups(request: Request, req: FollowUpRequest):
    followups = await generate_followups(
        req.question_text, req.answer_text, req.missing_info_types
    )
    return FollowUpResponse(followups=followups)


@router.post("/ai/check", response_model=VaguenessWithFollowupsResponse)
@limiter.limit(AI_NORMAL_LIMIT)
async def check_vagueness_with_followups(request: Request, req: VaguenessRequest):
    """Single LLM call: vagueness classification + follow-up generation together.
    ~1.5s vs ~3s for two sequential calls."""
    result = await detect_vagueness_with_followups(req.question_text, req.answer_text)
    return VaguenessWithFollowupsResponse(**result)


@router.post("/ai/check-followup", response_model=VaguenessWithFollowupsResponse)
@limiter.limit(AI_NORMAL_LIMIT)
async def check_followup_vagueness(request: Request, req: FollowUpCheckRequest):
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
@limiter.limit(AI_HEAVY_LIMIT)
async def cleanup(request: Request, req: CleanupRequest):
    result = await cleanup_transcript(req.raw_text)
    return CleanupResponse(**result)


@router.post("/ai/pii-check", response_model=PiiCheckResponse)
@limiter.limit(AI_NORMAL_LIMIT)
async def check_pii(request: Request, req: PiiCheckRequest):
    """Regex + GPT-5-mini PII scan used by the survey Next click.

    Returns metadata only (found / count / categories) — never the redacted
    text — because this endpoint is an advisory signal for the banner, not a
    save path. The authoritative scrub happens in ``/submissions/.../answer``
    via ``detect_and_redact_pii_with_ai`` on save.

    The underlying service memoises by sha256(text) and short-circuits
    AI calls for very short clean inputs, so repeat Next clicks stay cheap.
    """
    _redacted, count, cats = await detect_and_redact_pii_with_ai(req.text or "")
    return PiiCheckResponse(found=bool(count), count=count, categories=cats)
