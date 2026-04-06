import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from boto3.dynamodb.conditions import Key, Attr
from app.dynamo import get_submissions_table, query_all_items, scan_all_items
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
):
    from app.services.jotform_service import sync_submission

    subs_table = get_submissions_table()
    if cohort_id:
        items = query_all_items(
            subs_table,
            KeyConditionExpression=Key("pk").eq(f"COHORT#{cohort_id}"),
        )
    else:
        items = scan_all_items(subs_table, FilterExpression=Attr("sk").begins_with("SUB#"))

    submissions = [s for s in items if s.get("status") == "completed"]
    if not force:
        submissions = [s for s in submissions if not s.get("jotform_synced_at")]

    total = len(submissions)
    synced = 0
    failed = 0
    errors: list[dict] = []

    for sub in submissions:
        sub_id = uuid.UUID(sub["submission_id"])
        sync_result = await sync_submission(sub_id)
        if sync_result["success"]:
            synced += 1
        else:
            failed += 1
            errors.append({"submission_id": str(sub_id), "error": sync_result.get("error")})

    return {"total": total, "synced": synced, "failed": failed, "errors": errors}
