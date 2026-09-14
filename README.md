# Schema-Driven Dashboard Platform

A generic backend whose behaviour is entirely configuration-driven: register a
schema, ingest rows against it, register a dashboard configuration, read back
rendered dashboard data. Supporting a new use case — trade, customer, anything
else — requires no backend code.

Everything is held in memory. Restarting the server clears all state.

---

## Quick start

Run the application and tests from a fresh virtual environment created using
`backend/requirements.txt`; execution against unrelated globally installed
packages is not supported.

```bash
# from the project root
python3.12 -m venv .venv                    # Python 3.12
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

cd backend
python -m pytest                             # 184 tests; config from backend/pytest.ini
uvicorn app.main:app --reload                # serves on http://localhost:8000
```

Both `python -m pytest` and `uvicorn app.main:app` must be run from `backend/`:
that is where `pytest.ini` supplies `pythonpath` and `testpaths`, and where
`app.main` resolves. To serve from the project root instead, use
`uvicorn app.main:app --app-dir backend`.

Then open <http://localhost:8000/> and work through the four panels in order:
**1** register a schema → **2** ingest rows → **3** configure a dashboard →
**4** load it. That is the whole product; nothing else needs to be set up.

| URL | What it is |
| --- | --- |
| <http://localhost:8000/> | The UI (register schemas, ingest, configure, view) |
| <http://localhost:8000/docs> | Interactive OpenAPI documentation |

Each panel feeds the next — that is the data model, not a UI quirk: rows are
validated against a registered schema, and a dashboard is configured against
one, so the Schema dropdowns in panels 2 and 3 stay empty until a schema exists.

**A 60-second first run:**

**1. Register schema.** Set *Schema name* to `trade`, then fill three field
rows — *Add field* creates each new one:

| Name | Type | Aggregation metadata | Required |
| --- | --- | --- | --- |
| `tradeId` | `string` | no metadata | ☑ |
| `amount` | `number` | `sum` | ☑ |
| `status` | `string` | no metadata | ☐ |

Click **Register schema** and wait for the green *"Registered 'trade' with 3
field(s)."* The aggregation metadata is descriptive: it records how `amount` is
typically consumed, and a dashboard must still state its own aggregation.

**2. Ingest data.** The *Schema* dropdown now offers `trade`, and the form
builds itself from those fields. Paste into the batch box and click **Ingest
JSON batch**:

```json
[{"tradeId":"T001","amount":1000,"status":"OPEN"},{"tradeId":"T002","amount":1500}]
```

Expect *"Ingested 2 row(s); 2 stored for 'trade'."* T002 omits `status`
deliberately.

**3. Configure dashboard.** *Dashboard name* `trade-dashboard`, *Schema*
`trade`. Set *Summary field* to `amount` and *Aggregation* to `sum`, then click
**Add summary**. Under *Table columns* tick `tradeId`, `amount` and `status`,
then click **Add table view**. Two chips appear; click **Register dashboard**.

**4. Dashboard data.** Choose `trade-dashboard` and click **Load**. Expect a
summary card reading **2500** and a table whose T002 row shows `—` under
`status`, because that field was never supplied.

Prefer the terminal? [Two use cases, one backend](#two-use-cases-one-backend)
is the same walkthrough as runnable `curl` commands.

No database, no build step and no network access at runtime.
`requirements.txt` pins the whole stack:

| Dependency | Version | Why |
| --- | --- | --- |
| `fastapi` | 0.141.1 | Routing, request models, OpenAPI docs |
| `pydantic` | 2.13.5 | Structural validation of request bodies |
| `uvicorn[standard]` | 0.52.4 | ASGI server (`--reload` needs the extra) |
| `pytest` | 9.1.1 | test-only |
| `httpx2` | 2.12.0 | test-only — starlette 1.6's `TestClient` transport |

Field-level validation is hand-written in `app/validation.py` — the `jsonschema`
package is neither installed nor imported. (Pydantic still emits JSON Schema for
the OpenAPI document at `/docs`; that is FastAPI's own machinery, not a
validation library this project depends on.)

---

## API

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| `POST` | `/schema` | 201 | Register a data schema |
| `GET` | `/schemas` | 200 | List registered schemas *(convenience)* |
| `POST` | `/ingest` | 201 | Ingest rows against a registered schema |
| `POST` | `/dashboard` | 201 | Register a dashboard configuration |
| `GET` | `/dashboards` | 200 | List dashboard configurations *(convenience)* |
| `GET` | `/dashboard/{name}` | 200 | Generate dashboard data |

`GET /schemas` and `GET /dashboards` are not part of the assignment. They exist
so the UI can populate its dropdowns without the user retyping names, and they
return `{"schemas": []}` / `{"dashboards": []}` when nothing is registered.

### 1. Register a schema

```http
POST /schema
{
  "name": "trade",
  "fields": [
    {"name": "tradeId", "type": "string", "required": true},
    {"name": "amount",  "type": "number", "required": true, "aggregation": "sum"},
    {"name": "status",  "type": "string"},
    {"name": "settled", "type": "boolean"}
  ]
}
```

* `type` is one of `string`, `number`, `boolean`. Unknown types are rejected.
* `required` defaults to `false`.
* `aggregation` is optional **descriptive metadata** — see
  [Metadata is descriptive](#metadata-is-descriptive).
* Names must be URL-safe (`^[A-Za-z0-9][A-Za-z0-9_.-]*$`) and are matched
  exactly: `trade` and `Trade` are two different schemas.

### 2. Ingest data

```http
POST /ingest
{
  "schema": "trade",
  "rows": [
    {"tradeId": "T001", "amount": 1000, "status": "OPEN", "settled": false},
    {"tradeId": "T002", "amount": 1500, "status": "CLOSED"}
  ]
}
→ 201 {"schema": "trade", "ingested": 2, "totalRows": 2}
```

Each row must satisfy all of:

| Rule | Violation |
| --- | --- |
| Every required field is present | `required field is missing` |
| Values match the declared type | `expected number, got string` |
| No field outside the schema | `unknown field is not part of schema 'trade'` |
| No explicit `null`, for any field | `null is not an accepted value; omit the field instead` |

`true`/`false` are **not** numbers, even though Python's `bool` subclasses `int`.
Integers and floats are both `number`.

Repeated calls append. Ingestion is **atomic**: if any row fails, nothing is
stored and every offending row and field is listed in one response.

### 3. Register a dashboard configuration

```http
POST /dashboard
{
  "name": "trade-dashboard",
  "schema": "trade",
  "views": [
    {"type": "summary", "field": "amount", "aggregation": "sum"},
    {"type": "summary", "aggregation": "count"},
    {"type": "table", "columns": ["tradeId", "amount", "status"]}
  ]
}
```

Views are validated against the schema **at registration time**, so a
registered dashboard is always renderable:

* every `field` / `column` must exist in the referenced schema;
* `sum`, `avg`, `min`, `max` require a `number` field;
* `count` accepts any field type, and may omit `field` entirely;
* table columns must be non-empty and free of duplicates.

### 4. Generate dashboard data

```http
GET /dashboard/trade-dashboard
{
  "name": "trade-dashboard",
  "schema": "trade",
  "rowCount": 2,
  "views": [
    {"type": "summary", "field": "amount", "fieldType": "number",
     "aggregation": "sum", "value": 2500},
    {"type": "summary", "field": null, "fieldType": null,
     "aggregation": "count", "value": 2},
    {"type": "table",
     "columns": [{"name": "tradeId", "type": "string"},
                 {"name": "amount",  "type": "number"},
                 {"name": "status",  "type": "string"}],
     "rows": [{"tradeId": "T001", "amount": 1000, "status": "OPEN"},
              {"tradeId": "T002", "amount": 1500, "status": "CLOSED"}],
     "rowCount": 2}
  ]
}
```

All three inputs are used: the **configuration** selects the views, the
**ingested rows** supply the data, and the **schema** supplies each column's
type so a client can align and format values without inspecting the data.

---

## Behaviour worth knowing

### Error responses

Every non-2xx response — application errors, pydantic validation failures and
framework errors such as 404/405 alike — uses one envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "1 of 3 row(s) failed validation; no rows were ingested",
    "details": [
      {"row": 1, "field": "amount", "issue": "expected number, got string"}
    ]
  }
}
```

`details` is always a list; each entry always has `issue`, plus whichever of
`row`, `field` and `view` locates the problem. FastAPI's default
`{"detail": ...}` body never reaches a client: `RequestValidationError` is
overridden to use this envelope while keeping status 422.

| Status | When |
| --- | --- |
| `404` | A referenced schema or requested dashboard does not exist |
| `409` | That schema/dashboard name is already registered |
| `422` | Structurally readable but semantically invalid |

`422` covers empty batches, row validation failures, unknown row fields, schema
definition problems and invalid view/field/aggregation combinations. Checks run
in the order: referenced resources exist (404) → name is free (409) → the body
makes sense (422).

### Aggregations and empty data

| Aggregation | Field | Over no rows |
| --- | --- | --- |
| `sum` | required `number` | `0` |
| `avg` | required `number` | `null` |
| `min` / `max` | required `number` | `null` |
| `count` | optional, any type | `0` |

`count` **without** a field counts every row; `count` **with** a field counts the
rows in which that field is present. `sum`/`avg`/`min`/`max` skip rows that omit
an optional field — an omitted field is absent, not zero, so an average is taken
over the values that exist.

A schema with no ingested rows renders successfully (`200`), never `404`.

In table output, a field a row omitted is reported as `null` so every row has
the same keys. That is a rendering convenience only; `null` is still rejected on
the way in.

### Metadata is descriptive

`{"name": "amount", "type": "number", "aggregation": "sum"}` records how a field
is *typically* consumed. It is validated (only known aggregation names, and only
compatible with the field's type) but it never changes rendering: a summary view
must always state its own `aggregation`. Nothing is inferred behind the user's
back.

### Duplicate names

Re-registering an existing schema or dashboard name is a `409`, not an
overwrite. There is deliberately no update path: replacing a schema would strand
rows that were validated against the previous definition.

---

## Two use cases, one backend

```bash
# Trade
curl -X POST localhost:8000/schema -H 'content-type: application/json' -d '{
  "name":"trade","fields":[
    {"name":"tradeId","type":"string","required":true},
    {"name":"amount","type":"number","required":true,"aggregation":"sum"},
    {"name":"status","type":"string"}]}'

curl -X POST localhost:8000/ingest -H 'content-type: application/json' -d '{
  "schema":"trade","rows":[
    {"tradeId":"T001","amount":10000,"status":"OPEN"},
    {"tradeId":"T002","amount":15000,"status":"CLOSED"}]}'

curl -X POST localhost:8000/dashboard -H 'content-type: application/json' -d '{
  "name":"trade-dashboard","schema":"trade","views":[
    {"type":"summary","field":"amount","aggregation":"sum"},
    {"type":"table","columns":["tradeId","amount","status"]}]}'

curl localhost:8000/dashboard/trade-dashboard

# Customer — same server, no new backend code
curl -X POST localhost:8000/schema -H 'content-type: application/json' -d '{
  "name":"customer","fields":[
    {"name":"customerId","type":"string","required":true},
    {"name":"name","type":"string","required":true},
    {"name":"country","type":"string"},
    {"name":"score","type":"number"}]}'

curl -X POST localhost:8000/ingest -H 'content-type: application/json' -d '{
  "schema":"customer","rows":[
    {"customerId":"C1","name":"Ada","country":"UK","score":7},
    {"customerId":"C2","name":"Grace","country":"US","score":9}]}'

curl -X POST localhost:8000/dashboard -H 'content-type: application/json' -d '{
  "name":"customer-dashboard","schema":"customer","views":[
    {"type":"summary","field":"score","aggregation":"avg"},
    {"type":"summary","aggregation":"count"},
    {"type":"table","columns":["customerId","name","country"]}]}'

curl localhost:8000/dashboard/customer-dashboard
```

---

## Layout

```
backend/
  app/
    main.py          FastAPI app factory, error handlers, UI route
    api.py           HTTP routes and status-code policy
    models.py        Request/configuration models (structural validation)
    validation.py    Schema-definition and row validation (pure functions)
    aggregations.py  Aggregation registry
    dashboard.py     View validation + view rendering registries
    store.py         In-memory store
    errors.py        The error envelope
  tests/             184 tests
  requirements.txt
frontend/
  index.html         Single self-contained page: no build step, no dependencies
```

Two registries carry the extensibility:

* `aggregations._VALUE_AGGREGATIONS` — a new aggregation is one function plus
  one entry;
* `dashboard.VIEW_VALIDATORS` / `VIEW_RENDERERS` — a new view type is one
  validator plus one renderer.

No endpoint changes in either case. `tests/test_registries.py` fails if a
declared view type or aggregation is ever left unimplemented.

`app.main.create_app()` builds an application with its own store, which is what
gives every test a clean slate.

---

## Design decisions

| Decision | Rationale |
| --- | --- |
| A dashboard config carries a required `schema` | The assignment's example omits it, but `GET /dashboard/{name}` has to know which rows to read, and view fields can only be validated against a known schema. |
| Ingestion is atomic | A half-applied batch leaves the caller reconciling state; all-or-nothing with a complete error list is easier to act on. |
| Duplicate names conflict (409) | See [Duplicate names](#duplicate-names). |
| Views validated at registration | Fails fast, at the point where the mistake was made, rather than rendering a broken dashboard later. |
| Explicit `null` always rejected | One rule to state and to reason about: a value you do not have is an omitted key. |
| `422`, not `400`, for semantic failures | Consistent with FastAPI's own validation status, so clients see one code for "readable but wrong". |
| Field types limited to `string`/`number`/`boolean` | Enough for the use cases; dates would need parsing and timezone rules that earn nothing here. |

## Limitations

* In-memory only — restarting the server loses every schema, row and dashboard.
* No authentication, authorization, pagination, filtering, sorting or grouping.
* No update or delete: schemas, rows and dashboards can only be added.
* `avg` returns an unrounded float, so `5000.5 / 3` renders as
  `1666.8333333333333`; rounding is a presentation choice left to the client.
* The in-memory store is intended only for single-process assignment use. It
  has no explicit concurrency control or transactional guarantees, and multiple
  workers would maintain independent stores.
* Nested objects and arrays are not supported field types.
