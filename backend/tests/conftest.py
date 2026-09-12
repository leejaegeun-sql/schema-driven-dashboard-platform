"""Shared fixtures and sample use cases.

Two unrelated use cases -- trade and customer -- are defined here on purpose:
several tests assert that the same backend serves both with no special casing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app  # noqa: E402

TRADE_SCHEMA: dict[str, Any] = {
    "name": "trade",
    "fields": [
        {"name": "tradeId", "type": "string", "required": True},
        {"name": "amount", "type": "number", "required": True, "aggregation": "sum"},
        {"name": "status", "type": "string"},
        {"name": "settled", "type": "boolean"},
    ],
}

CUSTOMER_SCHEMA: dict[str, Any] = {
    "name": "customer",
    "fields": [
        {"name": "customerId", "type": "string", "required": True},
        {"name": "name", "type": "string", "required": True},
        {"name": "country", "type": "string"},
        {"name": "score", "type": "number"},
    ],
}

# status is absent from the third row and settled from the second: optional
# fields are genuinely optional, which several aggregation tests depend on.
TRADE_ROWS: list[dict[str, Any]] = [
    {"tradeId": "T001", "amount": 1000, "status": "OPEN", "settled": False},
    {"tradeId": "T002", "amount": 1500, "status": "CLOSED"},
    {"tradeId": "T003", "amount": 2500.5, "settled": True},
]

TRADE_DASHBOARD: dict[str, Any] = {
    "name": "trade-dashboard",
    "schema": "trade",
    "views": [
        {"type": "summary", "field": "amount", "aggregation": "sum"},
        {"type": "table", "columns": ["tradeId", "amount", "status"]},
    ],
}


@pytest.fixture
def client() -> TestClient:
    """A client backed by a fresh application, and therefore a fresh store."""
    return TestClient(create_app())


@pytest.fixture
def trade_client(client: TestClient) -> TestClient:
    """Client with the trade schema registered and nothing ingested."""
    assert client.post("/schema", json=TRADE_SCHEMA).status_code == 201
    return client


@pytest.fixture
def loaded_client(trade_client: TestClient) -> TestClient:
    """Client with the trade schema, three rows and a dashboard."""
    assert (
        trade_client.post("/ingest", json={"schema": "trade", "rows": TRADE_ROWS}).status_code
        == 201
    )
    assert trade_client.post("/dashboard", json=TRADE_DASHBOARD).status_code == 201
    return trade_client


def error_of(response) -> dict[str, Any]:
    """The error envelope of a failed response, asserting its shape."""
    body = response.json()
    assert set(body) == {"error"}, body
    error = body["error"]
    assert set(error) == {"code", "message", "details"}, error
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], list)
    for detail in error["details"]:
        assert isinstance(detail, dict)
        assert "issue" in detail
    return error
