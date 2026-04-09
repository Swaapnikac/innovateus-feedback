"""Seed script to create a default cohort in DynamoDB for development."""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import boto3
from app.config import get_settings

DEFAULT_COHORT_ID = "00000000-0000-0000-0000-000000000001"
SURVEY_CONFIG_PATH = Path(__file__).resolve().parents[2] / "docs" / "survey-config" / "survey-en.json"


def _load_default_survey() -> dict:
    with open(SURVEY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def seed(endpoint_url: str | None = None):
    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    elif settings.dynamodb_endpoint_url:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url

    dynamodb = boto3.resource("dynamodb", **kwargs)
    table = dynamodb.Table(settings.surveys_table_name)

    # Check if cohort already exists
    result = table.get_item(Key={"pk": f"COHORT#{DEFAULT_COHORT_ID}", "sk": "METADATA"})
    existing = result.get("Item")

    default_survey = _load_default_survey()
    now = datetime.now(timezone.utc).isoformat()

    if not existing:
        # Create cohort metadata
        table.put_item(Item={
            "pk": f"COHORT#{DEFAULT_COHORT_ID}",
            "sk": "METADATA",
            "cohort_id": DEFAULT_COHORT_ID,
            "name": "Pilot Cohort 1",
            "course_name": "Generative AI for Government",
            "survey_config": default_survey,
            "active_version": "v1",
            "max_submissions_per_ip": 1,
            "created_at": now,
        })

        # Create initial version
        table.put_item(Item={
            "pk": f"COHORT#{DEFAULT_COHORT_ID}",
            "sk": "VERSION#v1",
            "cohort_id": DEFAULT_COHORT_ID,
            "version_label": "v1",
            "config": default_survey,
            "change_summary": "Initial survey configuration",
            "created_by": "seed",
            "created_at": now,
        })

        print(f"Seeded cohort: Pilot Cohort 1 ({DEFAULT_COHORT_ID})")
    else:
        # Always refresh survey_config to latest default
        table.update_item(
            Key={"pk": f"COHORT#{DEFAULT_COHORT_ID}", "sk": "METADATA"},
            UpdateExpression="SET survey_config = :config",
            ExpressionAttributeValues={":config": default_survey},
        )
        print(f"Updated survey_config for: {existing.get('name')}")


if __name__ == "__main__":
    local = "--local" in sys.argv
    endpoint = "http://localhost:8000" if local else None
    seed(endpoint)
