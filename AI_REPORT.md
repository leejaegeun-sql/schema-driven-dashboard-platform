# AI Report

## Tools used

**Claude Code (Opus 5)** in VS Code for analysis, implementation, tests and
documentation; **headless Chrome over the DevTools Protocol** to verify the UI.

## Example prompts

1. _"Read round_1_assignment.pdf completely. Do not create or edit any files
   yet. List the mandatory requirements, deliverables, evaluation criteria and
   the ambiguities needing an explicit assumption — how a dashboard is
   associated with a schema, whether ingestion is atomic, duplicate
   registration, empty datasets, error-response consistency. Stop after the
   analysis."_
2. _"Use 422 rather than 400 for semantically invalid but readable requests;
   keep 409 for duplicate names, 404 for missing references; override
   RequestValidationError so pydantic errors use the same envelope."_
3. _"Cover every agreed positive and negative behaviour."_

Settling the ambiguities before writing code kept the implementation from
drifting.

## One suggestion I accepted

The assignment's example dashboard configuration has no schema reference. The
model pointed out that `GET /dashboard/{name}` then cannot know which rows to
read, and proposed a required top-level `schema` key plus validation of each
view field against that schema at registration time.

I accepted both. The deviation is deliberate and documented: without it the
platform cannot serve two use cases at once. Eager validation makes `sum` over a
string field a 422 at configuration time, not a broken view at read time.

## One suggestion I rejected

It recommended the conventional treatment of nulls — permit explicit `null` for
optional fields, reject it only for required ones. I rejected it: two spellings
of "no value" means two code paths in validation, aggregation and rendering, for
no gain. The rule is now one line — an explicit null is never accepted. I also
replaced its `400` for validation failures with `422`.

## How I validated the solution

- **184 pytest tests** with warnings treated as errors: type checking
  (including the `bool`-is-not-a-`number` trap), unknown and null fields, atomic
  rollback, the 404/409/422 paths, view validation, the empty-dataset contract.
- **Registry tests** failing if a declared view type or aggregation is left
  unimplemented.
- **A live curl walkthrough** running the trade and customer use cases on one
  process, and **the real UI in headless Chrome**, scripted through all four
  steps with zero console errors.
- **Clean virtual environments** built from `requirements.txt` alone. A
  dependency-compatibility trial moved the project onto the current FastAPI
  stack and removed one of its two warning filters.
