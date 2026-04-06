"""Create DynamoDB tables for InnovateUS Feedback Platform.

Run this script once to set up the two DynamoDB tables.
Works with both real AWS DynamoDB and DynamoDB Local.

Usage:
    python create_tables.py                    # Uses AWS credentials
    python create_tables.py --local            # Uses DynamoDB Local (localhost:8000)
"""
import sys
import boto3
from app.config import get_settings


def create_tables(endpoint_url: str | None = None):
    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    elif settings.dynamodb_endpoint_url:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url

    dynamodb = boto3.client("dynamodb", **kwargs)

    # ── Table 1: Surveys ─────────────────────────────────────────────
    # Stores cohort metadata and survey config versions.
    # PK: COHORT#<uuid>
    # SK: METADATA | VERSION#v1 | VERSION#v2 | ...
    try:
        dynamodb.create_table(
            TableName=settings.surveys_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created table: {settings.surveys_table_name}")
    except dynamodb.exceptions.ResourceInUseException:
        print(f"Table already exists: {settings.surveys_table_name}")

    # ── Table 2: Submissions ─────────────────────────────────────────
    # Stores submissions with embedded answers and extraction.
    # PK: COHORT#<uuid>
    # SK: SUB#<uuid>
    # GSI: IpHashIndex (ip_hash -> created_at) for duplicate checking
    try:
        dynamodb.create_table(
            TableName=settings.submissions_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "ip_hash", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "IpHashIndex",
                    "KeySchema": [
                        {"AttributeName": "ip_hash", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created table: {settings.submissions_table_name}")
    except dynamodb.exceptions.ResourceInUseException:
        print(f"Table already exists: {settings.submissions_table_name}")

    print("\nDynamoDB tables ready!")
    print(f"  Surveys table:     {settings.surveys_table_name}")
    print(f"  Submissions table: {settings.submissions_table_name}")


if __name__ == "__main__":
    local = "--local" in sys.argv
    endpoint = "http://localhost:8000" if local else None
    if local:
        print("Using DynamoDB Local at http://localhost:8000\n")
    else:
        print("Using AWS DynamoDB\n")
    create_tables(endpoint)
