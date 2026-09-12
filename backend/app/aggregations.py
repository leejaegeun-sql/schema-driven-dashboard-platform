"""Aggregation registry.

Adding an aggregation is one function plus one entry in ``_VALUE_AGGREGATIONS``
-- no endpoint, model or view code has to change.

Empty-input contract (a schema with no ingested rows, or an optional field that
no row supplies):

    sum -> 0        count -> 0        avg / min / max -> None
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

Number = float | int

#: Aggregations that only make sense over a numeric field.
NUMERIC_AGGREGATIONS: frozenset[str] = frozenset({"sum", "avg", "min", "max"})


def _sum(values: Sequence[Number]) -> Number:
    return sum(values)


def _avg(values: Sequence[Number]) -> float | None:
    return sum(values) / len(values) if values else None


def _min(values: Sequence[Number]) -> Number | None:
    return min(values) if values else None


def _max(values: Sequence[Number]) -> Number | None:
    return max(values) if values else None


_VALUE_AGGREGATIONS: dict[str, Callable[[Sequence[Number]], Any]] = {
    "sum": _sum,
    "avg": _avg,
    "min": _min,
    "max": _max,
}

#: ``count`` is handled separately: it counts rows, not values.
AGGREGATION_NAMES: frozenset[str] = frozenset(_VALUE_AGGREGATIONS) | {"count"}


def requires_number_field(name: str) -> bool:
    return name in NUMERIC_AGGREGATIONS


def requires_field(name: str) -> bool:
    """``count`` may omit ``field``; every other aggregation needs one."""
    return name != "count"


def is_compatible(name: str, field_type: str) -> bool:
    """Is this aggregation legal for a field of this type?"""
    return field_type == "number" if requires_number_field(name) else True


def aggregate(name: str, rows: list[dict[str, Any]], field: str | None) -> Any:
    """Apply an aggregation to rows.

    ``count`` with no field counts every row; ``count`` with a field counts the
    rows in which that field is present. Every other aggregation ignores rows
    that omit the field -- an optional field left out is absent, not zero.
    Explicit nulls never reach the store, so presence is the only test needed.
    """
    if name == "count":
        if field is None:
            return len(rows)
        return sum(1 for row in rows if field in row)
    values = [row[field] for row in rows if field in row]
    return _VALUE_AGGREGATIONS[name](values)
