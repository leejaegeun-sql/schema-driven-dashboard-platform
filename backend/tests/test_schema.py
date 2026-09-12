"""POST /schema and GET /schemas."""

from __future__ import annotations

import pytest
from conftest import CUSTOMER_SCHEMA, TRADE_SCHEMA, error_of


def test_register_schema_returns_201_and_the_stored_definition(client):
    response = client.post("/schema", json=TRADE_SCHEMA)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "trade"
    assert [field["name"] for field in body["fields"]] == [
        "tradeId",
        "amount",
        "status",
        "settled",
    ]
    # Defaults are made explicit in the stored definition.
    assert body["fields"][2]["required"] is False
    assert body["fields"][1]["aggregation"] == "sum"
    assert body["fields"][0]["aggregation"] is None


def test_two_unrelated_use_cases_coexist(client):
    assert client.post("/schema", json=TRADE_SCHEMA).status_code == 201
    assert client.post("/schema", json=CUSTOMER_SCHEMA).status_code == 201

    names = [schema["name"] for schema in client.get("/schemas").json()["schemas"]]
    assert names == ["trade", "customer"]


def test_duplicate_schema_name_is_a_conflict(trade_client):
    response = trade_client.post("/schema", json=TRADE_SCHEMA)

    assert response.status_code == 409
    assert error_of(response)["code"] == "SCHEMA_ALREADY_EXISTS"


def test_schema_names_are_case_sensitive(trade_client):
    response = trade_client.post("/schema", json={**TRADE_SCHEMA, "name": "Trade"})

    assert response.status_code == 201


def test_unknown_field_type_is_rejected(client):
    response = client.post(
        "/schema", json={"name": "trade", "fields": [{"name": "when", "type": "date"}]}
    )

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "REQUEST_VALIDATION_ERROR"
    assert error["details"][0]["field"].startswith("fields.0.type")


def test_empty_field_list_is_rejected(client):
    response = client.post("/schema", json={"name": "trade", "fields": []})

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "INVALID_SCHEMA"
    assert "at least one field" in error["message"]


def test_duplicate_field_names_are_rejected(client):
    response = client.post(
        "/schema",
        json={
            "name": "trade",
            "fields": [
                {"name": "amount", "type": "number"},
                {"name": "amount", "type": "string"},
            ],
        },
    )

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "INVALID_SCHEMA"
    assert error["details"] == [{"field": "amount", "issue": "duplicate field name"}]


def test_blank_field_name_is_rejected(client):
    response = client.post(
        "/schema", json={"name": "trade", "fields": [{"name": "   ", "type": "string"}]}
    )

    assert response.status_code == 422
    assert error_of(response)["code"] == "REQUEST_VALIDATION_ERROR"


def test_field_names_are_stripped(client):
    response = client.post(
        "/schema", json={"name": "trade", "fields": [{"name": " amount ", "type": "number"}]}
    )

    assert response.status_code == 201
    assert response.json()["fields"][0]["name"] == "amount"


@pytest.mark.parametrize("aggregation", ["sum", "avg", "min", "max"])
def test_numeric_aggregation_metadata_requires_a_number_field(client, aggregation):
    response = client.post(
        "/schema",
        json={
            "name": "trade",
            "fields": [{"name": "status", "type": "string", "aggregation": aggregation}],
        },
    )

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "INVALID_SCHEMA"
    assert error["details"][0]["field"] == "status"
    assert aggregation in error["details"][0]["issue"]


@pytest.mark.parametrize("field_type", ["string", "number", "boolean"])
def test_count_metadata_is_allowed_on_any_field_type(client, field_type):
    response = client.post(
        "/schema",
        json={
            "name": "trade",
            "fields": [{"name": "value", "type": field_type, "aggregation": "count"}],
        },
    )

    assert response.status_code == 201


def test_unknown_aggregation_metadata_is_rejected(client):
    response = client.post(
        "/schema",
        json={
            "name": "trade",
            "fields": [{"name": "amount", "type": "number", "aggregation": "median"}],
        },
    )

    assert response.status_code == 422
    assert error_of(response)["code"] == "REQUEST_VALIDATION_ERROR"


def test_unknown_top_level_key_is_rejected(client):
    response = client.post("/schema", json={**TRADE_SCHEMA, "owner": "ops"})

    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "REQUEST_VALIDATION_ERROR"
    assert error["details"][0]["field"] == "owner"


def test_unknown_key_inside_a_field_is_rejected(client):
    response = client.post(
        "/schema",
        json={"name": "trade", "fields": [{"name": "amount", "type": "number", "nullable": True}]},
    )

    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "fields.0.nullable"


def test_missing_name_is_rejected(client):
    response = client.post("/schema", json={"fields": TRADE_SCHEMA["fields"]})

    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "name"


@pytest.mark.parametrize("name", ["", " ", "trade/1", "trade dashboard", "-trade"])
def test_schema_names_must_be_url_safe(client, name):
    response = client.post("/schema", json={"name": name, "fields": TRADE_SCHEMA["fields"]})

    assert response.status_code == 422
    assert error_of(response)["code"] == "REQUEST_VALIDATION_ERROR"


def test_list_schemas_is_empty_before_anything_is_registered(client):
    response = client.get("/schemas")

    assert response.status_code == 200
    assert response.json() == {"schemas": []}


def test_list_schemas_returns_full_definitions(trade_client):
    """The UI builds its ingest form from this, so it needs the fields, not just
    the names."""
    schemas = trade_client.get("/schemas").json()["schemas"]

    assert len(schemas) == 1
    assert schemas[0]["name"] == "trade"
    assert schemas[0]["fields"][1] == {
        "name": "amount",
        "type": "number",
        "required": True,
        "aggregation": "sum",
    }
