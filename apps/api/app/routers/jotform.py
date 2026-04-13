import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Submission
from app.auth import require_admin
from app.config import get_settings

router = APIRouter()


@router.get("/jotform/status", dependencies=[Depends(require_admin)])
def jotform_status():
    s = get_settings()
    configured = bool(s.jotform_api_key and s.jotform_form_id)
    return {
        "configured": configured,
        "form_id": s.jotform_form_id or None,
        "api_url": s.jotform_api_url or None,
    }


@router.post("/jotform/sync/{submission_id}", dependencies=[Depends(require_admin)])
async def jotform_sync_one(submission_id: uuid.UUID):
    from app.services.jotform_service import sync_submission
    result = await sync_submission(submission_id)
    status_code = "ok" if result["success"] else "error"
    return {"status": status_code, "submission_id": str(submission_id), "error": result.get("error")}


@router.post("/jotform/sync-all", dependencies=[Depends(require_admin)])
async def jotform_sync_all(
    cohort_id: Optional[uuid.UUID] = None,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    from app.services.jotform_service import sync_submission

    q = select(Submission).where(Submission.status == "completed")
    if cohort_id:
        q = q.where(Submission.cohort_id == cohort_id)
    result = await db.execute(q)
    subs = result.scalars().all()

    if not force:
        subs = [s for s in subs if not s.jotform_synced_at]

    total = len(subs)
    synced = 0
    failed = 0
    errors: list[dict] = []

    for sub in subs:
        sync_result = await sync_submission(sub.id)
        if sync_result["success"]:
            synced += 1
        else:
            failed += 1
            errors.append({"submission_id": str(sub.id), "error": sync_result.get("error")})

    return {"total": total, "synced": synced, "failed": failed, "errors": errors}
