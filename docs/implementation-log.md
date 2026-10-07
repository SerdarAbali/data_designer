# Implementation log

This log records completed implementation work and phase progress. The
authoritative requirements remain in [MASTER-SPEC.md](../MASTER-SPEC.md);
phase scope and acceptance criteria remain in
[IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md).

## 2026-10-07 — README refresh and user guide

- Rewrote the [README](../README.md) for developers and operators: quick
  start, architecture, repository layout, workflow, migrations, and a
  documentation map. The detailed API route lists moved to
  [api-plan.md](./api-plan.md).
- Added the [User Guide](./user-guide.md) for integration designers: concepts,
  Catalog, Contract Designer, Landscape, Scenarios, a walkthrough tutorial,
  limits, and an FAQ.

## 2026-10-07 — Design-time scenarios and sequence diagrams

- Added a tenant-scoped `scenarios` table (migration `0007_scenarios`) and
  `/api/scenarios` CRUD plus `POST /api/scenarios/evaluate`. Contract-scoped
  and end-to-end scenarios share one document model.
- Contract steps reference an existing contract and phase only. Endpoints are
  derived from the contract, and evaluation reuses the dry-run engine and saved
  phase graphs. Scenarios never modify contracts and add no connectors or
  runtime execution.
- Contract Designer has a **Scenarios** tab, and Landscape has a **Scenarios**
  view. Both offer a generated read-only SVG sequence diagram (lifelines,
  actors, request/response arrows, self-calls, `alt`/`opt`/`loop` frames,
  contract and phase labels, evaluation markers) and a Steps editor with
  create, edit, duplicate, delete, reorder, and wrap/unwrap.
- Clicking a contract message opens that contract at the referenced phase.

Validation: 85 API tests and ruff passed. Frontend vitest, TypeScript, and the
production build passed. The migration was applied locally after a database
backup, and the authenticated UI was checked in the browser.

## 2026-10-04 — Catalog, mapping canvas, and Landscape UI refinement

The UI refinement work preserved the generic System → Object → Field model and
did not add vendor-specific behavior to the core.

- Catalog navigation uses a single-context inspector, with object and field
  tables and focused creation/edit dialogs.
- Integration mapping supports in-canvas field creation, editing and removal,
  field search, auto-mapping, and type mismatch indicators.
- Sample input supports synchronized table/form and raw JSON views, typed
  fields, multiple rows, mock-data generation, and a collapsible input drawer.
- Mapping assistance can insert supported conversion or mapping nodes. Compact
  transformation nodes and an end-to-end sample-row preview expose simulation
  results without putting configuration forms on canvas nodes.
- Landscape topology includes status-aware routes, saved layout, KPI summaries,
  auto-layout, quick actions, a field mapping drill-down drawer, and a hybrid
  view that expands systems into mapped field handles.
- Landscape node sizing, handle placement/visibility, edge layers and curves,
  and mapping-label position/visibility were refined. Direct mappings and
  transformed mappings have distinct labels.

Validation at the end of this refinement: `make check` passed, including 76 API
tests, frontend TypeScript/build checks, and Docker Compose configuration.
Visual inspection of the authenticated UI remains a manual check.

## 2026-10-04 — Bidirectional request/response mapping

- Added `response_graph` and `interaction_type` (`ONE_WAY`,
  `REQUEST_RESPONSE`, `ASYNC_CALLBACK`) while retaining the existing `graph`
  property as the outbound/request graph. Both directions reuse the
  integration's existing source and target objects.
- Added schema migration and transactionally maintained field references for
  response-source and response-target ports. Response graph validation reverses
  source/target object ownership; referenced fields remain protected from
  archive.
- Extended dry-run to run each graph independently and accept optional mock
  response rows keyed by target-object field UUID. Results preserve the existing
  request `rows`/`summary` contract and add per-direction outcomes and response
  summary data.
- Added request/response flow selection in the mapper, a mock response payload
  editor, bidirectional Landscape routes, and separate request and response
  sections in the Landscape field drill-down.
- Updated the data-model, engine, API, and capabilities documents. This adds
  simulation-only mapping behavior; it does not add connectors, external
  execution, or response fetching.

## Current phase — Phase 11: MVP hardening and polish

Phases 0–10 are implemented. Phase 11 is the current in-scope work: close
measurable security, reliability, accessibility, and end-to-end verification
gaps before calling the generic MVP complete.

### Phase 11.1 — Initial API response hardening

- Added `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and
  restrictive `Permissions-Policy` headers to API responses.
- Added a regression assertion for these headers to the health endpoint test.
- `make check` passed: 76 API tests, Ruff, frontend type-check/build, and
  Docker Compose configuration.

This is an initial hardening slice, not completion of Phase 11. The remaining
authorization, migration, API contract, accessibility, end-to-end, and
performance criteria in the implementation plan still require verification.

Phases 12–14 are explicitly post-MVP and are not being started now. This
includes connector architecture; CSV, Excel, and vendor connectors; live
external reads/writes; execution history; scheduling; monitoring; and alerting.
These items require separate approval after MVP acceptance.
