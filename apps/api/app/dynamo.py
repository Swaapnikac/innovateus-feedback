"""DynamoDB client module — replaces SQLAlchemy db.py.

Provides table accessors for the two DynamoDB tables:
  - Surveys table:      cohort metadata + survey config versions
  - Submissions table:  submissions with embedded answers + extraction

Tables are initialized once (Lambda connection reuse) and shared across requests.
"""
import json
from decimal import Decimal
import boto3
from app.config import get_settings


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles DynamoDB Decimal types."""
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def decimals_to_native(obj):
    """Recursively convert Decimal values from DynamoDB to int/float."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    if isinstance(obj, dict):
        return {k: decimals_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimals_to_native(i) for i in obj]
    return obj


_dynamodb_resource = None
_surveys_table = None
_submissions_table = None
_events_table = None


def _get_dynamodb():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        settings = get_settings()
        kwargs = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint_url:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
        _dynamodb_resource = boto3.resource("dynamodb", **kwargs)
    return _dynamodb_resource


def get_surveys_table():
    global _surveys_table
    if _surveys_table is None:
        settings = get_settings()
        _surveys_table = _get_dynamodb().Table(settings.surveys_table_name)
    return _surveys_table


def get_submissions_table():
    global _submissions_table
    if _submissions_table is None:
        settings = get_settings()
        _submissions_table = _get_dynamodb().Table(settings.submissions_table_name)
    return _submissions_table


def get_events_table():
    global _events_table
    if _events_table is None:
        settings = get_settings()
        _events_table = _get_dynamodb().Table(settings.events_table_name)
    return _events_table


def query_all_items(table, **kwargs):
    """Query with automatic pagination. Returns all matching items."""
    items = []
    response = table.query(**kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.query(**kwargs, ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    return items


def scan_all_items(table, **kwargs):
    """Scan with automatic pagination. Returns all matching items."""
    items = []
    response = table.scan(**kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.scan(**kwargs, ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    return items
