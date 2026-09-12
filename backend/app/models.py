"""Request and configuration models.

These models cover the *structural* contract (shapes, literals, known keys).
Everything that depends on registered state -- does this field exist in that
schema, is this aggregation legal for that field's type -- lives in
``validation.py`` and ``dashboard.py`` so it can be unit-tested without HTTP.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Field types the platform understands. Unknown names are rejected at
#: registration rather than silently accepted.
FieldType = Literal["string", "number", "boolean"]

#: Aggregations a summary view may ask for. Must stay in step with the
#: registry in ``aggregations.py`` (``test_registries.py`` enforces that).
AggregationName = Literal["sum", "avg", "min", "max", "count"]

#: Schema and dashboard names appear in URLs, so keep them URL-safe.
NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class StrictModel(BaseModel):
    """Base model: an unrecognised key in a request body is a client error."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SchemaField(StrictModel):
    name: str = Field(min_length=1)
    type: FieldType
    required: bool = False
    # Purely descriptive metadata: it records how a field is *typically*
    # consumed. A dashboard view must still state its own aggregation, so this
    # can never create hidden rendering behaviour.
    aggregation: AggregationName | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("field name must not be blank")
        return stripped


class SchemaDefinition(StrictModel):
    name: str = Field(pattern=NAME_PATTERN)
    fields: list[SchemaField]


class IngestRequest(StrictModel):
    # ``schema`` shadows an attribute of pydantic's BaseModel, so the attribute
    # is named ``schema_name`` and exposed over the wire under its alias.
    schema_name: Annotated[str, Field(alias="schema", pattern=NAME_PATTERN)]
    rows: list[Any]


class SummaryView(StrictModel):
    type: Literal["summary"]
    # Optional only because ``count`` may count rows rather than values.
    field: str | None = None
    aggregation: AggregationName


class TableView(StrictModel):
    type: Literal["table"]
    columns: list[str]


#: Discriminated on ``type``, so an unknown view type fails structurally.
View = Annotated[Union[SummaryView, TableView], Field(discriminator="type")]

#: View types the configuration model accepts, derived from the union above.
VIEW_TYPES: frozenset[str] = frozenset(
    member.model_fields["type"].annotation.__args__[0]  # type: ignore[union-attr]
    for member in (SummaryView, TableView)
)


class DashboardConfig(StrictModel):
    name: str = Field(pattern=NAME_PATTERN)
    schema_name: Annotated[str, Field(alias="schema", pattern=NAME_PATTERN)]
    views: list[View]
