"""Create the innovateus-events DynamoDB table.

Usage:
    python create_events_table.py              # Uses AWS credentials
    python create_events_table.py --local      # Uses DynamoDB Local
"""
import sys
import boto3
from app.config import get_settings


def create_events_table(endpoint_url: str | None = None):
    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    elif settings.dynamodb_endpoint_url:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url

    dynamodb = boto3.client("dynamodb", **kwargs)

    try:
        dynamodb.create_table(
            TableName=settings.events_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "gsi1_pk", "AttributeType": "S"},
                {"AttributeName": "gsi1_sk", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "CohortEventIndex",
                    "KeySchema": [
                        {"AttributeName": "gsi1_pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1_sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created table: {settings.events_table_name}")
    except dynamodb.exceptions.ResourceInUseException:
        print(f"Table already exists: {settings.events_table_name}")


if __name__ == "__main__":
    local = "--local" in sys.argv
    endpoint = "http://localhost:8000" if local else None
    create_events_table(endpoint)
