"""In-memory storage. No database, no persistence -- restarting clears it."""

from __future__ import annotations

from typing import Any

from .models import DashboardConfig, SchemaDefinition


class InMemoryStore:
    """Schemas, their ingested rows, and dashboard configurations.

    Names are matched exactly and are case-sensitive. The store is deliberately
    free of HTTP concerns: conflicts and lookups are decided by the caller.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, SchemaDefinition] = {}
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._dashboards: dict[str, DashboardConfig] = {}

    # -- schemas ---------------------------------------------------------
    def add_schema(self, schema: SchemaDefinition) -> None:
        self._schemas[schema.name] = schema
        self._rows.setdefault(schema.name, [])

    def get_schema(self, name: str) -> SchemaDefinition | None:
        return self._schemas.get(name)

    def has_schema(self, name: str) -> bool:
        return name in self._schemas

    def list_schemas(self) -> list[SchemaDefinition]:
        return list(self._schemas.values())

    # -- rows ------------------------------------------------------------
    def add_rows(self, schema_name: str, rows: list[dict[str, Any]]) -> int:
        """Append validated rows and return the new total for that schema."""
        stored = self._rows.setdefault(schema_name, [])
        # Copy so later mutation of the caller's dicts cannot reach the store.
        stored.extend(dict(row) for row in rows)
        return len(stored)

    def get_rows(self, schema_name: str) -> list[dict[str, Any]]:
        """Rows in ingestion order."""
        return self._rows.get(schema_name, [])

    # -- dashboards ------------------------------------------------------
    def add_dashboard(self, config: DashboardConfig) -> None:
        self._dashboards[config.name] = config

    def get_dashboard(self, name: str) -> DashboardConfig | None:
        return self._dashboards.get(name)

    def has_dashboard(self, name: str) -> bool:
        return name in self._dashboards

    def list_dashboards(self) -> list[DashboardConfig]:
        return list(self._dashboards.values())
