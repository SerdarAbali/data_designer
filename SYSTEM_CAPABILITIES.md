# Data Designer — Technical & Functional System Report

**Repository review date:** 2026-10-04  
**Scope:** Current repository implementation, not future roadmap capabilities.
**How to use the app:** see the [User Guide](./docs/user-guide.md).

## 1. Executive System Overview

### Core purpose

Data Designer is an internal enterprise architecture and data-integration
design tool. It lets users describe systems and their schemas generically,
design field-to-field integration graphs, test mappings against sample data,
and inspect integration relationships and health in a landscape view.

The application addresses two related problems:

1. Keeping a user-maintained, stable-identity catalog of systems, objects, and
   fields without requiring a dedicated application model for each vendor.
2. Designing and reviewing transformations between those schemas, with
   server-side dry runs and visible graph lineage before any future execution
   capability is considered.

The core domain remains `System → Object → Field`. Vendor names and data types
are ordinary metadata values. The current application does not connect to
Salesforce, Meta, Mailchimp, SAP, CSV files, or other external services.

### Target persona

The primary users are enterprise architects, data engineers, and solution or
integration leads who need to catalogue schemas, design mappings, assess
dependencies/conflicts, and communicate data-flow architecture. It is an
internal design and simulation workspace, not currently a production
integration runtime.

## 2. High-Level System Architecture & Tech Stack

### Architecture

The application is a browser-based React client backed by a FastAPI REST API
and PostgreSQL. The frontend does not execute mapping transformations as the
source of truth: it submits saved or draft graphs and sample rows to the API,
where the API validates metadata and calls the isolated transformation engine.

```text
Browser (React/Vite)
    │ REST/JSON
    ▼
FastAPI API ── SQLAlchemy ── PostgreSQL
    │
    └── Pure transformation engine (in-process)
```

Docker Compose defines the PostgreSQL, API, and web development services. The
database is stored in a named Docker volume. There is no separate queue, worker,
connector service, or distributed execution runtime in the current system.

### Frontend stack

- React 19 and TypeScript.
- Vite 6 for development and production bundling.
- `@xyflow/react` (React Flow) for the integration graph editor and enterprise
  topology/field-lineage canvas.
- Local React component state and hooks are used for workspace state; no
  dedicated global state library is configured.
- Styling uses repository CSS files (`web/src/style.css` and
  `web/src/styles/`); Tailwind is not configured.
- The interface includes Catalog, Integrations, and Landscape workspaces,
  together with reusable catalog and landscape components.

### Backend stack

- Python 3.13, FastAPI, Uvicorn, and Pydantic/Pydantic Settings.
- SQLAlchemy 2 for data access and model definitions.
- PostgreSQL 17 with Psycopg; JSON columns use PostgreSQL JSONB where
  supported.
- Alembic manages schema migrations.
- HTTP REST endpoints exchange JSON. There is no GraphQL or gRPC service.
- The transformation engine is Python code accepting graph/field/sample-row
  values; it does not depend on FastAPI, SQLAlchemy, network services, or the
  browser.

### Tooling and delivery

- `make up`, `make down`, and `make logs` operate the Compose development
  services.
- `make check` runs Ruff, the API pytest suite, the frontend TypeScript
  type-check and Vite production build, then validates Docker Compose config.
- `make install` installs backend development requirements and runs `npm ci`.
- No frontend unit-test runner is configured in `web/package.json`; frontend
  automated validation in the current check is TypeScript plus production
  build.
- The latest recorded project check passed 77 API tests and the frontend and
  Compose validation steps. The build emits a Vite warning that React Flow's
  `"use client"` module directive is ignored by the bundler.

## 3. Comprehensive Feature & Functionality Inventory

### Design-time scenarios and sequence diagrams (2026-10-07 addition)

- **Contract Designer → Scenarios tab** for scenarios scoped to one contract.
  It also lists end-to-end scenarios that reference the contract.
- **Landscape → Scenarios view** for multi-contract, end-to-end scenarios.
  Both use one shared document model and API.
- Each scenario includes:
  - Name and category (Happy path, Alternative, or Error).
  - Preconditions and trigger.
  - Participating systems or actors, and contracts.
  - Before- and after-state sample values per system object.
  - Ordered steps. A step is a contract phase message, a self-call, or an
    actor message, and can carry sample and expected values.
  - Nested `alt`, `opt`, and `loop` blocks.
  - Assertions and notes.
- Two views are available:
  - **Sequence Diagram:** generated, read-only SVG. It shows lifelines,
    request and return arrows, self-calls, fragments, contract and phase
    labels, and evaluation markers. Clicking a message opens the referenced
    contract phase.
  - **Steps:** editor with create, edit, duplicate, delete, reorder, and
    wrap or unwrap.
- Evaluation runs the step's sample values through the existing engine and
  the contract's saved mappings.
- Scenarios never copy or modify contract definitions. They are design-time
  only, with no connectors or runtime execution.

### Contract mapping CSV exchange (2026-10-07 addition)

- Active-tab import/export for existing contracts, including unsaved draft
  export independent of matrix filters.
- Versioned UTF-8 CSV with direct mappings or one independent conversion per
  receiver field; scalar settings and fail/skip policies.
- Templates using current field names, delimiter/header detection and manual
  mapping, searchable field resolution, row-level issues, and issue reports.
- Add-only/default, semantic duplicate detection, explicit replace-matching,
  all-or-nothing preview/confirmation, draft application, and Undo import.
- Existing graph Save persists changes with tenant/CSRF/revision protection.
  Other phase graphs, schemas, sample data, and dependencies remain untouched.
- Unsupported advanced/shared/disconnected graphs and unrepresentable settings
  block complete exports or unsafe replacement; no silent partial output.
- 1 MiB / 500-row CSV limits plus existing graph/config bounds. Formula-like
  text is rejected. No catalog creation or business-data CSV connector.
- Frontend conversion, dialog, and editor regression tests cover this feature;
  implementation uses Papa Parse for CSV parsing/serialization.

### Authentication and workspace shell

- Login and logout for the configured internal user.
- Authenticated identity and tenant information are exposed to the frontend.
- Session tokens are stored hashed in the database; login password verification
  uses Argon2; the browser receives HTTP-only session and separate CSRF
  cookies.
- Mutating routes require CSRF verification. Login attempts are rate limited.
- There is no public self-registration or user-administration workflow.

### Catalog and Systems Management

- Create, list, read, update, archive, and restore generic systems.
- Store system name, kind, description, icon, color, visual position, binding
  state, and bounded metadata JSON.
- Create, list, read, update, archive, and restore objects under a system.
- Model fields under objects with stable UUID identity, name, label,
  description, user-defined data type string, required/nullable flags, default
  value, external identifier, ordering, origin, and metadata.
- Enforce tenant scoping and parent ownership in API queries and database
  foreign-key constraints.
- Archive records instead of physically deleting them. Operations reject
  archiving a system, object, or field when active integrations still refer to
  it; systems and objects also archive their descendants as appropriate.
- Rename display names or labels without changing UUID identity, preserving
  graph references.
- The Catalog workspace presents a searchable System → Object → Field tree and
  a single-context inspector. System and object views show child tables and
  focused creation dialogs. Field views edit one field's configuration.
- Metadata can be viewed/edited as JSON. A demo catalog fixture/loader uses the
  same generic catalog model as manually created catalog data and does not
  connect to external systems.

### Integration route management and visual mapping engine

- Create integrations by selecting a generic source system/object and target
  system/object; list, retrieve, update, and archive them.
- Persist a version-1 graph with source/target endpoint nodes, transformation
  nodes, positions, edges, and node configuration.
- Graph field ports reference immutable field UUIDs using `field:<uuid>` IDs;
  labels are presentation metadata, not graph identity.
- The editor dynamically generates source and target field handles from catalog
  object metadata.
- Users can create, edit, and delete endpoint fields from the mapping canvas.
  Deletion warns when graph edges use the field and removes affected active
  graph connections during the UI operation.
- Supports direct field mappings, one-to-one name-based auto-mapping, field
  search, and type-mismatch indicators.
- A type-conversion assist can propose inserting a compatible function or MAP
  node on a newly connected mismatched field edge. The editor rewires the graph
  and can run a draft simulation.
- Graph saves use an expected revision to detect stale concurrent updates.
  Graph validation checks allowed node types, ports, field ownership, topology,
  node configuration, cycles/arity constraints, and size bounds.
- No arbitrary Python/JavaScript or user-authored expression execution is
  supported. Transformations are restricted to the server's allowlisted node
  and function implementations.

#### Supported graph node types

`source`, `target`, `constant`, `fx`, `concat`, `ifelse`, `map`, `coalesce`,
`lookup`, `filter`, and `validate`.

#### Supported `fx` functions

`trim`, `title`, `lower`, `upper`, `e164`, `date`, `toInt`, `toNumber`,
`toString`, `toBoolean`, `parseDate`, and `formatDate`.

Date parsing/formatting and E.164 normalization accept explicit configuration
where required. Node error policies include `fail`, `skip`, and `default`.
Target values are validated against their generic field type metadata, with
supported scalar coercions.

#### Sample data and simulation UI

- Sample payloads are arrays of rows whose values are keyed by source field
  UUID.
- The sample-data editor supports a form/table mode and raw JSON mode with
  bidirectional parsing/synchronization.
- Inputs are selected based on field data type. Users can add and remove rows.
- Mock sample rows can be generated from source field names and types.
- The sample-data area can collapse to leave more canvas space.
- Users can inspect simulation output, per-node traces, target values, row
  outcomes, and errors. A Data Preview drawer shows source values, the
  transformation path, resulting target values, and validation status.
- Simulation is server-side and has no external write or read side effects.
  Results are returned to the client; there is no persisted simulation-run
  history in the current implementation.
- Integrations support `ONE_WAY`, `REQUEST_RESPONSE`, and `ASYNC_CALLBACK`
  interaction types. Request mappings run from the source object to the target
  object; a separately saved response graph maps the existing target object's
  mock response fields back to the existing source object. The mapper switches
  between both graph orientations, and its response payload is simulation-only.
- Dry-run responses preserve the original request result and additionally
  provide request/response outcomes and a separate response summary. The
  Landscape edge indicates bidirectional interaction, and its drill-down shows
  request and response mappings separately.

### Enterprise Landscape View

- **Macro topology:** Systems render as React Flow nodes; each integration is
  represented by a directed route between its endpoint systems. System
  positions are persisted using the system update API.
- **Route status styling:** Draft, healthy, and attention states use distinct
  edge styling and labels. Healthy routes animate. Selecting a route highlights
  it.
- **Hybrid architecture:** Users may switch between **Systems Only** and
  **Hybrid Architecture**, or expand/collapse individual system cards inline.
  Expanded cards expose field names, data-type badges, and connected field
  handles. Field-level edges are derived from saved graph paths and can label
  transformations or direct mappings.
- **KPI summary:** Displays system count, active (non-draft) route count,
  healthy-route percentage among active routes, and unresolved target-field
  conflict count.
- **Auto-layout:** A deterministic graph-direction layout places systems by
  dependency rank and saves their positions.
- **System actions:** Cards include object/route counts and quick actions for
  adding an integration or opening the catalog.
- **Field mapping drill-down:** Selecting a route opens an in-canvas drawer with
  source field/type, transformation chain, target field/type, and dry-run health.
  It can expand/collapse, dismiss with Escape or outside click, and open the
  full mapper.
- **Integration summary:** A collapsible list shows integration status, source
  and target object labels, sample-row counts, reasons, and conflicts.
- Landscape data is assembled in the frontend from catalog, integration, and
  architecture-analysis APIs; there is no dedicated topology-projection API.

### Integrations and data lineage

- Integration dependencies are explicit upstream-to-downstream metadata links.
- Self-dependencies and cycles are rejected; dependencies do not run or schedule
  integrations.
- Architecture analysis identifies multiple active integrations writing to
  the same target object/field using stable object/field IDs and reports all
  active writers.
- Health status is derived from mapping count, conflicts, and upstream status:
  draft indicates no target mappings, attention indicates conflicts or
  unhealthy upstream dependencies, otherwise a mapped route is healthy.
- The UI links conflict and dependency information back to integrations.

## 4. Data Models & API Surface

### Core domain entities

- **Tenant:** Ownership boundary for users and catalog/integration data.
- **User / AuthSession:** Internal account and revocable, expiring authenticated
  sessions; session and CSRF token hashes are persisted.
- **System (`systems`):** Tenant-owned generic application/system metadata and
  saved canvas position.
- **Object (`objects`):** A named/labelled schema entity owned by one system.
- **Field (`fields`):** A named schema attribute owned by one object. Field
  names and types are metadata; UUIDs are the stable identity.
- **Integration (`integrations`):** Source and target system/object references,
  a versioned graph JSON document, sample rows, revision, and optional
  trigger-configuration metadata.
- **IntegrationFieldRef:** Current source/target field references extracted
  from active graphs and used for deletion safeguards and conflict analysis.
- **IntegrationDependency:** Tenant-scoped upstream/downstream dependency edge.
- **Graph nodes and edges:** Embedded versioned JSON graph records rather than
  separate node/edge relational tables. Node types are allowlisted; field ports
  point to field UUIDs.
- **Health metrics:** Derived API analysis values rather than a separate
  persisted health entity.

### Primary API routes

#### Authentication

- `GET /api/auth/csrf` — issue login CSRF token.
- `POST /api/auth/login` — authenticate and create session.
- `POST /api/auth/logout` — revoke session (CSRF-protected).
- `GET /api/auth/me` — current authenticated user and tenant.

#### Catalog

- `GET /api/catalog/systems` — paginated system list.
- `POST /api/catalog/systems` — create system.
- `GET/PATCH/DELETE /api/catalog/systems/{systemId}` — read, update, archive;
  `POST .../{systemId}/restore` restores.
- `GET/POST /api/catalog/systems/{systemId}/objects` — list/create objects.
- `GET/PATCH/DELETE /api/catalog/objects/{objectId}` — read, update, archive;
  `POST .../{objectId}/restore` restores.
- `GET/POST /api/catalog/objects/{objectId}/fields` — list/create fields.
- `GET/PATCH/DELETE /api/catalog/fields/{fieldId}` — read, update, archive;
  `POST .../{fieldId}/restore` restores.

#### Integrations, graph mappings, and simulation

- `GET/POST /api/integrations` — list/create integrations.
- `GET/PATCH/DELETE /api/integrations/{integrationId}` — read, update, archive.
- `PUT /api/integrations/{integrationId}/graph` — save request graph, response
  graph, and interaction type, optionally with name and sample rows, using
  optimistic revision checks.
- `POST /api/integrations/{integrationId}/dry-run` — simulate saved graph or a
  supplied draft graph and rows; request/response routes can include a mock
  `responsePayload` and return separate `requestOutcomes` /
  `responseOutcomes`.
- `GET /api/integrations/architecture` — derived route health, upstream
  dependency details, and target-field conflicts.
- `GET/POST /api/integrations/{integrationId}/dependencies` — list/add
  downstream dependencies for an upstream integration.
- `DELETE /api/integrations/{integrationId}/dependencies/{downstreamId}` —
  remove dependency.

#### Scenarios

- `GET/POST /api/scenarios` — list (`scope`, `integration_id` filters) and
  create design-time scenarios.
- `GET/PUT/DELETE /api/scenarios/{scenarioId}` — read, revision-checked
  update, archive.
- `POST /api/scenarios/evaluate` — evaluate an unsaved scenario document
  against saved contract phase graphs with the dry-run engine. Nothing is
  persisted.

#### Health

- `GET /health` — reports API and database readiness without exposing database
  connection details.

Catalog and integration routes are authenticated and tenant-scoped. Mutations
require the CSRF header. The dry-run API accepts bounded row payloads, optional
graph overrides, and returns row outcomes, target values keyed by field UUID,
structured errors, trace data, and summary counts. Dry-run data is not sent to
external systems.

## 5. Automated Testing & Validation Status

### Latest recorded automated validation

The latest `make check` run passed:

- Ruff checks over API application, tests, and Alembic code.
- **77 API pytest tests** covering authentication, catalog, CLI, engine,
  health, and integration behavior, including bidirectional request/response
  graph simulation and field-reference tracking.
- Frontend TypeScript type-check (`tsc --noEmit`).
- Vite production build.
- Docker Compose configuration validation.

The pytest run reports one upstream Starlette deprecation warning regarding
`anyio.abc.BlockingPortal`; it did not fail validation. Vite also reports that
React Flow's module-level `"use client"` directive is ignored during bundling.

### Test coverage and limitations

- Engine behavior has a focused API-side unit test suite for operations,
  validation, simulation outcomes, and traces.
- API tests cover tenant/auth boundaries, graph references and revision
  conflicts, archive constraints, dry-run behavior, architecture conflicts,
  and dependency health.
- No frontend unit/component test runner is configured, and no quantitative
  coverage percentage was produced by the recorded check.
- `make check` is a local validation target; a separate CI/CD workflow is not
  described as part of the current repository capability.
- The authenticated UI still benefits from a manual browser pass for visual,
  keyboard, responsive, and end-to-end verification.

## Current scope boundary

The present application is a generic catalog, graph designer, and dry-run
simulation tool. CSV/Excel import, vendor connectors, credentialed external
connections, real fetch/transform/write execution, persisted run history,
scheduling, monitoring, and alerting are later-stage capabilities and are not
implemented by the current system.
