"""Dashboard views: validated at registration, rendered at read time.

``VIEW_RENDERERS`` is the second registry (after aggregations): a new view type
is one validator plus one renderer, with no changes to the endpoints.
"""

from __future__ import annotations

from typing import Any, Callable

from . import aggregations
from .models import DashboardConfig, SchemaDefinition, SummaryView, TableView


def _field_types(schema: SchemaDefinition) -> dict[str, str]:
    return {field.name: field.type for field in schema.fields}


# -- validation (POST /dashboard) ----------------------------------------


def _validate_summary(
    view: SummaryView, schema: SchemaDefinition, index: int
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    types = _field_types(schema)

    if view.field is None:
        if aggregations.requires_field(view.aggregation):
            errors.append(
                {
                    "view": index,
                    "issue": (
                        f"aggregation '{view.aggregation}' requires a 'field'"
                    ),
                }
            )
        return errors

    if view.field not in types:
        errors.append(
            {
                "view": index,
                "field": view.field,
                "issue": f"field is not part of schema '{schema.name}'",
            }
        )
        return errors

    field_type = types[view.field]
    if not aggregations.is_compatible(view.aggregation, field_type):
        errors.append(
            {
                "view": index,
                "field": view.field,
                "issue": (
                    f"aggregation '{view.aggregation}' requires a number field; "
                    f"'{view.field}' is {field_type}"
                ),
            }
        )
    return errors


def _validate_table(
    view: TableView, schema: SchemaDefinition, index: int
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    types = _field_types(schema)

    if not view.columns:
        errors.append({"view": index, "issue": "table view must define at least one column"})
        return errors

    seen: set[str] = set()
    for column in view.columns:
        if column in seen:
            errors.append({"view": index, "field": column, "issue": "duplicate column"})
        seen.add(column)
        if column not in types:
            errors.append(
                {
                    "view": index,
                    "field": column,
                    "issue": f"column is not part of schema '{schema.name}'",
                }
            )
    return errors


VIEW_VALIDATORS: dict[str, Callable[[Any, SchemaDefinition, int], list[dict[str, Any]]]] = {
    "summary": _validate_summary,
    "table": _validate_table,
}


def validate_views(
    config: DashboardConfig, schema: SchemaDefinition
) -> list[dict[str, Any]]:
    """Check every view against the schema it claims to read, reporting all
    problems at once so a bad configuration never reaches the renderer."""
    errors: list[dict[str, Any]] = []
    for index, view in enumerate(config.views):
        errors.extend(VIEW_VALIDATORS[view.type](view, schema, index))
    return errors


# -- rendering (GET /dashboard/{name}) ------------------------------------


def _render_summary(
    view: SummaryView, schema: SchemaDefinition, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    types = _field_types(schema)
    return {
        "type": "summary",
        "field": view.field,
        "fieldType": types.get(view.field) if view.field else None,
        "aggregation": view.aggregation,
        "value": aggregations.aggregate(view.aggregation, rows, view.field),
    }


def _render_table(
    view: TableView, schema: SchemaDefinition, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    types = _field_types(schema)
    return {
        "type": "table",
        # Column types come from the schema so a client can render numbers and
        # booleans differently without guessing from the data.
        "columns": [{"name": name, "type": types[name]} for name in view.columns],
        # A field an optional row omitted is reported as null, so every row has
        # the same keys and the table stays rectangular.
        "rows": [{name: row.get(name) for name in view.columns} for row in rows],
        "rowCount": len(rows),
    }


VIEW_RENDERERS: dict[str, Callable[[Any, SchemaDefinition, list[dict[str, Any]]], dict[str, Any]]] = {
    "summary": _render_summary,
    "table": _render_table,
}


def render_dashboard(
    config: DashboardConfig,
    schema: SchemaDefinition,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine configuration, schema and ingested rows into a renderable payload."""
    return {
        "name": config.name,
        "schema": config.schema_name,
        "rowCount": len(rows),
        "views": [VIEW_RENDERERS[view.type](view, schema, rows) for view in config.views],
    }
