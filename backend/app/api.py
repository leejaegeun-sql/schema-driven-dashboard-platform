"""HTTP routes.

Status-code policy, applied uniformly:

    201  resource registered / rows accepted
    200  read
    404  a referenced schema or requested dashboard does not exist
    409  a schema or dashboard with that name is already registered
    422  structurally readable but semantically invalid (validation failures,
         unknown row fields, empty batches, bad view/field/aggregation combos)

Checks run in that order too: existence of referenced resources, then name
conflicts, then semantic validation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status

from . import dashboard as dashboard_views
from . import validation
from .errors import ApiError
from .models import DashboardConfig, IngestRequest, SchemaDefinition
from .store import InMemoryStore

router = APIRouter()


def get_store(request: Request) -> InMemoryStore:
    return request.app.state.store


def _require_schema(store: InMemoryStore, name: str) -> SchemaDefinition:
    schema = store.get_schema(name)
    if schema is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "SCHEMA_NOT_FOUND",
            f"schema '{name}' is not registered",
        )
    return schema


@router.post(
    "/schema",
    status_code=status.HTTP_201_CREATED,
    summary="Register a data schema",
    tags=["schema"],
)
def register_schema(
    payload: SchemaDefinition, store: InMemoryStore = Depends(get_store)
) -> dict[str, Any]:
    """Register a named schema. Names are exact and case-sensitive; re-registering
    an existing name is a conflict rather than an overwrite, because rows already
    ingested against the old definition could not be re-validated."""
    if store.has_schema(payload.name):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "SCHEMA_ALREADY_EXISTS",
            f"schema '{payload.name}' is already registered",
        )
    if not payload.fields:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_SCHEMA",
            "schema must define at least one field",
        )
    errors = validation.validate_schema_definition(payload)
    if errors:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_SCHEMA",
            f"schema '{payload.name}' is invalid",
            errors,
        )

    store.add_schema(payload)
    return payload.model_dump()


@router.get(
    "/schemas",
    summary="List registered schemas (convenience endpoint)",
    tags=["schema"],
)
def list_schemas(store: InMemoryStore = Depends(get_store)) -> dict[str, Any]:
    """Not part of the core specification -- it exists so the UI can populate its
    dropdowns. Returns an empty list when nothing is registered."""
    return {"schemas": [schema.model_dump() for schema in store.list_schemas()]}


@router.post(
    "/ingest",
    status_code=status.HTTP_201_CREATED,
    summary="Ingest rows against a registered schema",
    tags=["data"],
)
def ingest(
    payload: IngestRequest, store: InMemoryStore = Depends(get_store)
) -> dict[str, Any]:
    """Ingestion is atomic: if any row fails validation nothing is stored, and
    every failing row and field is reported. Repeated calls append."""
    schema = _require_schema(store, payload.schema_name)

    if not payload.rows:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "EMPTY_BATCH",
            "'rows' must contain at least one row",
        )

    errors = validation.validate_rows(schema, payload.rows)
    if errors:
        failed = len({error["row"] for error in errors})
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "VALIDATION_ERROR",
            (
                f"{failed} of {len(payload.rows)} row(s) failed validation; "
                "no rows were ingested"
            ),
            errors,
        )

    total = store.add_rows(schema.name, payload.rows)
    return {"schema": schema.name, "ingested": len(payload.rows), "totalRows": total}


@router.post(
    "/dashboard",
    status_code=status.HTTP_201_CREATED,
    summary="Register a dashboard configuration",
    tags=["dashboard"],
)
def register_dashboard(
    payload: DashboardConfig, store: InMemoryStore = Depends(get_store)
) -> dict[str, Any]:
    """A dashboard names the schema it reads, and every view is validated against
    that schema now -- so a registered dashboard is always renderable."""
    schema = _require_schema(store, payload.schema_name)

    if store.has_dashboard(payload.name):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "DASHBOARD_ALREADY_EXISTS",
            f"dashboard '{payload.name}' is already registered",
        )
    if not payload.views:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_DASHBOARD",
            "dashboard must define at least one view",
        )
    errors = dashboard_views.validate_views(payload, schema)
    if errors:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_DASHBOARD",
            f"dashboard '{payload.name}' is not valid for schema '{schema.name}'",
            errors,
        )

    store.add_dashboard(payload)
    return payload.model_dump(by_alias=True)


@router.get(
    "/dashboards",
    summary="List registered dashboard configurations (convenience endpoint)",
    tags=["dashboard"],
)
def list_dashboards(store: InMemoryStore = Depends(get_store)) -> dict[str, Any]:
    """Not part of the core specification -- it exists so the UI can list what is
    available. Returns an empty list when nothing is registered."""
    return {
        "dashboards": [
            config.model_dump(by_alias=True) for config in store.list_dashboards()
        ]
    }


@router.get(
    "/dashboard/{name}",
    summary="Generate dashboard data",
    tags=["dashboard"],
)
def get_dashboard(
    name: str, store: InMemoryStore = Depends(get_store)
) -> dict[str, Any]:
    """Combine the registered schema, the ingested rows and the dashboard
    configuration into a payload ready for rendering. A dashboard with no data
    renders successfully: sum and count are 0, avg/min/max are null, tables empty."""
    config = store.get_dashboard(name)
    if config is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "DASHBOARD_NOT_FOUND",
            f"dashboard '{name}' is not registered",
        )
    schema = _require_schema(store, config.schema_name)
    rows = store.get_rows(config.schema_name)
    return dashboard_views.render_dashboard(config, schema, rows)
