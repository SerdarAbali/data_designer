# Data Designer — Implementation Plan

## Authority, scope, and planning assumptions

The supplied [MASTER-SPEC.md](../MASTER-SPEC.md) is the authoritative product and technical specification for this project. This plan translates its roadmap into tasks and records proposed defaults for details it leaves open in [data-model.md](./data-model.md), [engine-spec.md](./engine-spec.md), and [api-plan.md](./api-plan.md). Those defaults do not require a separate product specification; resolve only genuinely open decisions at the relevant task gate. Do not infer that vendor-specific behavior belongs in the core.

This document is a plan only. The current workspace has no Git metadata; the authoritative master spec is at the repository root. Phase 0 establishes the repository layout while preserving and continuing to use that file as the source of truth; implementation is not gated on creating a separate product specification.

## Product invariant

The core must represent `System → Object → Field` as user-managed generic data. Salesforce, Meta, Mailchimp, SAP, CSV, Excel, and future sources are values/bindings handled by fixtures or adapters—not core entity classes, fixed catalogs, or special execution branches. A fresh catalog must be usable without a connector or application-code change.

## Proposed phase order

The sequence below preserves the roadmap's “generic core before connectors” rule. Authentication precedes tenant-scoped data; the catalog precedes integrations; graph validation and the engine precede simulation; API simulation precedes live UI simulation. Hardening is moved ahead of connector/execution work so that non-MVP integrations do not destabilize the generic MVP.

| Phase | Name | Exit gate |
|---|---|---|
| 0 | Environment and repository bootstrap | ARM64-compatible toolchain, Git repository, documented commands, canonical docs layout |
| 1 | Application skeleton, Docker, PostgreSQL | Browser → React/Vite → FastAPI → PostgreSQL works via Compose |
| 2 | Authentication and tenant boundary | Secure login/logout; protected, tenant-scoped APIs |
| 3 | Dynamic System/Object/Field catalog | Arbitrary catalog CRUD works with no code changes |
| 4 | Integration model and graph schema | Generic integrations save a validated, versioned graph |
| 5 | Pure transformation engine | Engine runs without web, database, or filesystem dependencies |
| 6 | Dry-run/simulation API | API returns bounded results, counts, errors, and traces |
| 7 | System/Object/Field designer UI | A user can build a catalog from an empty database |
| 8 | Visual integration editor | Dynamic field ports, graph editing, save, and API-backed simulation work |
| 9 | Enterprise landscape | Systems/integrations display and navigate with persisted positions |
| 10 | Conflict and dependency analysis | Conflicts, cycles, health, and upstream warnings are explained |
| 11 | MVP hardening and polish | Security, quality, accessibility, performance, and manual gates pass |
| 12 | Connector architecture (post-MVP) | Optional adapter boundary, only when a connector is approved |
| 13 | Future connectors (post-MVP) | CSV, Excel, and vendor connectors are separate optional milestones |
| 14 | Real execution, scheduling, and monitoring (post-MVP) | Separately approved capabilities; never prerequisites for MVP |

Phases 0–11 define the generic MVP. Phases 12–14 are explicitly post-MVP and do not block MVP acceptance or use.

## Current implementation status

Phases 0–10 are implemented. The recent catalog, integration-canvas, and
Landscape visual refinements are recorded in
[implementation-log.md](./implementation-log.md). Continue with Phase 11's
bounded MVP hardening and end-to-end verification tasks.

Do not start Phases 12–14 as part of the current work. Connector architecture,
CSV/Excel/vendor integrations, real external execution, scheduling, monitoring,
and alerting remain post-MVP and require separate approval.

## Cross-cutting implementation rules

- Use PostgreSQL UUID identities and tenant-scoped foreign keys; display names and labels are never graph identity.
- Use the master-spec graph field `version` (initially `1`); an optional current save revision is only for optimistic concurrency.
- Validate every graph server-side; React Flow is a view/editor, not the validation or execution authority.
- Keep engine inputs/outputs plain typed values; do not import FastAPI, SQLAlchemy, PostgreSQL, React, HTTP, or filesystem APIs into the engine package.
- Store sample data only as bounded, user-controlled data; never use it as executable code or silently log its values.
- Use migrations for schema changes, strict TypeScript and Python typing, and targeted automated tests at every task gate.
- All application images and dependencies must be verified for `linux/arm64`; pin supported image/dependency versions rather than relying on floating `latest` tags.
- Any external connector maps into the generic catalog and can be absent without disabling the core application.
- Work one task at a time. Run its targeted tests and the repository-wide check, manually verify its acceptance criterion, then commit before advancing.

## Phase 0 — Environment and repository bootstrap

### Task 0.1 — Establish the documented ARM64 development baseline

**Objective:** Reconcile the supplied files and establish a reproducible host/repository baseline.  
**Why it exists:** Docker/Compose and Node.js are currently unavailable, and the workspace is not a Git repository. The authoritative `MASTER-SPEC.md` currently resides at the repository root.  
**Files/components likely affected:** `README.md`, `docs/host-environment.md`, `docs/assumptions.md`, `docs/blockers.md`, `docs/dependencies.md`, `.gitignore`, repository directories. Preserve the root `MASTER-SPEC.md`; do not require a separate product-spec document.  
**Database changes:** None.  
**API changes:** None.  
**Frontend changes:** None.  
**Tests required:** Verify `git`, `docker`, `docker compose`, Python, and Node.js versions; verify ARM64 image availability and a clean repository check.  
**Dependencies:** None.  
**Acceptance criteria:** A Git repository and expected `docs/`, `api/`, `web/`, and `fixtures/` layout exist; setup/check commands and host facts are documented; the root `MASTER-SPEC.md` remains authoritative and is preserved; all tools needed by the next phase work on ARM64.  
**Potential risks:** Installing host packages requires deliberate approval/privilege; Debian 13 is reported by this host, but Raspberry Pi OS identity is not established by the inspected OS metadata. Do not modify SSH, boot, Tailscale, or OS configuration as part of application bootstrap.

## Phase 1 — Application skeleton, Docker, and PostgreSQL

### Task 1.1 — Create the Compose application skeleton and health path

**Objective:** Start a minimal React/Vite frontend, FastAPI backend, and PostgreSQL service.  
**Why it exists:** All later vertical slices need a working, reproducible application boundary.  
**Files/components likely affected:** `docker-compose.yml`, `docker-compose.dev.yml`, `api/app/main.py`, `api/app/config.py`, `api/app/db.py`, `web/`, `Makefile`, `.env.example`.  
**Database changes:** PostgreSQL service, named persistent volume, readiness/health check; no domain tables.  
**API changes:** `GET /health` reports API and database readiness without disclosing secrets.  
**Frontend changes:** Minimal Vite/React entry point and API connectivity check.  
**Tests required:** Container health/startup tests, database-unavailable health test, frontend build/smoke test.  
**Dependencies:** Task 0.1.  
**Acceptance criteria:** One documented command starts ARM64-compatible `db`, `api`, and `web`; health distinguishes API-up from database-unavailable; persistent volume survives container recreation.  
**Potential risks:** Weak health checks can report readiness prematurely; development and production settings must not expose database ports or credentials unintentionally.

### Task 1.2 — Establish migrations, checks, and CI baseline

**Objective:** Add repeatable schema migration, lint/type-check, test, and local check workflows.  
**Why it exists:** Every later phase needs a consistent, verifiable gate.  
**Files/components likely affected:** `api/alembic.ini`, `api/alembic/`, `api/pyproject.toml`, `web/package.json`, lint/test configuration, `Makefile`, CI workflow.  
**Database changes:** Alembic-managed empty initial schema; migration upgrade/downgrade smoke tests.  
**API changes:** None beyond baseline health.  
**Frontend changes:** TypeScript strict-mode build and lint/check commands.  
**Tests required:** Fresh database migration, migration replay, Python unit-test discovery, frontend type-check/build, `make check`.  
**Dependencies:** Task 1.1.  
**Acceptance criteria:** A clean checkout can install locked dependencies, migrate an empty database, and pass one documented check command.  
**Potential risks:** ARM64 wheel/native package gaps; Python 3.13 compatibility must be verified and the supported version pinned rather than assumed.

## Phase 2 — Authentication and tenant boundary

### Task 2.1 — Add tenant and user persistence

**Objective:** Represent the initial single-tenant/single-user deployment while keeping data tenant-scoped.  
**Why it exists:** The catalog and integrations carry `tenant_id`; ownership must be defined before those tables exist.  
**Files/components likely affected:** `api/app/models/tenant.py`, `api/app/models/user.py`, migration, auth schemas/repository.  
**Database changes:** One internal tenant/workspace boundary, one provisioned user, and server-side sessions; unique normalized user email; tenant-scoped domain rows.  
**API changes:** Internal identity/session DTOs only.  
**Frontend changes:** None.  
**Tests required:** Tenant/user creation, normalized uniqueness, foreign-key behavior, session persistence and expiry.  
**Dependencies:** Task 1.2.  
**Acceptance criteria:** A provisioned internal user resolves to one lightweight tenant/workspace boundary for data isolation. No multi-user collaboration, roles, invitations, organizations, SaaS administration, or signup flow is introduced.  
**Potential risks:** Bootstrap credentials must not be committed or printed; email normalization and cookie/session deployment behind TLS need explicit configuration.

### Task 2.2 — Implement secure session authentication

**Objective:** Provide login, logout, current-user, protected routes, and login throttling.  
**Why it exists:** Domain APIs must never be anonymously accessible or rely on frontend-only authorization.  
**Files/components likely affected:** `api/app/auth/`, auth routes/dependencies, `api/app/config.py`, frontend login/session client.  
**Database changes:** Hashed opaque session tokens with expiry/revocation; optional login-throttle state if selected over a process-local limiter.  
**API changes:** `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`; shared authenticated-tenant dependency.  
**Frontend changes:** Login/logout flow, protected application shell, handling expired sessions.  
**Tests required:** Argon2id success/invalid password, logout revocation, protected endpoint, tenant context, rate limit, CSRF, secure cookie attributes.  
**Dependencies:** Task 2.1.  
**Acceptance criteria:** Unauthenticated clients cannot access protected APIs; logout invalidates the server session; password hashes are Argon2id; cookies are HttpOnly, Secure in HTTPS deployment, SameSite-protected, and mutating cookie-auth requests are CSRF-protected.  
**Potential risks:** In-memory rate limits do not survive restarts or multiple API replicas; trusted proxy configuration, CSRF tokens, session rotation, and secret provisioning must be tested.

## Phase 3 — Dynamic System/Object/Field catalog

### Task 3.1 — Add generic catalog schema and migration

**Objective:** Persist arbitrary systems, objects, and fields without vendor-specific models.  
**Why it exists:** This is the required generic foundation and the first architectural gate.  
**Files/components likely affected:** `api/app/models/{system,object,field}.py`, migration, catalog domain types, `docs/data-model.md`.  
**Database changes:** Tenant-scoped `systems`, `objects`, and `fields`; parent FKs and ordering; UUID IDs; free-form system `kind`; generic data type values; `metadata` JSONB; archive timestamps; unique active names scoped to parent.  
**API changes:** None in this task.  
**Frontend changes:** None.  
**Tests required:** Migration constraints, cross-tenant FK rejection, arbitrary kind/name persistence, field ordering, supported generic data types.  
**Dependencies:** Task 2.2.  
**Acceptance criteria:** System → Object → Field is represented through generic rows; names are display values, not identity; schema contains no Salesforce/Meta/Mailchimp/SAP-specific entity or enum.  
**Potential risks:** Redundant `tenant_id` columns require composite FKs/constraints; JSON metadata needs size/shape limits; data types must be generic and documented, with an opaque extension path rather than vendor-specific branches.

### Task 3.2 — Implement catalog CRUD, validation, and safe archive

**Objective:** Expose tenant-scoped catalog CRUD with predictable delete semantics.  
**Why it exists:** The catalog must be manageable by API and later by UI, while preserving integration references.  
**Files/components likely affected:** Catalog schemas, services, routes, authorization dependencies, generated API types.  
**Database changes:** Use the Task 3.1 schema; add indexes or constraints revealed by API access patterns.  
**API changes:** CRUD/list/detail routes for systems, objects, fields; ordering and pagination; conflict/error response schema.  
**Frontend changes:** None.  
**Tests required:** CRUD and validation matrix, arbitrary names/kinds/types, ordering, tenant isolation, archive/restore and active-name conflict behavior. Referenced-item conflict tests belong to Task 4.2, when integrations and graph references exist.  
**Dependencies:** Task 3.1.  
**Acceptance criteria:** An authenticated user creates a wholly new arbitrary hierarchy through the API without code changes; system/object/field names may be changed without changing IDs; invalid hierarchy or cross-tenant access is rejected.  
**Potential risks:** Bulk child operations and concurrent archive/update require transactions. Phase 3 retains archived IDs; Task 4.2 must add transactional integration-reference checks and safe same-tenant conflict details without leaking another tenant's data.

### Task 3.3 — Add generic, idempotent demo fixtures

**Objective:** Populate illustrative Salesforce/Meta/Mailchimp/SAP-like examples as ordinary catalog data.  
**Why it exists:** Demonstrations must not create a hidden vendor-specific domain path.  
**Files/components likely affected:** `fixtures/demo/`, fixture loader/CLI, test fixtures, setup docs.  
**Database changes:** Inserts rows through the same catalog services/schema; no fixture-only tables.  
**API changes:** No public seed endpoint; optional local-only command.  
**Frontend changes:** None.  
**Tests required:** Idempotent repeated loading, clean-database load, arbitrary non-demo catalog still works, fixture rows use the same model.  
**Dependencies:** Task 3.2.  
**Acceptance criteria:** Demo data uses ordinary `System`, `Object`, and `Field` rows with generic `kind`, `origin`, and metadata; removing fixtures changes no application code.  
**Potential risks:** Seed accounts and real personal data must never be included; a development seed command must not overwrite user data.

## Phase 4 — Integration model and graph schema

### Task 4.1 — Add integrations, graph persistence, and dependency records

**Objective:** Persist source/target object integrations and a versioned graph document.  
**Why it exists:** Mapping and simulation need a generic object-to-object integration boundary.  
**Files/components likely affected:** Integration/dependency models, migration, graph schema module, `docs/data-model.md`, `docs/api-plan.md`.  
**Database changes:** `integrations` with tenant, source/target system+object references, name/description/trigger config, bounded sample rows, a current save revision, and JSONB graph using the master-spec `version` property; integration dependency edges. No graph-history table in MVP.  
**API changes:** Integration CRUD/list/detail and graph save payload contract.  
**Frontend changes:** None.  
**Tests required:** Same-tenant endpoint constraints, sample-row persistence/limits, invalid endpoints, optimistic concurrency conflict, dependency uniqueness.  
**Dependencies:** Task 3.2.  
**Acceptance criteria:** Any active source object may map to any active target object; graph JSON uses `version: 1`; a lightweight current revision prevents overwriting a concurrent edit. Graph history is not required.  
**Potential risks:** JSONB alone cannot enforce graph references; endpoint system/object IDs must not disagree.

### Task 4.2 — Validate graphs and maintain field references transactionally

**Objective:** Define and enforce graph topology, stable field ports, node configuration, and catalog references.  
**Why it exists:** Invalid or stale graphs must not reach the engine or be saved as valid integrations.  
**Files/components likely affected:** Graph schemas/validator, integration service, `integration_field_refs` model/migration, catalog archive service.  
**Database changes:** Keep graph field references canonical by UUID. A current-reference index/table may be used only to support required deletion checks and conflict visibility; do not build graph-history infrastructure.  
**API changes:** Graph validation errors with stable codes and node/edge/port paths.  
**Frontend changes:** None.  
**Tests required:** Allowed node types, port direction/compatibility, field ownership and active status, duplicate target-field mapping, cycles, malformed configs, stale revision, archive conflict, transactional rollback.  
**Dependencies:** Task 4.1.  
**Acceptance criteria:** Server validates the graph and its field references before save; only allowlisted node types and valid field UUID ports are accepted. Safe current-revision compare-and-swap prevents lost updates.  
**Potential risks:** Graph validators can diverge from editor rules; stale catalog metadata and concurrent field archival require transaction isolation/locking and explicit conflict responses.

## Phase 5 — Pure transformation engine

### Task 5.1 — Freeze the engine boundary and normalized data contract

**Objective:** Define engine input/output DTOs independent of web, persistence, and UI libraries.  
**Why it exists:** Transformation execution must be reusable and independently testable.  
**Files/components likely affected:** `api/app/engine/` or a separately importable `engine/` package, `docs/engine-spec.md`, fixture/golden format.  
**Database changes:** None.  
**API changes:** None; API adapters translate to/from engine DTOs.  
**Frontend changes:** None.  
**Tests required:** Import-boundary test proving engine imports no FastAPI/SQLAlchemy/database/UI/filesystem modules; DTO validation and JSON round-trip.  
**Dependencies:** Task 4.2.  
**Acceptance criteria:** A pure function accepts bounded rows, resolved field metadata, and an already validated graph; it returns deterministic row outcomes, target values, errors, counts, and traces.  
**Potential risks:** Passing ORM objects or database lookups into engine breaks the boundary; define null, missing, coercion, date/time, decimal, and error semantics before implementation.

### Task 5.2 — Implement deterministic transformation functions and nodes

**Objective:** Implement the MVP graph nodes and `fx` functions in the roadmap.  
**Why it exists:** Mappings need useful transformation behavior without arbitrary user code.  
**Files/components likely affected:** Engine node/function registry, typed values, `docs/engine-spec.md`.  
**Database changes:** None.  
**API changes:** None.  
**Frontend changes:** None.  
**Tests required:** Unit and golden tests for `constant`, `fx`, `concat`, `ifelse`, `map`, `coalesce`, `lookup`, `filter`, `validate`; `trim`, `title`, `lower`, `upper`, `e164`, `date`; `fail`, `skip`, `default` policies.  
**Dependencies:** Task 5.1.  
**Acceptance criteria:** Every supported operation is allowlisted, typed, deterministic, documented, and has defined invalid-input behavior; no Python/JavaScript expression execution or network access exists.  
**Potential risks:** Locale-sensitive text/date parsing, E.164 interpretation, coercion, lookup semantics, and missing/null distinction need fixed semantics and explicit validation errors.

### Task 5.3 — Add row execution, outcomes, errors, and node trace

**Objective:** Execute validated graphs over sample rows and return explainable per-row results.  
**Why it exists:** Dry runs and the editor need trustworthy, inspectable execution results.  
**Files/components likely affected:** Engine graph executor, trace/result DTOs, golden/property tests.  
**Database changes:** None.  
**API changes:** None.  
**Frontend changes:** None.  
**Tests required:** `ok`/`skipped`/`failed` outcomes, every node's trace, row isolation/error policies, deterministic repeated execution, property-based graph/value invariants, golden fixtures.  
**Dependencies:** Task 5.2.  
**Acceptance criteria:** Each evaluated node has a trace entry linked to row/node/port; outputs are keyed by target field UUID; errors are structured and do not conceal failed rows.  
**Potential risks:** Trace size can exceed output size; define truncation/limits while preserving accurate counts and explicit truncation indicators.

## Phase 6 — Dry-run/simulation API

### Task 6.1 — Expose bounded simulation endpoint

**Objective:** Run a saved or editor-draft integration through the engine via authenticated API.  
**Why it exists:** The frontend must not execute transformations locally, and simulation is required for MVP.  
**Files/components likely affected:** Dry-run route/service, request/response schemas, API docs, API tests.  
**Database changes:** None required; read integration/catalog metadata. Persisted run history is deferred.  
**API changes:** `POST /api/integrations/{id}/dry-run`; rows plus optional validated unsaved graph override and expected saved revision; response with per-row outcomes, summary counts, target values keyed by field ID, node traces, structured errors.  
**Frontend changes:** None in this task.  
**Tests required:** Saved/draft graph, validation error, auth/tenant isolation, row/byte/graph limits, counts, trace correlation, stale revision, no sample-data logging.  
**Dependencies:** Task 5.3 and Task 4.2.  
**Acceptance criteria:** API returns the engine contract without reimplementing transformations; request bounds and explicit timeout/size failures are enforced; dry run has no external side effects.  
**Potential risks:** Synchronous CPU work can block the API; enforce tight limits, measure latency, and move to a job model only if measured workload requires it.

## Phase 7 — System/Object/Field designer UI

### Task 7.1 — Build system and object designers

**Objective:** Let a user create, edit, reorder, inspect, and archive systems/objects from the UI.  
**Why it exists:** The generic catalog should be useful before connectors exist.  
**Files/components likely affected:** `web/src/features/catalog/`, API client/types, routing, reusable forms/dialogs.  
**Database changes:** None beyond Phase 3.  
**API changes:** Use catalog CRUD/list endpoints; handle validation and conflict responses.  
**Frontend changes:** System designer and object list/detail/editor, empty/loading/error states, saved positions/order.  
**Tests required:** Component tests for CRUD and errors; browser/e2e test creating arbitrary system/object names and kinds.  
**Dependencies:** Task 3.2 and Task 2.2.  
**Acceptance criteria:** No hard-coded system or object catalog; arbitrary user-defined structures persist and reload; archive conflicts are actionable.  
**Potential risks:** Optimistic UI may hide failed writes; use server-confirmed state and visible save/error feedback.

### Task 7.2 — Build dynamic field designer

**Objective:** Create and edit fields, data types, requirements, metadata, and ordering.  
**Why it exists:** Integration availability depends on editable, database-backed field metadata.  
**Files/components likely affected:** Catalog field feature/forms, generated types, field query/cache invalidation.  
**Database changes:** None beyond Phase 3.  
**API changes:** Use field CRUD/order/archive endpoints.  
**Frontend changes:** Dynamic field list/editor with generic data-type selector, required/nullable/default and metadata controls.  
**Tests required:** Field CRUD and reorder tests; query refresh after field change; arbitrary field labels/names; referenced-field archive conflict.  
**Dependencies:** Task 7.1 and Task 3.2.  
**Acceptance criteria:** Adding, renaming, or reordering fields requires no frontend code change and is reflected in subsequent integration-design metadata queries.  
**Potential risks:** Cached schema can create stale graph ports; define invalidation/refetch behavior and show archived/broken references clearly.

## Phase 8 — Visual integration editor

### Task 8.1 — Render source/target with dynamic React Flow ports

**Objective:** Generate source output and target input ports from catalog metadata.  
**Why it exists:** Field mappings must adapt to arbitrary database-backed schemas.  
**Files/components likely affected:** `web/src/features/integrations/editor/`, `@xyflow/react` custom nodes, field metadata hooks.  
**Database changes:** None.  
**API changes:** Use integration detail and object field endpoints.  
**Frontend changes:** Source/target node handles use immutable field UUIDs as port identity and current labels only as display text; reconnect/refetch when catalog changes.  
**Tests required:** Dynamic port generation, stable port IDs after rename/reorder, newly-added fields appear without a bundle/code change, stale/archived port handling.  
**Dependencies:** Task 7.2 and Task 4.2.  
**Acceptance criteria:** Port set is derived only from selected object metadata; no field-name-based graph identity or hard-coded vendor fields exist.  
**Potential risks:** React Flow handle IDs must remain stable across rerenders; async metadata changes must not silently mutate a saved graph.

### Task 8.2 — Edit, configure, validate, and persist graph

**Objective:** Add allowlisted transformation nodes, inspectors, graph validation feedback, and revision-safe save.  
**Why it exists:** Users need to create integrations visually, with server validation remaining authoritative.  
**Files/components likely affected:** Editor canvas, node inspector/config forms, graph state/schema adapter, save hooks.  
**Database changes:** Uses graph/revision persistence from Phase 4.  
**API changes:** Graph save/validate calls with expected revision; actionable validation errors.  
**Frontend changes:** Add constant/fx/concat/ifelse/map/coalesce/lookup/filter/validate nodes; connect and configure; unsaved/saving/conflict states.  
**Tests required:** Graph serialization compatibility, node config validation, optimistic concurrency conflict, save/reload round trip, keyboard/accessibility basics.  
**Dependencies:** Task 8.1 and Task 4.2.  
**Acceptance criteria:** Editor graph round-trips through versioned API unchanged; stale writes are surfaced, not overwritten; unsupported node configs cannot be marked saved.  
**Potential risks:** Frontend/backend graph schema drift; generate or contract-test shared schemas and maintain explicit migrations for future graph versions.

### Task 8.3 — Add debounced API simulation and trace inspector

**Objective:** Show simulation results and selected-row per-node traces in the editor.  
**Why it exists:** Users need rapid feedback without moving engine execution into the browser.  
**Files/components likely affected:** Editor simulation panel, API hooks, trace/results views.  
**Database changes:** None.  
**API changes:** Uses Phase 6 dry-run endpoint; submit draft graph after approximately 300 ms idle.  
**Frontend changes:** Debounce/cancel stale requests, counts, target values, row selection, node trace, explicit run/error/limit states.  
**Tests required:** Debounce behavior, stale response suppression, trace-to-node selection, failed/skipped rows, server error display.  
**Dependencies:** Task 8.2 and Task 6.1.  
**Acceptance criteria:** Transformations execute only on the server; latest draft results replace older responses, and trace values correlate to selected row/node.  
**Potential risks:** Frequent large requests and sensitive sample data; cancellation, row limits, privacy-aware logging, and clear loading indicators are mandatory.

## Phase 9 — Enterprise landscape

### Task 9.1 — Build persisted system/integration landscape

**Objective:** Visualize systems as nodes and integrations as directed edges.  
**Why it exists:** Users need an enterprise-level view above individual field mappings.  
**Files/components likely affected:** Landscape page, React Flow system/integration nodes, position API/hooks.  
**Database changes:** Tenant-scoped system positions already defined; add only if the model lacks a versioned position field.  
**API changes:** Landscape projection endpoint and position update endpoint if existing catalog APIs are insufficient.  
**Frontend changes:** Zoom/pan, system nodes, integration edges/labels/status/row counts, saved positions, navigation to editor.  
**Tests required:** Projection tests, position persistence/reload, tenant isolation, navigation, empty-state behavior.  
**Dependencies:** Task 7.1, Task 4.1, Task 8.2.  
**Acceptance criteria:** Any generic systems and integrations appear correctly; positions persist; selecting an edge opens the matching integration.  
**Potential risks:** Large landscapes affect rendering; use bounded queries and measured virtualization/visibility strategies rather than premature complexity.

## Phase 10 — Conflict and dependency analysis

### Task 10.1 — Detect target-field conflicts

**Objective:** Report multiple active integrations writing to the same target object/field.  
**Why it exists:** This is the roadmap's first architecture-intelligence feature.  
**Files/components likely affected:** Analysis service/query, landscape/editor warning UI, API schemas.  
**Database changes:** Index target field-reference lookup by tenant, object, and field.  
**API changes:** Tenant-scoped `GET /api/integrations/architecture` includes all active writers and stable object/field IDs.  
**Frontend changes:** Conflict markers and drill-down to integrations/field in landscape and editor.  
**Tests required:** Single/multiple writer cases, archived integration/reference handling, tenant isolation, field rename stability.  
**Dependencies:** Task 4.2 and Task 9.1.  
**Acceptance criteria:** Conflict identity uses stable object/field IDs; warning identifies all active integrations and is absent for one writer.  
**Potential risks:** Graph writes and analysis reads racing; define transactionally current reference rows and label analysis freshness.

### Task 10.2 — Validate integration dependencies and health

**Objective:** Detect self-dependencies/cycles and derive draft/attention/healthy status plus upstream warnings.  
**Why it exists:** Integration health must explain upstream and graph problems, not merely decorate the landscape.  
**Files/components likely affected:** Dependency service/validator, status projection, API and landscape/editor status UI.  
**Database changes:** Dependency edge indexes and constraints as required.  
**API changes:** Dependency CRUD/analysis and health fields.  
**Frontend changes:** Status legend, upstream warning details, cycle/conflict navigation.  
**Tests required:** Self-edge, multi-edge cycle, healthy/draft/attention rules, unhealthy upstream propagation, tenant boundaries.  
**Dependencies:** Task 10.1 and Task 9.1.  
**Acceptance criteria:** Self-dependencies and cycles are rejected. Status is deterministic: `draft` means zero mapped target fields; `attention` means a target-field conflict, an unhealthy upstream, or an unanalysable dependency cycle; otherwise a mapped integration is `healthy`. A downstream integration with an unhealthy upstream is `attention`, including when it is otherwise a draft. Each warning has an explanatory reason; dependency metadata does not execute or schedule integrations.  
**Potential risks:** Status rules can become opaque or expensive; use bounded/current tenant data and iterative dependency analysis rather than unbounded recursion.

## Phase 11 — MVP hardening and polish

### Task 11.1 — Security, reliability, accessibility, and UX hardening

**Objective:** Close cross-cutting MVP gaps in API/UI behavior and operational safety.  
**Why it exists:** The roadmap makes stability, auth, validation, empty states, and accessibility an MVP exit gate.  
**Files/components likely affected:** API/auth/catalog/integration modules, frontend forms/editor/landscape, logging/configuration, deployment documentation.  
**Database changes:** Review migration safety and backup/restore procedure; only add schema changes with tested migrations.  
**API changes:** Consistent validation/error envelopes, secure headers, CORS/host allow-lists, rate limits, request limits, redacted logs.  
**Frontend changes:** Loading/empty/error/confirmation/unsaved/saving/broken-mapping states, keyboard and screen-reader accessibility, responsive layout.  
**Tests required:** Security regression tests, authorization matrix, migration upgrade test, API contract tests, accessibility checks, frontend integration tests.  
**Dependencies:** Phases 2–10.  
**Acceptance criteria:** No unhandled/silent failure paths; all endpoints enforce tenant ownership; no secrets/sample rows in logs; strict type/lint/test checks pass.  
**Potential risks:** “Polish” can expand without exit criteria; keep a severity-ranked defect list and require explicit sign-off for deferred risks.

### Task 11.2 — Performance and end-to-end MVP verification

**Objective:** Verify realistic schema/graph/integration workloads and the empty-database user journey.  
**Why it exists:** Phase gates require evidence of complete user value, not isolated component tests.  
**Files/components likely affected:** Test fixtures, load/performance tests, deployment/runbook docs, targeted performance fixes.  
**Database changes:** Index review from measured query plans; no speculative denormalization.  
**API changes:** Verify pagination and configured dry-run bounds.  
**Frontend changes:** Verify large-schema/graph interaction and avoid measured unnecessary rerenders.  
**Tests required:** End-to-end create two arbitrary systems/objects/fields → integrate → transform → simulate → inspect trace → landscape/conflicts/dependencies; ARM64 Compose smoke test; measured repeated dry-run and representative graph limits.  
**Dependencies:** Task 11.1.  
**Acceptance criteria:** Roadmap MVP definition passes from an empty database with zero connectors; known scale limits and test results are documented.  
**Potential risks:** Host capacity is finite (4 ARM cores, about 8 GiB RAM); performance thresholds must reflect actual target use and avoid claiming unmeasured scalability.

## Phase 12 — Connector architecture

### Task 12.1 — Define isolated connector/discovery contracts

**Objective:** Specify how adapters discover/bind generic metadata without changing core domain or engine.  
**Why it exists:** Future connectors should populate/bind the catalog while connectors remain optional.  
**Files/components likely affected:** `api/app/connectors/` protocol/registry boundary, connector contract docs, adapter tests.  
**Database changes:** Optional connection/binding records and external identity mappings only after threat/data-retention review; do not add vendor columns to generic entities.  
**API changes:** Authenticated connector capability/discovery routes only if a concrete adapter needs them.  
**Frontend changes:** None required in this architecture-only task.  
**Tests required:** Contract tests with a fake adapter, generic catalog unchanged, core starts with no adapter registered, discovery reconciliation idempotency.  
**Dependencies:** Post-MVP; not a dependency of Task 11.2 or MVP acceptance.  
**Acceptance criteria:** If connector work is approved after MVP, the protocol separates discovery/binding from generic catalog and engine code.  
**Potential risks:** Premature plugin/marketplace design; no connector registry or plugin infrastructure is required for MVP.

## Phase 13 — Future connectors

### Task 13.1 — CSV discovery/import adapter (post-MVP)

**Objective:** Read CSV headers/sample rows and bind them to generic system/object/field records.  
**Why it exists:** CSV is the first real connector in the roadmap and validates adapter boundaries.  
**Files/components likely affected:** CSV adapter, upload/import service, isolated parsing tests, operator docs.  
**Database changes:** Generic catalog rows plus import/binding metadata; raw file retention only if explicitly needed and bounded.  
**API changes:** Upload/inspect/confirm-import routes with authentication, size limits, and explicit lifecycle.  
**Frontend changes:** Optional import wizard; not required to make catalog/editor usable.  
**Tests required:** Encoding/delimiter/header edge cases, size limits, malformed inputs, tenant isolation, idempotent mapping, no engine special case.  
**Dependencies:** Task 12.1, only if CSV connector work is approved after MVP.  
**Acceptance criteria:** Imported columns become generic fields; CSV-derived sample rows use the same dry-run contract; core works when the adapter is disabled.  
**Potential risks:** Formula injection on later export, malicious/oversized inputs, PII retention, and ambiguous headers.

### Task 13.2 — Excel connector (post-MVP)

**Objective:** Map workbook/worksheet/column metadata into the generic model.  
**Why it exists:** Excel is a separately specified future connector, not an MVP requirement.  
**Files/components likely affected:** Optional Excel adapter, isolated parsing tests, operator documentation.  
**Database changes:** Generic catalog rows only, unless separately approved import metadata is needed.  
**API changes:** Optional workbook inspection/import routes only when this post-MVP task is approved.  
**Frontend changes:** Optional import UI only when approved.  
**Tests required:** Workbook/worksheet/column parsing and generic catalog mapping; core remains usable with the adapter absent.  
**Dependencies:** Post-MVP connector architecture, if approved.  
**Acceptance criteria:** Worksheet columns become ordinary generic fields and require no engine special case.  
**Potential risks:** File size, malformed workbooks, and retention of uploaded data.

### Task 13.3 — Salesforce and other vendor connectors (post-MVP)

**Objective:** Add a separately approved vendor adapter, beginning with Salesforce only if prioritized.  
**Why it exists:** Vendor connectors are future extensions, not prerequisites for the generic application.  
**Files/components likely affected:** Isolated adapter package, secure credential integration, metadata reconciliation, contract tests.  
**Database changes:** Adapter-specific credential references/bindings outside generic System/Object/Field attributes, only if approved.  
**API changes:** Vendor discovery/OAuth routes only for approved scope.  
**Frontend changes:** Vendor setup/OAuth flow only for approved scope.  
**Tests required:** Adapter contract, OAuth PKCE/state/token tests if applicable, metadata reconciliation, no vendor behavior in the generic engine.  
**Dependencies:** Post-MVP connector architecture and explicit product approval.  
**Acceptance criteria:** The adapter is independently removable and maps metadata to generic entities; core passes with no connector installed.  
**Potential risks:** Credential leakage, external API changes/rate limits, and vendor assumptions escaping adapter boundaries.

## Phase 14 — Real execution, scheduling, and monitoring (post-MVP)

### Task 14.1 — Add explicit real execution and audit trail

**Objective:** Extend mature simulation into explicitly configured fetch/transform/validate/write execution.  
**Why it exists:** Production side effects are materially different from safe dry runs.  
**Files/components likely affected:** Execution service/worker, connector execution interface, run/audit models, permissions and confirmation UI.  
**Database changes:** Run ID, lifecycle timestamps, row counts, errors, retries, audit events, retention policy.  
**API changes:** Start/status/cancel execution APIs with idempotency and authorization.  
**Frontend changes:** Explicit configuration/confirmation and execution history; simulation remains clearly distinct.  
**Tests required:** Idempotency, partial failure, retry safety, audit completeness, credential protection, dry-run non-regression, connector failure simulation.  
**Dependencies:** Post-MVP only; approved connector execution capability and production-execution threat/recovery review required. No MVP task depends on this.  
**Acceptance criteria:** No real writes occur from dry-run/editor simulation; every real run is attributable, bounded, auditable, and explicitly authorized.  
**Potential risks:** Duplicate writes, irreversible side effects, secrets/PII in logs, and unsafe retries. Do not start this phase until operational recovery and authorization are approved.

### Task 14.2 — Add scheduling, monitoring, and alerting

**Objective:** Add recurring runs, operational monitoring, and alerts only after run semantics are stable.  
**Why it exists:** Schedules and distributed execution add lifecycle and reliability concerns outside MVP.  
**Files/components likely affected:** Scheduler/worker, run state machine, observability/alerting configuration, operations docs.  
**Database changes:** Schedule, lease/claim, heartbeat, and alert-delivery records as justified by deployment design.  
**API changes:** Schedule lifecycle, execution history, retry controls, monitoring endpoints.  
**Frontend changes:** Schedule management, dashboards, alert/history views.  
**Tests required:** Duplicate scheduling prevention, missed-run recovery, worker restart, retry/alert behavior, timezone and daylight-saving transitions.  
**Dependencies:** Task 14.1; post-MVP only.  
**Acceptance criteria:** Schedules are observable, recoverable, and do not duplicate execution; operational limits, retention, and alert ownership are documented.  
**Potential risks:** Raspberry Pi uptime/storage constraints, clock/timezone errors, queue growth, and premature distributed-worker complexity.

## Cross-phase architectural answers and gates

The proposed decisions are specified in the supporting documents. At implementation gates, explicitly verify:

1. **Dynamic catalog:** generic tenant-scoped relational tables with parent FKs; no vendor-specific core entities.
2. **Stable identity:** immutable UUIDs; graph references field UUIDs via ports, never names or labels.
3. **Field deletion:** archive rather than physical deletion; reject archival while referenced by the current graph and return integration references. Historical graph retention is not part of MVP.
4. **Object deletion:** archive rather than cascade-delete; reject while used as an integration endpoint or while active field references remain. System archive applies the same rule to its hierarchy.
5. **Graph persistence:** JSON document with master-spec `version: 1`, stable node/edge IDs, and field-ID ports. A lightweight current save revision may prevent lost updates; immutable snapshots/history are post-MVP only if later required.
6. **Dynamic React Flow ports:** derive from object-field API metadata; field UUIDs are handle IDs; labels are display-only; backend revalidates.
7. **Engine boundary:** pure typed input of validated graph, resolved generic field metadata, sample rows, and limits; typed row outcomes/output values/errors/node trace; no I/O or framework dependencies.
8. **Simulation:** authenticated, bounded dry-run request with rows and optional draft graph/revision; response includes per-row outcomes, aggregate counts, field-ID-keyed targets, traces, structured errors, and truncation/limit indicators.
9. **Seed data:** idempotent fixture loader uses normal generic catalog rows and services; examples do not enable special-case core behavior.
10. **Future connectors:** adapters discover/bind generic catalog metadata behind a narrow interface; engine and generic core operate with zero adapters.

## Major risks / decisions to confirm before implementation

- The root `MASTER-SPEC.md` is the authoritative specification. Phase 0 should preserve and reference it; no separate product specification is required.
- The workspace is not a Git repository and has no existing project skeleton; bootstrap must preserve the supplied roadmap and establish its canonical documentation path.
- Delete/archive, type coercion/null semantics, `e164` and `date` behavior, and trigger configuration require product sign-off before their respective phases. Graph-history retention is outside MVP.
- Cookie-auth CSRF, reverse-proxy trust, secret provisioning, single-process rate limiting, data retention, and connector credential storage require deployment/security decisions.
- Hardware is ARM64 with 4 CPU cores and about 8 GiB RAM. Validate the entire Docker/dependency stack and set realistic simulation/resource limits on the target, not only on a developer workstation.
- API shape generation/shared validation approach (OpenAPI-generated TypeScript vs contract tests) should be selected in Phase 1 and applied consistently to graph and error schemas.

## Definition of MVP complete

From an empty database, the single internal user creates arbitrary systems, objects, and fields; creates a generic integration; maps fields through the visual editor; inserts transformations; runs server-side simulation on sample rows; inspects per-node trace; returns to the landscape; and sees conflicts and dependencies. Field renames do not break graph references, and simulation never performs external writes. Connectors, graph-history infrastructure, real execution, scheduling, and monitoring are not MVP prerequisites.
