import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from boto3.dynamodb.conditions import Key, Attr
from app.dynamo import get_surveys_table, get_submissions_table, query_all_items, scan_all_items, decimals_to_native
from app.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    MetricsResponse,
    PaginatedResponses,
    SubmissionSummary,
    CohortResponse,
    CohortSettingsRequest,
    CreateCohortRequest,
)
from app.auth import verify_password, create_access_token, require_admin
from app.config import get_settings
from app.services.export_service import (
    generate_raw_csv,
    generate_structured_csv,
    generate_summary_pdf,
    generate_summary_pptx,
)

router = APIRouter()

DEFAULT_SURVEY_PATH = Path(__file__).resolve().parents[4] / "docs" / "survey-config" / "survey-en.json"


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(req: AdminLoginRequest, response: Response):
    settings = get_settings()
    if not settings.admin_password_hash:
        raise HTTPException(status_code=500, detail="Admin password not configured")

    if not verify_password(req.password, settings.admin_password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_access_token({"sub": "admin", "role": "manager"})
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=settings.environment != "development",
        samesite="none" if settings.environment != "development" else "lax",
        max_age=86400,
    )
    return AdminLoginResponse(token=token)


@router.get("/cohorts", dependencies=[Depends(require_admin)])
def list_cohorts():
    table = get_surveys_table()
    # Scan for all METADATA items
    results = scan_all_items(
        table,
        FilterExpression=Attr("sk").eq("METADATA"),
    )
    cohorts = sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)
    return [
        CohortResponse(
            id=uuid.UUID(c["cohort_id"]),
            name=c["name"],
            course_name=c["course_name"],
            max_submissions_per_ip=int(c.get("max_submissions_per_ip", 1)),
            created_at=datetime.fromisoformat(c["created_at"]),
        )
        for c in cohorts
    ]


@router.post("/cohorts", response_model=CohortResponse, dependencies=[Depends(require_admin)])
def create_cohort(req: CreateCohortRequest):
    table = get_surveys_table()
    cohort_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    default_config = None
    if DEFAULT_SURVEY_PATH.exists():
        default_config = json.loads(DEFAULT_SURVEY_PATH.read_text(encoding="utf-8"))

    # Create cohort metadata
    table.put_item(Item={
        "pk": f"COHORT#{cohort_id}",
        "sk": "METADATA",
        "cohort_id": cohort_id,
        "name": req.name,
        "course_name": req.course_name,
        "survey_config": default_config,
        "active_version": "v1",
        "max_submissions_per_ip": 1,
        "created_at": now,
    })

    # Create initial version
    if default_config:
        table.put_item(Item={
            "pk": f"COHORT#{cohort_id}",
            "sk": "VERSION#v1",
            "cohort_id": cohort_id,
            "version_label": "v1",
            "config": default_config,
            "change_summary": "Initial survey configuration",
            "created_by": "admin",
            "created_at": now,
        })

    return CohortResponse(
        id=uuid.UUID(cohort_id),
        name=req.name,
        course_name=req.course_name,
        max_submissions_per_ip=1,
        created_at=datetime.fromisoformat(now),
    )


def _get_submissions_for_filters(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
) -> list[dict]:
    """Fetch submissions matching the given filters."""
    subs_table = get_submissions_table()

    if cohort_id:
        # Query by cohort (efficient — uses partition key)
        items = query_all_items(
            subs_table,
            KeyConditionExpression=Key("pk").eq(f"COHORT#{cohort_id}"),
        )
    else:
        # Scan all submissions
        items = scan_all_items(
            subs_table,
            FilterExpression=Attr("sk").begins_with("SUB#"),
        )

    # Apply filters in Python
    filtered = []
    for item in items:
        if not item.get("sk", "").startswith("SUB#"):
            continue
        # Skip empty in-progress submissions (no answers and not completed)
        if item.get("status") == "started" and not item.get("answers"):
            continue
        if start and item.get("created_at", "") < start.isoformat():
            continue
        if end and item.get("created_at", "") > end.isoformat():
            continue
        if survey_version and item.get("survey_version") != survey_version:
            continue
        filtered.append(decimals_to_native(item))

    return filtered


@router.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(require_admin)])
def get_metrics(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
):
    submissions = _get_submissions_for_filters(cohort_id, start, end, survey_version)

    total = len(submissions)
    completed = [s for s in submissions if s.get("status") == "completed"]
    completion_rate = len(completed) / total if total > 0 else 0

    times = [int(s["time_to_complete_sec"]) for s in completed if s.get("time_to_complete_sec")]
    avg_time = sum(times) / len(times) if times else None

    # Recommendation scores
    scores = []
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_id") == "q1_recommend":
                try:
                    scores.append(int(a["answer_raw"]))
                except (ValueError, TypeError, KeyError):
                    pass
    avg_score = sum(scores) / len(scores) if scores else None

    # Confidence distribution
    conf_dist: dict[str, int] = {}
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_id") == "q2_confidence":
                val = a.get("answer_raw") or "Unknown"
                conf_dist[val] = conf_dist.get(val, 0) + 1

    # Vagueness rate
    open_answers = []
    for sub in submissions:
        for a in sub.get("answers", []):
            if a.get("question_type") == "open":
                open_answers.append(a)
    vague_count = sum(1 for a in open_answers if a.get("is_vague") is True)
    vagueness_rate = vague_count / len(open_answers) if open_answers else None

    return MetricsResponse(
        total_submissions=total,
        completed_submissions=len(completed),
        completion_rate=round(completion_rate, 3),
        avg_time_to_complete_sec=round(avg_time, 1) if avg_time else None,
        avg_recommend_score=round(avg_score, 2) if avg_score else None,
        confidence_distribution=conf_dist,
        vagueness_rate=round(vagueness_rate, 3) if vagueness_rate is not None else None,
    )


@router.get("/responses", response_model=PaginatedResponses, dependencies=[Depends(require_admin)])
def get_responses(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    survey_version: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    submissions = _get_submissions_for_filters(cohort_id, start, end, survey_version)
    submissions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    total = len(submissions)
    start_idx = (page - 1) * page_size
    page_items = submissions[start_idx:start_idx + page_size]

    items = []
    for sub in page_items:
        native_answers = decimals_to_native(sub.get("answers", []))
        answers_list = [
            {
                "question_id": a.get("question_id"),
                "question_type": a.get("question_type"),
                "answer_raw": a.get("answer_raw"),
                "input_mode": a.get("input_mode"),
                "is_vague": a.get("is_vague"),
                "followup_1": a.get("followup_1"),
                "followup_1_answer": a.get("followup_1_answer"),
                "followup_2": a.get("followup_2"),
                "followup_2_answer": a.get("followup_2_answer"),
            }
            for a in native_answers
        ]

        extraction = decimals_to_native(sub.get("extraction"))
        extraction_dict = None
        if extraction:
            extraction_dict = {
                "what_was_tried": extraction.get("what_was_tried"),
                "planned_task_or_workflow": extraction.get("planned_task_or_workflow"),
                "outcome_or_expected_outcome": extraction.get("outcome_or_expected_outcome"),
                "barriers": extraction.get("barriers"),
                "enablers": extraction.get("enablers"),
                "public_benefit": extraction.get("public_benefit"),
                "top_themes": extraction.get("top_themes"),
                "success_story_candidate": extraction.get("success_story_candidate"),
            }

        items.append(
            SubmissionSummary(
                id=uuid.UUID(sub["submission_id"]),
                cohort_id=uuid.UUID(sub["cohort_id"]),
                created_at=datetime.fromisoformat(sub["created_at"]),
                completed_at=datetime.fromisoformat(sub["completed_at"]) if sub.get("completed_at") else None,
                status=sub["status"],
                time_to_complete_sec=int(sub["time_to_complete_sec"]) if sub.get("time_to_complete_sec") else None,
                survey_version=sub.get("survey_version"),
                ip_hash=sub.get("ip_hash"),
                answers=answers_list,
                extraction=extraction_dict,
            )
        )

    return PaginatedResponses(items=items, total=total, page=page, page_size=page_size)


@router.get("/export/raw.csv", dependencies=[Depends(require_admin)])
def export_raw_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
):
    submissions = _get_submissions_for_filters(cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    completed.sort(key=lambda x: x.get("created_at", ""))
    csv_data = generate_raw_csv(completed, cohort_id)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=raw_export.csv"},
    )


@router.get("/export/structured.csv", dependencies=[Depends(require_admin)])
def export_structured_csv(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
):
    submissions = _get_submissions_for_filters(cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    completed.sort(key=lambda x: x.get("created_at", ""))
    csv_data = generate_structured_csv(completed, cohort_id)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=structured_export.csv"},
    )


@router.get("/export/summary.pdf", dependencies=[Depends(require_admin)])
def export_summary_pdf(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
):
    submissions = _get_submissions_for_filters(cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    pdf_bytes = generate_summary_pdf(completed, cohort_id)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=summary_report.pdf"},
    )


@router.get("/export/summary.pptx", dependencies=[Depends(require_admin)])
def export_summary_pptx(
    cohort_id: Optional[uuid.UUID] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
):
    submissions = _get_submissions_for_filters(cohort_id, start, end)
    completed = [s for s in submissions if s.get("status") == "completed"]
    pptx_bytes = generate_summary_pptx(completed, cohort_id)
    return StreamingResponse(
        iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": "attachment; filename=summary_report.pptx"},
    )


@router.delete("/responses", dependencies=[Depends(require_admin)])
def delete_all_responses(cohort_id: Optional[uuid.UUID] = None):
    subs_table = get_submissions_table()

    if cohort_id:
        items = query_all_items(
            subs_table,
            KeyConditionExpression=Key("pk").eq(f"COHORT#{cohort_id}"),
        )
    else:
        items = scan_all_items(
            subs_table,
            FilterExpression=Attr("sk").begins_with("SUB#"),
        )

    if not items:
        return {"status": "ok", "deleted": 0}

    # Batch delete
    with subs_table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})

    return {"status": "ok", "deleted": len(items)}


@router.post("/cohorts/{cohort_id}/settings", dependencies=[Depends(require_admin)])
def update_cohort_settings(cohort_id: uuid.UUID, req: CohortSettingsRequest):
    table = get_surveys_table()
    result = table.get_item(Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"})
    if not result.get("Item"):
        raise HTTPException(status_code=404, detail="Cohort not found")

    table.update_item(
        Key={"pk": f"COHORT#{cohort_id}", "sk": "METADATA"},
        UpdateExpression="SET max_submissions_per_ip = :val",
        ExpressionAttributeValues={":val": req.max_submissions_per_ip},
    )
    return {"status": "updated", "max_submissions_per_ip": req.max_submissions_per_ip}


@router.get("/qualtrics/status", dependencies=[Depends(require_admin)])
def qualtrics_status():
    s = get_settings()
    configured = bool(s.qualtrics_api_token and s.qualtrics_survey_id and s.qualtrics_datacenter_id)
    return {
        "configured": configured,
        "survey_id": s.qualtrics_survey_id or None,
        "datacenter_id": s.qualtrics_datacenter_id or None,
    }


@router.post("/qualtrics/sync/{submission_id}", dependencies=[Depends(require_admin)])
async def qualtrics_sync_one(submission_id: uuid.UUID):
    from app.services.qualtrics_service import sync_submission
    result = await sync_submission(submission_id, force=True)
    status_code = "ok" if result["success"] else "error"
    return {"status": status_code, "submission_id": str(submission_id), "error": result.get("error")}


@router.post("/qualtrics/sync-all", dependencies=[Depends(require_admin)])
async def qualtrics_sync_all(
    cohort_id: Optional[uuid.UUID] = None,
    force: bool = Query(False),
):
    from app.services.qualtrics_service import sync_submission

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
        submissions = [s for s in submissions if not s.get("qualtrics_synced_at")]

    total = len(submissions)
    synced = 0
    failed = 0
    errors: list[dict] = []

    for sub in submissions:
        sub_id = uuid.UUID(sub["submission_id"])
        sync_result = await sync_submission(sub_id, force=True)
        if sync_result["success"]:
            synced += 1
        else:
            failed += 1
            errors.append({"submission_id": str(sub_id), "error": sync_result.get("error")})

    return {"total": total, "synced": synced, "failed": failed, "errors": errors}
