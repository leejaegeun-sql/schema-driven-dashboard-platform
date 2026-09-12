"""POST /dashboard and GET /dashboards: configuration is validated eagerly."""

from __future__ import annotations

import pytest
from conftest import CUSTOMER_SCHEMA, TRADE_DASHBOARD, error_of


def register(client, views, name="d", schema="trade"):
    return client.post(
        "/dashboard", json={"name": name, "schema": schema, "views": views}
    )


def test_register_dashboard_returns_201_and_the_stored_config(trade_client):
    response = trade_client.post("/dashboard", json=TRADE_DASHBOARD)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "trade-dashboard"
    assert body["schema"] == "trade"
    assert body["views"][0] == {"type": "summary", "field": "amount", "aggregation": "sum"}
    assert body["views"][1] == {"type": "table", "columns": ["tradeId", "amount", "status"]}


def test_duplicate_dashboard_name_is_a_conflict(trade_client):
    trade_client.post("/dashboard", json=TRADE_DASHBOARD)

    response = trade_client.post("/dashboard", json=TRADE_DASHBOARD)

    assert response.status_code == 409
    assert error_of(response)["code"] == "DASHBOARD_ALREADY_EXISTS"


def test_dashboard_names_are_global_across_schemas(trade_client):
    trade_client.post("/schema", json=CUSTOMER_SCHEMA)
    register(trade_client, [{"type": "table", "columns": ["tradeId"]}], name="shared")

    response = register(
        trade_client,
        [{"type": "table", "columns": ["customerId"]}],
        name="shared",
        schema="customer",
    )

    assert response.status_code == 409


def test_unknown_schema_is_not_found(client):
    response = register(client, [{"type": "table", "columns": ["tradeId"]}])

    assert response.status_code == 404
    assert error_of(response)["code"] == "SCHEMA_NOT_FOUND"


def test_empty_view_list_is_rejected(trade_client):
    response = register(trade_client, [])

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "INVALID_DASHBOARD"
    assert "at least one view" in error["message"]


def test_unknown_view_type_is_rejected(trade_client):
    response = register(trade_client, [{"type": "pie", "field": "amount"}])

    assert response.status_code == 422
    assert error_of(response)["code"] == "REQUEST_VALIDATION_ERROR"


def test_summary_view_must_state_its_own_aggregation(trade_client):
    """The schema declares aggregation 'sum' on amount, but that metadata is
    descriptive: a view that omits its aggregation is still invalid."""
    response = register(trade_client, [{"type": "summary", "field": "amount"}])

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "REQUEST_VALIDATION_ERROR"
    assert error["details"][0]["field"].endswith("aggregation")


def test_summary_field_must_exist_in_the_schema(trade_client):
    response = register(
        trade_client, [{"type": "summary", "field": "amonut", "aggregation": "sum"}]
    )

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "INVALID_DASHBOARD"
    assert error["details"] == [
        {"view": 0, "field": "amonut", "issue": "field is not part of schema 'trade'"}
    ]


@pytest.mark.parametrize("aggregation", ["sum", "avg", "min", "max"])
def test_numeric_aggregations_require_a_number_field(trade_client, aggregation):
    response = register(
        trade_client, [{"type": "summary", "field": "status", "aggregation": aggregation}]
    )

    assert response.status_code == 422
    detail = error_of(response)["details"][0]
    assert detail == {
        "view": 0,
        "field": "status",
        "issue": f"aggregation '{aggregation}' requires a number field; 'status' is string",
    }


@pytest.mark.parametrize("aggregation", ["sum", "avg", "min", "max"])
def test_numeric_aggregations_require_a_field(trade_client, aggregation):
    response = register(trade_client, [{"type": "summary", "aggregation": aggregation}])

    assert response.status_code == 422
    detail = error_of(response)["details"][0]
    assert detail == {"view": 0, "issue": f"aggregation '{aggregation}' requires a 'field'"}


def test_count_may_omit_the_field(trade_client):
    assert register(trade_client, [{"type": "summary", "aggregation": "count"}]).status_code == 201


@pytest.mark.parametrize("field", ["status", "settled", "amount"])
def test_count_accepts_any_field_type(trade_client, field):
    response = register(trade_client, [{"type": "summary", "field": field, "aggregation": "count"}])

    assert response.status_code == 201


def test_count_still_requires_a_known_field(trade_client):
    response = register(trade_client, [{"type": "summary", "field": "nope", "aggregation": "count"}])

    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "nope"


def test_table_columns_must_exist_in_the_schema(trade_client):
    response = register(trade_client, [{"type": "table", "columns": ["tradeId", "trader"]}])

    assert response.status_code == 422
    assert error_of(response)["details"] == [
        {"view": 0, "field": "trader", "issue": "column is not part of schema 'trade'"}
    ]


def test_duplicate_table_columns_are_rejected(trade_client):
    response = register(trade_client, [{"type": "table", "columns": ["tradeId", "tradeId"]}])

    assert response.status_code == 422
    assert error_of(response)["details"] == [
        {"view": 0, "field": "tradeId", "issue": "duplicate column"}
    ]


def test_table_needs_at_least_one_column(trade_client):
    response = register(trade_client, [{"type": "table", "columns": []}])

    assert response.status_code == 422
    assert error_of(response)["details"] == [
        {"view": 0, "issue": "table view must define at least one column"}
    ]


def test_all_bad_views_are_reported_at_once(trade_client):
    response = register(
        trade_client,
        [
            {"type": "summary", "field": "amount", "aggregation": "sum"},
            {"type": "summary", "field": "status", "aggregation": "avg"},
            {"type": "table", "columns": ["ghost"]},
        ],
    )

    assert response.status_code == 422
    details = error_of(response)["details"]
    assert [detail["view"] for detail in details] == [1, 2]


def test_a_view_may_not_reference_another_schemas_field(trade_client):
    trade_client.post("/schema", json=CUSTOMER_SCHEMA)

    response = register(trade_client, [{"type": "table", "columns": ["customerId"]}])

    assert response.status_code == 422


def test_list_dashboards_is_empty_before_anything_is_registered(client):
    response = client.get("/dashboards")

    assert response.status_code == 200
    assert response.json() == {"dashboards": []}


def test_list_dashboards_returns_configs_with_their_schema(loaded_client):
    dashboards = loaded_client.get("/dashboards").json()["dashboards"]

    assert len(dashboards) == 1
    assert dashboards[0]["name"] == "trade-dashboard"
    assert dashboards[0]["schema"] == "trade"
