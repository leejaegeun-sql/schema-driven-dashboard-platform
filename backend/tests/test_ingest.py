"""POST /ingest: validation rules and atomicity."""

from __future__ import annotations

import pytest
from conftest import TRADE_ROWS, TRADE_SCHEMA, error_of


def ingest(client, rows, schema="trade"):
    return client.post("/ingest", json={"schema": schema, "rows": rows})


def stored_rows(client) -> int:
    """Row count as seen through a dashboard -- the store has no read endpoint."""
    client.post(
        "/dashboard",
        json={
            "name": "probe",
            "schema": "trade",
            "views": [{"type": "summary", "aggregation": "count"}],
        },
    )
    return client.get("/dashboard/probe").json()["views"][0]["value"]


def test_valid_rows_are_accepted(trade_client):
    response = ingest(trade_client, TRADE_ROWS)

    assert response.status_code == 201
    assert response.json() == {"schema": "trade", "ingested": 3, "totalRows": 3}


def test_repeated_ingestion_appends(trade_client):
    ingest(trade_client, TRADE_ROWS)
    response = ingest(trade_client, [{"tradeId": "T004", "amount": 10}])

    assert response.json() == {"schema": "trade", "ingested": 1, "totalRows": 4}


def test_optional_fields_may_be_omitted(trade_client):
    assert ingest(trade_client, [{"tradeId": "T1", "amount": 1}]).status_code == 201


def test_unknown_schema_is_not_found(client):
    response = ingest(client, [{"tradeId": "T1", "amount": 1}])

    assert response.status_code == 404
    assert error_of(response)["code"] == "SCHEMA_NOT_FOUND"


def test_schema_lookup_is_case_sensitive(trade_client):
    response = ingest(trade_client, [{"tradeId": "T1", "amount": 1}], schema="Trade")

    assert response.status_code == 404


def test_empty_batch_is_rejected(trade_client):
    response = ingest(trade_client, [])

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "EMPTY_BATCH"


def test_missing_required_field_is_rejected(trade_client):
    response = ingest(trade_client, [{"amount": 1000}])

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"] == [
        {"row": 0, "issue": "required field is missing", "field": "tradeId"}
    ]


@pytest.mark.parametrize("field", ["tradeId", "status"])
def test_explicit_null_is_never_accepted(trade_client, field):
    """Required or optional, an explicit null is a client error: omit the key."""
    row = {"tradeId": "T1", "amount": 1}
    row[field] = None

    response = ingest(trade_client, [row])

    assert response.status_code == 422
    error = error_of(response)
    assert error["details"][0]["field"] == field
    assert "null is not an accepted value" in error["details"][0]["issue"]


@pytest.mark.parametrize(
    ("row", "field", "expected"),
    [
        ({"tradeId": "T1", "amount": "1000"}, "amount", "expected number, got string"),
        ({"tradeId": "T1", "amount": True}, "amount", "expected number, got boolean"),
        ({"tradeId": 1, "amount": 1000}, "tradeId", "expected string, got number"),
        ({"tradeId": "T1", "amount": 1, "settled": "yes"}, "settled", "expected boolean, got string"),
        ({"tradeId": "T1", "amount": {"v": 1}}, "amount", "expected number, got object"),
        ({"tradeId": "T1", "amount": [1]}, "amount", "expected number, got array"),
    ],
)
def test_type_mismatches_are_rejected(trade_client, row, field, expected):
    response = ingest(trade_client, [row])

    assert response.status_code == 422
    detail = error_of(response)["details"][0]
    assert detail["field"] == field
    assert detail["issue"] == expected


@pytest.mark.parametrize("amount", [1000, 1000.5, -3, 0])
def test_integers_and_floats_are_both_numbers(trade_client, amount):
    assert ingest(trade_client, [{"tradeId": "T1", "amount": amount}]).status_code == 201


@pytest.mark.parametrize("settled", [True, False])
def test_booleans_are_accepted_for_boolean_fields(trade_client, settled):
    response = ingest(trade_client, [{"tradeId": "T1", "amount": 1, "settled": settled}])

    assert response.status_code == 201


def test_unknown_fields_are_rejected(trade_client):
    response = ingest(trade_client, [{"tradeId": "T1", "amount": 1, "trader": "alice"}])

    assert response.status_code == 422
    detail = error_of(response)["details"][0]
    assert detail["field"] == "trader"
    assert "unknown field" in detail["issue"]


@pytest.mark.parametrize("row", ["not-an-object", 42, None, ["a"]])
def test_rows_must_be_objects(trade_client, row):
    response = ingest(trade_client, [row])

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert "expected an object" in error["details"][0]["issue"]


def test_every_problem_in_the_batch_is_reported(trade_client):
    response = ingest(
        trade_client,
        [
            {"tradeId": "T1", "amount": 1},                    # valid
            {"amount": "big", "trader": "alice"},              # three problems
            {"tradeId": "T3"},                                 # missing amount
        ],
    )

    assert response.status_code == 422
    error = error_of(response)
    assert error["message"] == "2 of 3 row(s) failed validation; no rows were ingested"
    assert error["details"] == [
        {"row": 1, "issue": "unknown field is not part of schema 'trade'", "field": "trader"},
        {"row": 1, "issue": "required field is missing", "field": "tradeId"},
        {"row": 1, "issue": "expected number, got string", "field": "amount"},
        {"row": 2, "issue": "required field is missing", "field": "amount"},
    ]


def test_a_failed_batch_stores_nothing(trade_client):
    response = ingest(trade_client, [{"tradeId": "T1", "amount": 1}, {"tradeId": "T2"}])

    assert response.status_code == 422
    assert stored_rows(trade_client) == 0


def test_a_failed_batch_leaves_earlier_rows_untouched(trade_client):
    ingest(trade_client, TRADE_ROWS)

    assert ingest(trade_client, [{"tradeId": "T4", "amount": "oops"}]).status_code == 422
    assert stored_rows(trade_client) == 3


def test_rows_of_one_schema_do_not_leak_into_another(client):
    client.post("/schema", json=TRADE_SCHEMA)
    client.post(
        "/schema",
        json={"name": "customer", "fields": [{"name": "customerId", "type": "string", "required": True}]},
    )
    ingest(client, TRADE_ROWS)

    response = client.post("/ingest", json={"schema": "customer", "rows": [{"customerId": "C1"}]})

    assert response.json() == {"schema": "customer", "ingested": 1, "totalRows": 1}


def test_a_large_batch_is_handled(trade_client):
    rows = [{"tradeId": f"T{i}", "amount": i} for i in range(1000)]

    response = ingest(trade_client, rows)

    assert response.json()["totalRows"] == 1000


@pytest.mark.parametrize(
    "body",
    [
        {"rows": [{"tradeId": "T1", "amount": 1}]},          # no schema
        {"schema": "trade"},                                  # no rows
        {"schema": "trade", "rows": "nope"},                  # rows not a list
        {"schema": "trade", "rows": [], "mode": "partial"},   # unknown key
    ],
)
def test_structurally_invalid_bodies_are_rejected(trade_client, body):
    response = trade_client.post("/ingest", json=body)

    assert response.status_code == 422
    assert error_of(response)["code"] == "REQUEST_VALIDATION_ERROR"
