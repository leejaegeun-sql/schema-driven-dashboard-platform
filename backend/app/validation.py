"""Validation of schema definitions and of ingested rows.

Pure functions returning lists of error details, with no HTTP awareness, so the
rules can be unit-tested directly. Callers decide the status code.
"""

from __future__ import annotations

from typing import Any, Callable

from . import aggregations
from .models import SchemaDefinition

#: ``bool`` is a subclass of ``int`` in Python, so a boolean would otherwise
#: pass as a number. It must not.
TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def json_type_name(value: Any) -> str:
    """The JSON type name of a value, for readable error messages."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _detail(row: int, field: str | None, issue: str) -> dict[str, Any]:
    detail: dict[str, Any] = {"row": row, "issue": issue}
    if field is not None:
        detail["field"] = field
    return detail


def validate_schema_definition(schema: SchemaDefinition) -> list[dict[str, Any]]:
    """Check a schema definition for internal contradictions."""
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in schema.fields:
        if field.name in seen:
            errors.append({"field": field.name, "issue": "duplicate field name"})
        seen.add(field.name)
        if field.aggregation and not aggregations.is_compatible(
            field.aggregation, field.type
        ):
            errors.append(
                {
                    "field": field.name,
                    "issue": (
                        f"aggregation metadata '{field.aggregation}' requires a "
                        f"number field; '{field.name}' is {field.type}"
                    ),
                }
            )
    return errors


def validate_row(
    schema: SchemaDefinition, row: Any, row_index: int
) -> list[dict[str, Any]]:
    """Validate one row, reporting *every* problem it has, not just the first."""
    if not isinstance(row, dict):
        return [
            _detail(
                row_index, None, f"expected an object, got {json_type_name(row)}"
            )
        ]

    errors: list[dict[str, Any]] = []
    known = {field.name for field in schema.fields}

    for key in row:
        if key not in known:
            errors.append(
                _detail(
                    row_index,
                    key,
                    f"unknown field is not part of schema '{schema.name}'",
                )
            )

    for field in schema.fields:
        if field.name not in row:
            if field.required:
                errors.append(_detail(row_index, field.name, "required field is missing"))
            continue
        value = row[field.name]
        if value is None:
            errors.append(
                _detail(
                    row_index,
                    field.name,
                    "null is not an accepted value; omit the field instead",
                )
            )
            continue
        if not TYPE_CHECKS[field.type](value):
            errors.append(
                _detail(
                    row_index,
                    field.name,
                    f"expected {field.type}, got {json_type_name(value)}",
                )
            )

    return errors


def validate_rows(
    schema: SchemaDefinition, rows: list[Any]
) -> list[dict[str, Any]]:
    """Validate a whole batch. Ingestion is atomic, so the caller stores rows
    only when this comes back empty."""
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        errors.extend(validate_row(schema, row, index))
    return errors
