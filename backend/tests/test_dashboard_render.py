"""GET /dashboard/{name}: turning configuration + schema + rows into a payload."""

from __future__ import annotations

import pytest
from conftest import CUSTOMER_SCHEMA, TRADE_ROWS, error_of


def summary(client, field, aggregation, name="s"):
    """Register a one-view dashboard and return the rendered view."""
    view = {"type": "summary", "aggregation": aggregation}
    if field is not None:
        view["field"] = field
    assert client.post("/dashboard", json={"name": name, "schema": "trade", "views": [view]}).status_code == 201
    return client.get(f"/dashboard/{name}").json()["views"][0]


def test_dashboard_payload_shape(loaded_client):
    body = loaded_client.get("/dashboard/trade-dashboard").json()

    assert body["name"] == "trade-dashboard"
    assert body["schema"] == "trade"
    assert body["rowCount"] == 3
    assert [view["type"] for view in body["views"]] == ["summary", "table"]


def test_summary_sums_a_numeric_field(loaded_client):
    view = loaded_client.get("/dashboard/trade-dashboard").json()["views"][0]

    assert view == {
        "type": "summary",
        "field": "amount",
        "fieldType": "number",
        "aggregation": "sum",
        "value": 5000.5,
    }


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [("sum", 5000.5), ("min", 1000), ("max", 2500.5), ("count", 3)],
)
def test_aggregations_over_a_required_field(loaded_client, aggregation, expected):
    assert summary(loaded_client, "amount", aggregation)["value"] == expected


def test_average_is_computed_over_the_present_values(loaded_client):
    assert summary(loaded_client, "amount", "avg")["value"] == pytest.approx(5000.5 / 3)


def test_count_without_a_field_counts_every_row(loaded_client):
    view = summary(loaded_client, None, "count")

    assert view["field"] is None
    assert view["fieldType"] is None
    assert view["value"] == 3


@pytest.mark.parametrize(("field", "expected"), [("status", 2), ("settled", 2), ("tradeId", 3)])
def test_count_with_a_field_counts_rows_where_it_is_present(loaded_client, field, expected):
    assert summary(loaded_client, field, "count")["value"] == expected


def test_optional_number_field_aggregates_only_present_rows(client):
    client.post("/schema", json=CUSTOMER_SCHEMA)
    client.post(
        "/ingest",
        json={
            "schema": "customer",
            "rows": [
                {"customerId": "C1", "name": "Ada", "score": 10},
                {"customerId": "C2", "name": "Grace"},
                {"customerId": "C3", "name": "Alan", "score": 30},
            ],
        },
    )
    client.post(
        "/dashboard",
        json={
            "name": "customers",
            "schema": "customer",
            "views": [
                {"type": "summary", "field": "score", "aggregation": "avg"},
                {"type": "summary", "field": "score", "aggregation": "count"},
                {"type": "summary", "aggregation": "count"},
            ],
        },
    )

    views = client.get("/dashboard/customers").json()["views"]

    assert views[0]["value"] == 20  # (10 + 30) / 2, not / 3
    assert views[1]["value"] == 2
    assert views[2]["value"] == 3


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [("sum", 0), ("count", 0), ("avg", None), ("min", None), ("max", None)],
)
def test_empty_dataset_renders_successfully(trade_client, aggregation, expected):
    """A registered schema with no rows is not an error."""
    view = summary(trade_client, "amount", aggregation)

    assert view["value"] == expected


def test_empty_dataset_renders_an_empty_table(trade_client):
    trade_client.post(
        "/dashboard",
        json={
            "name": "empty",
            "schema": "trade",
            "views": [{"type": "table", "columns": ["tradeId", "amount"]}],
        },
    )

    body = trade_client.get("/dashboard/empty").json()

    assert body["rowCount"] == 0
    assert body["views"][0]["rows"] == []
    assert body["views"][0]["rowCount"] == 0


def test_a_field_no_row_supplies_behaves_like_an_empty_dataset(client):
    """score is in the schema but absent from every ingested row."""
    client.post("/schema", json=CUSTOMER_SCHEMA)
    client.post(
        "/ingest",
        json={"schema": "customer", "rows": [{"customerId": "C1", "name": "Ada"}]},
    )
    client.post(
        "/dashboard",
        json={
            "name": "scores",
            "schema": "customer",
            "views": [
                {"type": "summary", "field": "score", "aggregation": "sum"},
                {"type": "summary", "field": "score", "aggregation": "avg"},
                {"type": "summary", "field": "score", "aggregation": "min"},
                {"type": "summary", "field": "score", "aggregation": "max"},
                {"type": "summary", "field": "score", "aggregation": "count"},
            ],
        },
    )

    values = [view["value"] for view in client.get("/dashboard/scores").json()["views"]]

    assert values == [0, None, None, None, 0]


def test_table_reports_column_types_from_the_schema(loaded_client):
    view = loaded_client.get("/dashboard/trade-dashboard").json()["views"][1]

    assert view["columns"] == [
        {"name": "tradeId", "type": "string"},
        {"name": "amount", "type": "number"},
        {"name": "status", "type": "string"},
    ]


def test_table_rows_are_rectangular_and_in_ingestion_order(loaded_client):
    view = loaded_client.get("/dashboard/trade-dashboard").json()["views"][1]

    assert view["rows"] == [
        {"tradeId": "T001", "amount": 1000, "status": "OPEN"},
        {"tradeId": "T002", "amount": 1500, "status": "CLOSED"},
        # status was never supplied for T003: reported as null, not missing.
        {"tradeId": "T003", "amount": 2500.5, "status": None},
    ]


def test_table_shows_only_the_configured_columns(loaded_client):
    view = loaded_client.get("/dashboard/trade-dashboard").json()["views"][1]

    assert "settled" not in view["rows"][0]


def test_booleans_survive_rendering(trade_client):
    trade_client.post(
        "/ingest",
        json={"schema": "trade", "rows": [{"tradeId": "T1", "amount": 1, "settled": False}]},
    )
    trade_client.post(
        "/dashboard",
        json={"name": "b", "schema": "trade", "views": [{"type": "table", "columns": ["settled"]}]},
    )

    assert trade_client.get("/dashboard/b").json()["views"][0]["rows"] == [{"settled": False}]


def test_mixed_integers_and_floats_sum_exactly(trade_client):
    trade_client.post(
        "/ingest",
        json={
            "schema": "trade",
            "rows": [{"tradeId": "T1", "amount": 1}, {"tradeId": "T2", "amount": 2.5}],
        },
    )

    assert summary(trade_client, "amount", "sum")["value"] == 3.5


def test_a_dashboard_reflects_rows_ingested_after_it_was_registered(loaded_client):
    before = loaded_client.get("/dashboard/trade-dashboard").json()["rowCount"]
    loaded_client.post(
        "/ingest", json={"schema": "trade", "rows": [{"tradeId": "T9", "amount": 500}]}
    )

    after = loaded_client.get("/dashboard/trade-dashboard").json()

    assert before == 3
    assert after["rowCount"] == 4
    assert after["views"][0]["value"] == 5500.5


def test_unknown_dashboard_is_not_found(client):
    response = client.get("/dashboard/ghost")

    assert response.status_code == 404
    assert error_of(response)["code"] == "DASHBOARD_NOT_FOUND"


def test_two_use_cases_are_served_by_the_same_backend(client):
    """The point of the platform: a second use case needs no backend change."""
    client.post(
        "/schema",
        json={
            "name": "trade",
            "fields": [
                {"name": "tradeId", "type": "string", "required": True},
                {"name": "amount", "type": "number", "required": True},
            ],
        },
    )
    client.post("/schema", json=CUSTOMER_SCHEMA)
    client.post("/ingest", json={"schema": "trade", "rows": [{"tradeId": "T1", "amount": 100}]})
    client.post(
        "/ingest",
        json={
            "schema": "customer",
            "rows": [
                {"customerId": "C1", "name": "Ada", "country": "UK", "score": 7},
                {"customerId": "C2", "name": "Grace", "country": "US", "score": 9},
            ],
        },
    )
    client.post(
        "/dashboard",
        json={
            "name": "trades",
            "schema": "trade",
            "views": [{"type": "summary", "field": "amount", "aggregation": "sum"}],
        },
    )
    client.post(
        "/dashboard",
        json={
            "name": "customers",
            "schema": "customer",
            "views": [
                {"type": "summary", "field": "score", "aggregation": "avg"},
                {"type": "table", "columns": ["customerId", "name", "country"]},
            ],
        },
    )

    trades = client.get("/dashboard/trades").json()
    customers = client.get("/dashboard/customers").json()

    assert trades["rowCount"] == 1
    assert trades["views"][0]["value"] == 100
    assert customers["rowCount"] == 2
    assert customers["views"][0]["value"] == 8
    assert customers["views"][1]["rows"][1] == {
        "customerId": "C2",
        "name": "Grace",
        "country": "US",
    }
