"""The two extension points stay in step with the models that describe them."""

from __future__ import annotations

import typing

import pytest
from app import aggregations
from app.dashboard import VIEW_RENDERERS, VIEW_VALIDATORS
from app.models import VIEW_TYPES, AggregationName


def test_every_declared_view_type_can_be_validated_and_rendered():
    assert VIEW_TYPES == set(VIEW_RENDERERS) == set(VIEW_VALIDATORS)


def test_every_declared_aggregation_is_implemented():
    assert set(typing.get_args(AggregationName)) == aggregations.AGGREGATION_NAMES


@pytest.mark.parametrize(
    ("name", "expected"), [("sum", 0), ("avg", None), ("min", None), ("max", None), ("count", 0)]
)
def test_aggregating_no_rows(name, expected):
    assert aggregations.aggregate(name, [], "amount") == expected


@pytest.mark.parametrize(
    ("name", "expected"), [("sum", 6), ("avg", 2), ("min", 1), ("max", 3), ("count", 3)]
)
def test_aggregating_values(name, expected):
    rows = [{"amount": 1}, {"amount": 2}, {"amount": 3}]

    assert aggregations.aggregate(name, rows, "amount") == expected


def test_count_of_rows_versus_count_of_a_field():
    rows = [{"amount": 1}, {}, {"amount": 3}]

    assert aggregations.aggregate("count", rows, None) == 3
    assert aggregations.aggregate("count", rows, "amount") == 2


@pytest.mark.parametrize(
    ("name", "field_type", "expected"),
    [
        ("sum", "number", True),
        ("sum", "string", False),
        ("avg", "boolean", False),
        ("count", "string", True),
        ("count", "boolean", True),
    ],
)
def test_aggregation_compatibility(name, field_type, expected):
    assert aggregations.is_compatible(name, field_type) is expected
