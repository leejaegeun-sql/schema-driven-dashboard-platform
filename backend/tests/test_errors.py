"""Every failure path answers with the same envelope."""

from __future__ import annotations

import pytest
from conftest import TRADE_SCHEMA, error_of


@pytest.fixture
def failures(trade_client):
    """One response per error path the API can produce."""
    trade_client.post(
        "/dashboard",
        json={"name": "d", "schema": "trade", "views": [{"type": "summary", "aggregation": "count"}]},
    )
    return {
        "schema conflict": trade_client.post("/schema", json=TRADE_SCHEMA),
        "invalid schema": trade_client.post("/schema", json={"name": "x", "fields": []}),
        "unknown schema": trade_client.post("/ingest", json={"schema": "ghost", "rows": [{}]}),
        "empty batch": trade_client.post("/ingest", json={"schema": "trade", "rows": []}),
        "row validation": trade_client.post("/ingest", json={"schema": "trade", "rows": [{}]}),
        "dashboard conflict": trade_client.post(
            "/dashboard",
            json={"name": "d", "schema": "trade", "views": [{"type": "table", "columns": ["tradeId"]}]},
        ),
        "invalid dashboard": trade_client.post(
            "/dashboard",
            json={"name": "e", "schema": "trade", "views": [{"type": "table", "columns": ["ghost"]}]},
        ),
        "unknown dashboard": trade_client.get("/dashboard/ghost"),
        "pydantic": trade_client.post("/schema", json={"name": "x"}),
        "malformed json": trade_client.post(
            "/ingest", content=b"{not json", headers={"content-type": "application/json"}
        ),
        "unknown route": trade_client.get("/nope"),
        "wrong method": trade_client.delete("/schema"),
    }


def test_every_error_uses_the_same_envelope(failures):
    for label, response in failures.items():
        assert response.status_code >= 400, label
        error_of(response)  # asserts the envelope's shape
        assert "detail" not in response.json(), label


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("schema conflict", 409),
        ("invalid schema", 422),
        ("unknown schema", 404),
        ("empty batch", 422),
        ("row validation", 422),
        ("dashboard conflict", 409),
        ("invalid dashboard", 422),
        ("unknown dashboard", 404),
        ("pydantic", 422),
        ("malformed json", 422),
        ("unknown route", 404),
        ("wrong method", 405),
    ],
)
def test_status_codes(failures, label, expected):
    assert failures[label].status_code == expected


@pytest.mark.parametrize(
    ("label", "code"),
    [
        ("schema conflict", "SCHEMA_ALREADY_EXISTS"),
        ("invalid schema", "INVALID_SCHEMA"),
        ("unknown schema", "SCHEMA_NOT_FOUND"),
        ("empty batch", "EMPTY_BATCH"),
        ("row validation", "VALIDATION_ERROR"),
        ("dashboard conflict", "DASHBOARD_ALREADY_EXISTS"),
        ("invalid dashboard", "INVALID_DASHBOARD"),
        ("unknown dashboard", "DASHBOARD_NOT_FOUND"),
        ("pydantic", "REQUEST_VALIDATION_ERROR"),
        ("malformed json", "REQUEST_VALIDATION_ERROR"),
        ("unknown route", "NOT_FOUND"),
        ("wrong method", "METHOD_NOT_ALLOWED"),
    ],
)
def test_error_codes(failures, label, code):
    assert error_of(failures[label])["code"] == code


def test_pydantic_failures_keep_status_422_but_lose_fastapis_default_body(trade_client):
    response = trade_client.post("/schema", json={"name": "trade", "fields": "lots"})

    assert response.status_code == 422
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == "fields"


def test_malformed_json_has_no_misleading_field_location(trade_client):
    response = trade_client.post(
        "/ingest", content=b"{oops", headers={"content-type": "application/json"}
    )

    detail = error_of(response)["details"][0]
    assert "field" not in detail
    assert "JSON" in detail["issue"]


def test_validation_details_locate_the_row_and_the_field(trade_client):
    response = trade_client.post(
        "/ingest", json={"schema": "trade", "rows": [{"tradeId": "T1", "amount": 1}, {}]}
    )

    details = error_of(response)["details"]
    assert {detail["row"] for detail in details} == {1}
    assert {detail["field"] for detail in details} == {"tradeId", "amount"}
