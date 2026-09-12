"""Validation is a pure function, so it is tested without going through HTTP."""

from __future__ import annotations

import pytest
from app.models import SchemaDefinition
from app.validation import json_type_name, validate_row, validate_rows

SCHEMA = SchemaDefinition.model_validate(
    {
        "name": "trade",
        "fields": [
            {"name": "tradeId", "type": "string", "required": True},
            {"name": "amount", "type": "number", "required": True},
            {"name": "status", "type": "string"},
        ],
    }
)


def test_a_valid_row_produces_no_errors():
    assert validate_row(SCHEMA, {"tradeId": "T1", "amount": 1}, 0) == []


def test_all_problems_in_a_row_are_reported_together():
    errors = validate_row(SCHEMA, {"amount": "x", "trader": "alice"}, 7)

    assert [error["row"] for error in errors] == [7, 7, 7]
    assert [error["field"] for error in errors] == ["trader", "tradeId", "amount"]


def test_row_indices_are_positions_in_the_batch():
    errors = validate_rows(SCHEMA, [{"tradeId": "T1", "amount": 1}, {}, {}])

    assert sorted({error["row"] for error in errors}) == [1, 2]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "boolean"),
        (1, "number"),
        (1.5, "number"),
        ("x", "string"),
        (None, "null"),
        ([], "array"),
        ({}, "object"),
    ],
)
def test_json_type_names(value, expected):
    assert json_type_name(value) == expected
