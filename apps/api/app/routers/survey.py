import copy
import json
import random
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Cohort

router = APIRouter()

SURVEY_CONFIG_DIR = Path(__file__).resolve().parents[4] / "docs" / "survey-config"


def _load_default_survey() -> dict:
    path = SURVEY_CONFIG_DIR / "survey-en.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _randomize_within_groups(config: dict) -> dict:
    """Shuffle questions within groups that have randomize=True.

    Preserves group presentation order defined by question_groups.
    Questions without a group are appended at the end in their original order.
    Conditional dependencies are respected: if B depends on A, A comes first.
    """
    config = copy.deepcopy(config)
    questions: list[dict] = config.get("questions", [])
    groups_meta: list[dict] = config.get("question_groups", [])

    if not groups_meta:
        return config

    randomize_set = {g["id"] for g in groups_meta if g.get("randomize")}
    group_order = [g["id"] for g in groups_meta]

    buckets: dict[str, list[dict]] = {gid: [] for gid in group_order}
    ungrouped: list[dict] = []

    for q in questions:
        gid = q.get("group")
        if gid and gid in buckets:
            buckets[gid].append(q)
        else:
            ungrouped.append(q)

    for gid in group_order:
        if gid in randomize_set:
            random.shuffle(buckets[gid])
            _fix_conditional_order(buckets[gid])

    result: list[dict] = []
    for gid in group_order:
        result.extend(buckets[gid])
    result.extend(ungrouped)

    config["questions"] = result
    return config


def _fix_conditional_order(questions: list[dict]) -> None:
    """Move any question with a condition so it appears after its dependency."""
    changed = True
    while changed:
        changed = False
        id_to_idx = {q["id"]: i for i, q in enumerate(questions)}
        for i, q in enumerate(questions):
            cond = q.get("condition")
            if not cond:
                continue
            dep_id = cond.get("question_id")
            dep_idx = id_to_idx.get(dep_id)
            if dep_idx is not None and dep_idx > i:
                questions.pop(i)
                questions.insert(dep_idx, q)
                changed = True
                break


@router.get("/survey/{cohort_id}")
async def get_survey(
    cohort_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    cohort = await db.get(Cohort, cohort_id)

    config = cohort.survey_config if cohort else None
    if not config:
        try:
            config = _load_default_survey()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Survey configuration not found")

    config = _randomize_within_groups(config)

    response.headers["Cache-Control"] = "no-store"
    return {"cohort_id": str(cohort_id), "survey": config}
