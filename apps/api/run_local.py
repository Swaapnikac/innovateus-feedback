"""Run InnovateUS API locally with in-process DynamoDB mock.

Usage: python run_local.py
"""
import os
import sys
import time

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["DYNAMODB_ENDPOINT_URL"] = ""

from moto import mock_aws
import boto3

# Start mock globally — stays active for entire process
_mock = mock_aws()
_mock.start()

# Create tables
_client = boto3.client("dynamodb", region_name="us-east-1")

_client.create_table(
    TableName="innovateus-surveys",
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

_client.create_table(
    TableName="innovateus-submissions",
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
    GlobalSecondaryIndexes=[{
        "IndexName": "IpHashIndex",
        "KeySchema": [
            {"AttributeName": "ip_hash", "KeyType": "HASH"},
            {"AttributeName": "created_at", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }],
    BillingMode="PAY_PER_REQUEST",
)

_client.create_table(
    TableName="innovateus-events",
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
    GlobalSecondaryIndexes=[{
        "IndexName": "CohortEventIndex",
        "KeySchema": [
            {"AttributeName": "gsi1_pk", "KeyType": "HASH"},
            {"AttributeName": "gsi1_sk", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }],
    BillingMode="PAY_PER_REQUEST",
)

# Seed
from seed import seed
seed()

print("\n" + "=" * 50)
print("InnovateUS Feedback API (Local Dev)")
print("=" * 50)
print("  API:     http://localhost:8000")
print("  Docs:    http://localhost:8000/docs")
print("  DB:      DynamoDB (in-memory mock)")
print("  Note:    Data resets on restart")
print("  Press Ctrl+C to stop")
print("=" * 50 + "\n")

# Run uvicorn directly (no reload — reload forks a new process that loses the mock)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
