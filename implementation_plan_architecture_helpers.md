# Deterministic Architecture Helper-Action Layer — Implementation Plan

## Scope and outcome

Design a narrow, deterministic internal API that lets a future embedded agent inspect architecture, create a non-domain-persisting proposal, request explicit human approval, apply only approved operations, and safely undo its own changes. This phase does **not** implement OpenCode/MCP/LLM integration, a chat interface, provider configuration, a generic command executor, or a replacement architecture engine.

Proposal generation may persist helper lifecycle, operation, validation, approval, and audit records. It must not write architecture-domain data. Only `apply_change_set` may persist approved architecture-domain operations.

## 1. Current implementation reuse map

| Concern | Existing implementation | Reuse and constraints |
|---|---|---|
| User, tenant, workspace authorization | `api/app/auth/dependencies.py`, `api/app/workspaces/routes.py` | Use authenticated user and existing workspace access rules. There is no role/approver model; do not imply one. |
| Workspace and state resolution | `api/app/architecture/routes.py`, `api/app/architecture/state_scope.py` | Resolve state within workspace; preserve canonical object IDs; reuse `assert_writable`, state membership, overrides, and Current protection. |
| Current enrichment | `POST /api/workspaces/{workspace_id}/states/{state_id}/include-objects` in `api/app/architecture/routes.py` | This remains the only controlled Current-enrichment workflow. Helper proposals do not write to Current. |
| Canonical registry and state nodes | `api/app/models/architecture_object.py`, `api/app/architecture/objects.py` | Reuse canonical IDs and existing discipline checks. Never substitute model-local IDs for registry IDs. |
| Enterprise | `api/app/architecture/enterprise.py` | Reuse goals, requirements, capabilities, processes, roles, principles, relationships, strategy/capability/process projections, and impact logic. |
| Information | `api/app/architecture/information.py` | Reuse entities, canonical child attributes, relationships, Catalog realizations, ownership, lineage, and impact logic. |
| Solution | `api/app/architecture/solution.py` | Reuse boundaries, components, members, interfaces, operations/events, repositories, deployment, trust boundaries, and typed links. Preserve provided/required semantics. |
| Catalog | `api/app/catalog/routes.py`, `api/app/catalog/service.py`, `api/app/models/catalog.py` | Search and inspect existing systems, objects, and fields only. This phase never creates or modifies Catalog records. |
| Integrations and Contracts | `api/app/integrations/routes.py`, `api/app/integrations/graph.py`, `api/app/models/integration.py` | Reuse endpoint, graph, field-reference, and revision validation. Reused Contracts are read-only; changed designs become new draft Contracts. |
| Mapping/transformation engine | `api/app/engine/core.py`, `api/app/engine/operations.py`, `api/app/integrations/integration_design.py` | Reuse existing graph validation and Mapping & Tests projections. Never fabricate Catalog-field IDs or execute a test automatically. |
| Scenarios and conformance | `api/app/scenarios/routes.py`, `api/app/scenarios/schemas.py`, `api/app/integrations/integration_design.py` | Reuse scenario reference validation and conformance projections. Do not run evaluations/tests during proposal or apply. |
| Traceability | `api/app/architecture/traceability.py` | Reuse the graph, usages, and trace traversal. Filter and cap helper responses rather than returning unrestricted workspace graphs. |
| Deterministic demo | `api/app/demo/{catalog,enterprise,information,solution,integration,scenarios}.py` | Reuse as deterministic fixture/reference material for customer-onboarding acceptance. The complete demo generator itself is not a proposal/apply mechanism. |
| Existing behavioral tests | `api/tests/test_architecture_states.py`, `test_enterprise_workbench.py`, `test_information_modeler.py`, `test_solution_designer.py`, `test_traceability.py`, `test_integrations.py`, `test_integration_designer.py`, `test_scenarios.py`, `test_demo_workspaces.py` | Extend focused tests and preserve existing isolation, field-reference, revision, and conformance behavior. |

Most existing write handlers combine HTTP parsing, validation, database writes, and `commit()`. The helper layer must not call route handlers as internal functions. Extract only the domain validation/write operations needed for a transactional application service, retaining the existing API behavior.

## 2. Smallest safe architecture

Add one `api/app/helper_actions/` package with strict schemas, shared context resolution, read helpers, proposal helpers, lifecycle/application services, and a narrow router. Keep operation dispatch a closed registry of typed domain operations; each operation maps to an explicit service method. There is no arbitrary function name, executable code, ORM payload, SQL, or model-selected dispatcher in the request schema.

All invocations use one context resolver to validate:

- Authenticated user and accessible tenant/workspace.
- Enabled disciplines and requested discipline subset.
- Architecture state, workspace ownership, state type, and active workbench when relevant.
- Selected canonical object IDs, active status, kind, tenant/workspace scope, and relationship endpoints.
- Existing workspace permission and CSRF on mutating requests.

Reads may inspect Current, Candidate, or Target. Proposal targets and domain apply operations must target Candidate or Target. Reject cross-workspace references, unauthorized actions, disabled-discipline actions, direct Current writes, malformed/noncanonical IDs, unsupported relationship types, and IDs that do not resolve to active records in the authorized workspace. Requested disabled disciplines are omitted by composite orchestration; a direct helper request for a disabled discipline is rejected.

Read responses are structured, deterministic, sorted, paginated/capped, and include truncation metadata. Bound search page size, details, relationships/usages, and trace depth/results. Do not expose arbitrary ORM records or dump every workspace object by default.

### Narrow internal API

Use existing cookie authentication and CSRF protections. Proposed routes:

- `POST /api/workspaces/{workspace_id}/helper-actions/reads/{helper_name}` — invoke one allowlisted bounded read helper.
- `POST /api/workspaces/{workspace_id}/helper-actions/proposals/{helper_name}` — create a durable change-set proposal without domain writes.
- `GET /api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}` — retrieve proposal and bounded operation details.
- `POST /api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/validate`
- `POST /api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/approve` — explicit authenticated approval of the exact proposal hash.
- `POST /api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/apply`
- `POST /api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/undo`
- `GET /api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/status` — lifecycle and per-operation results.

Use strict Pydantic inputs (`extra="forbid"`), bounded strings/lists/depths, and typed helper-specific request models. Approval is a separate user action even when proposer and approver are the same user; record both user IDs independently and bind approval to the exact immutable proposal hash. No separation-of-duties claim is made.

### Bounded read helper registry

Implement deterministic wrappers over existing reads for: `get_workspace_context`, `get_enabled_disciplines`, `get_architecture_state`, `search_canonical_objects`, `get_object_details`, `get_object_relationships`, `get_object_usages`, `trace_architecture_path`, `compare_current_candidate`, `list_catalog_systems`, `inspect_catalog_schema`, `list_integration_contracts`, `inspect_contract`, `inspect_mapping_coverage`, and `inspect_scenarios_and_conformance`.

The wrappers should use the existing Enterprise impact comparison, Information impact/lineage/physical mapping projections, Solution design, Integration landscape/contract/conformance projections, and traceability graph where applicable. State and workspace filters are mandatory even if an underlying record is tenant-scoped.

## 3. Proposal and operation model

Each change set contains:

- Change-set ID, tenant/workspace/state IDs, state type, proposer ID, requested helper, creation/update timestamps, lifecycle status, and proposal hash.
- Bounded summary and input summary; assumptions; unresolved decisions; warnings.
- Reused canonical objects and proposal-local objects proposed for creation.
- Typed operations covering property updates, state memberships, state/canonical relationships, Contracts, mappings/transformations, scenarios, and tests.
- Expected traceability, validation results, approval data, apply results, undo status/results, and affected workbenches.

Each operation contains a stable operation ID, closed domain action and target type, existing canonical ID or temporary proposal ID, before value where applicable, proposed value, dependencies, validation status/issues, and human-readable explanation. Operation schemas use a discriminated union of known domain payloads; there is no arbitrary executable code.

Temporary IDs are resolved to canonical IDs only during apply; the result returns the mapping. Proposed updates capture the expected before projection/fingerprint. Validation and approval are invalidated if the immutable proposal changes. Apply revalidates and rechecks current before values immediately before writing.

### Helper families

- **Enterprise:** strategy chain (Goal → Requirement → Capability → Process), capability/process support, and impact resolution. Reuse matching goals, requirements, capabilities, processes, roles, principles, systems, and solutions before proposing creations.
- **Information:** entities, canonical child attributes, entity relationships, Catalog-field realizations, and information-gap resolution. Model type, optionality, keys, cardinality, ownership, stewardship, authority, classification, and sensitivity using existing schemas. Reuse Catalog fields only; ambiguous or absent realizations remain unresolved with an explicit gap. Never create a duplicate Catalog field to satisfy a logical mapping.
- **Solution:** boundary, components, provided/required interfaces, operations/events, repository usage, deployment, trust-boundary membership, and interactions. Preserve canonical system IDs and interface semantics. Do not propose sequence steps without supporting interfaces, operations/events, Contracts, repositories, or relationships.
- **Integration:** direct request/reply, event-driven, runtime-mediated, and file-transfer proposals; Contract, field mapping/transformation, resilience, scenario, and conformance-test proposals. Reuse existing Contract only if endpoints, interaction type, interfaces, purpose, schemas, mappings, resilience, and behavior already satisfy the design. Otherwise propose a new draft Contract and an explicit typed relationship such as “alternative to” or “proposed replacement for”; do not mutate the existing Contract. Match endpoint + interaction type + interfaces + purpose to avoid duplicate Contracts. Reuse only actual Catalog field IDs. Integration Runtime is optional. Ambiguous semantic mappings remain unresolved. Tests never run automatically.
- **Composite:** `propose_end_to_end_architecture` accepts business intent, workspace, Candidate/Target state, requested disciplines, preferred existing objects, integration preferences, constraints, and desired outcomes. It invokes enabled smaller helpers and returns one dependency-ordered change set. It omits disabled disciplines rather than requiring all four.

## 4. Exact persistence and migration

Add one Alembic migration after current head `0018` (proposed revision `0019_architecture_helper_actions.py`) and register the model in `api/app/models/__init__.py`. Use project JSON/JSONB conventions and composite tenant/workspace scoping consistent with existing models.

1. **`helper_change_sets`**: UUID ID; tenant/workspace/state foreign keys; proposer user ID; helper name; bounded summary/input summary; assumptions, unresolved decisions, warnings, reused/proposed refs; lifecycle status; immutable proposal hash; approval actor/time/hash; validation/apply/undo result summaries; created/updated/applied/undone timestamps.
2. **`helper_change_operations`**: UUID row ID; change-set ID; stable operation ID and dependency order; closed operation/action/target types; existing target ID or temporary ID; before/proposed JSON values; dependencies; validation status/issues; applied canonical ID; ownership metadata and post-apply fingerprint; per-operation apply/undo status and conflict explanation.
3. **`helper_audit_events`**: append-only event ID; tenant/workspace/state/change-set/user IDs; event type; bounded redacted summary; affected canonical IDs; affected Contract IDs and revisions; timestamp.

Approval event data records proposer and approver separately, including same-user approval. Audit only structured, bounded input summaries; never store secrets, full uploaded files, or unrestricted model prompts. No new architecture-domain model is required for helper proposals; existing canonical domain models remain authoritative.

## 5. Validation, approval, apply, and undo rules

### Validation and approval

Validation checks workspace/tenant/state scope, enabled discipline, canonical ID/kind, relationship allowlists, state type, domain constraints, dependencies, Catalog-field existence, mapping ambiguity, Contract endpoint/interface consistency, and scenario references. Validation may read and persist helper validation results only; it does not write domain records, run tests, or execute mappings.

Approval requires an authenticated explicit action with the current proposal hash. Self-approval is allowed. Record proposer and approver independently. Any proposal change, invalidating context change, or stale hash requires revalidation and fresh approval.

### Transactional apply

`apply_change_set` requires approved status and matching approval hash, reloads and validates all context and operation fingerprints immediately before persistence, then applies operations in topological order in one SQLAlchemy transaction where practical. Use explicit operation-to-service dispatch; never call committing FastAPI handlers. Roll back all domain writes on failure. Preserve canonical IDs for reused objects and return affected objects, IDs, Contracts/revisions, state, and workbenches.

Write only Candidate/Target memberships, overrides, rows, and relationships through existing semantics. Reused canonical objects and reused Contracts are read-only. Catalog is strictly read-only in this phase. Candidate/Target Contract changes are represented by new draft Contracts, with explicit relationships to alternatives/replacements. Scenario creation follows Contract creation and validation. Record integration revision 1 for new Contracts; if a permitted future operation updates an owned Contract, increment its revision once for the whole apply and record before/after values. Do not run graph dry-runs, scenario evaluations, conformance tests, or other tests automatically.

### Conflict-safe undo

Undo affects only operations owned by the change set and is independent of import-batch undo. Reverse dependencies in order. For updates, restore before values only when current values still equal the recorded post-apply fingerprint. For creates, remove only the exact owned row/edge/membership/state occurrence and only if unchanged and not referenced outside the change set. Never delete reused objects, Catalog records, or reused Contracts. If a later edit or external reference is detected, refuse that destructive operation, preserve it, and report the conflicting operation/fields; mark undo partial/conflicted rather than claiming complete success. Retrying undo must be idempotent for already-reversed operations.

## 6. Permissions, gating, and security

- Reuse `get_current_user`, `get_accessible_workspace`, current session/CSRF validation, and the existing tenant-owner/active-tenant workspace boundary. Do not invent a new permission system.
- Resolve every state by both ID and workspace ID, and every canonical reference by tenant/workspace scope and expected kind. Treat tenant-scoped Integrations/Scenarios as workspace-visible only through the authorized workspace context.
- Direct proposal/apply writes to Current are rejected. Current enrichment remains available only through its existing controlled endpoint and is not a helper operation.
- Enforce workspace discipline gating per requested operation and helper. Composite orchestration skips disabled disciplines; direct disabled helper calls fail closed.
- Allow only registered helper names, operation types, targets, and relationship types. No generic executor, dynamic import, arbitrary SQL, raw ORM serialization, or caller-selected service/function.
- Bound request and result sizes, operation counts, dependency depth, graph/trace results, and strings. Redact sensitive values from audit; do not persist model prompts or secrets.
- Protect mutating endpoints with CSRF. Approval is a separate authenticated request, explicit and hash-bound, but may be by the proposer under the current model.

## 7. Files to add or modify

### New files

- `api/app/helper_actions/__init__.py`
- `api/app/helper_actions/schemas.py`
- `api/app/helper_actions/context.py`
- `api/app/helper_actions/service.py` (closed operation registry, lifecycle, validation, proposal orchestration; split only if needed for clarity)
- `api/app/helper_actions/routes.py`
- `api/app/models/helper_action.py`
- `api/alembic/versions/0019_architecture_helper_actions.py`
- `api/tests/test_helper_actions.py`
- `api/tests/test_helper_action_apply.py` (apply/undo and composite acceptance)

### Existing files to modify

- `api/app/models/__init__.py`, `api/app/main.py`.
- Extract transaction-compatible domain operations only as needed from `api/app/architecture/{enterprise,information,solution}.py`, `api/app/integrations/routes.py`, and `api/app/scenarios/routes.py`; preserve existing route contracts and validation.
- Add focused tests in the existing workbench, state, integration, scenario, and traceability test modules where regression coverage belongs.

No frontend files are needed in this phase; there is no UI redesign or OpenCode integration.

## 8. Transaction and Contract revision boundaries

Lifecycle/validation/approval/audit persistence is separate from architecture-domain operations, but approval and audit transitions must be recorded consistently. Apply must persist domain operations and the applied audit/status transition transactionally where feasible; if audit storage cannot be in the same transaction, do not report apply success without a durable result. Undo records per-operation completion/conflict so retries are safe.

Existing API handlers commit per request, so application must use extracted database-session operations that flush but do not commit. On any domain failure, roll back the unit of work. New Contracts start at revision 1; existing Contracts are never updated by helper apply in this phase. Record Contract ID and revision for reuse/new creation in proposal, apply response, and audit. Validate scenario documents against the final proposed Contract references before apply; do not evaluate scenarios or mark them passing automatically.

## 9. Compatibility and migration strategy

Add a single forward-only migration after `0018`; no existing table semantics or API payloads should change. Register models for metadata-based test databases and verify Alembic chain compatibility. Preserve SQLite and PostgreSQL JSON behavior and existing composite tenant foreign-key patterns. Do not change application version or release metadata for this planning/feature work unless separately requested under repository release policy.

The key compatibility risk is that several existing domain APIs are route-centric and commit internally. Refactor only the minimum operation logic needed for safe apply; keep their public endpoints, schemas, validation, and behavior stable. The helper API is additive and does not affect existing web workbenches.

## 10. Targeted test strategy

Use the existing TestClient + SQLite/foreign-key fixtures and patterns from `test_traceability.py`, `test_architecture_states.py`, `test_information_modeler.py`, `test_solution_designer.py`, `test_integrations.py`, `test_integration_designer.py`, and `test_scenarios.py`.

- **Reads/context:** tenant/workspace isolation; active/archived state checks; caps, deterministic order, truncation; invalid IDs; enabled/disabled disciplines; selected-object kind checks.
- **Proposal lifecycle:** proposal persists helper records but no architecture-domain rows or changes to states, memberships, relationships, Catalog, Contracts, mappings, scenarios, or tests; stable operation IDs; strict schemas; validation result persistence; separate explicit approval bound to hash; self-approval with separate proposer/approver fields.
- **Domain proposals:** reuse matching canonical objects; proposal-local IDs; state isolation; child attributes; relationship allowlists; provided/required direction; repository/trust/deployment; no unsupported sequence fabrication; Catalog-only realization and unresolved ambiguity.
- **Integration:** Contract deduplication by endpoints/interaction/interfaces/purpose; unchanged reused Contract; alternative/replacement Contract proposal when design differs; actual Catalog field IDs; runtime optional; invalid graph/reference rejection; resilience schema; scenarios validate but tests do not run.
- **Apply/undo:** unapproved/stale-hash rejection; immediate revalidation; transaction rollback injection; canonical ID preservation; only approved operations applied; Current unchanged; Contract revision recording; exact ownership undo; no reused-object deletion; detection/refusal of later edits/external references; idempotent retry and clear partial-conflict result.
- **Migration:** revision chain, SQLite metadata, and upgrade compatibility.

For each slice, run focused tests during development, then run `make check` once at the end of that slice. Stop for human review before starting the next slice. Do not run tests for this plan-only task.

## 11. Deterministic customer-onboarding acceptance scenario

Create an isolated test workspace with all relevant disciplines enabled and deterministic existing demo Catalog systems/objects/fields (CRM, Billing, and optionally Integration Runtime). Seed the Catalog inventory only; do not seed the completed architecture/Contracts that the helper is meant to propose. Use a fixed structured input: customer onboarding intent, Candidate state, preferred demo systems and Catalog fields, explicit integration preferences/constraints, and desired trace outcomes.

Expected proposal may contain:

- Enterprise Goal → Requirement → Capability → Process, reusing matching canonical objects first.
- Information Customer entity → canonical child attributes → realizations to existing Catalog fields. Missing/ambiguous physical fields remain unresolved; no Catalog additions are proposed.
- Solution Boundary → components → provided/required interfaces → supported operations/events → repository usage.
- Integration direct request/reply and event-driven/runtime-mediated paths where supported by existing systems/interfaces; new draft Contract only when no existing Contract matches; explicit alternative/replacement relationship when based on an existing Contract; real-field mappings; supported transformations/resilience; success/error scenario proposals and test definitions.

Acceptance assertions:

1. Proposal creation persists change-set, operation, validation, and audit data only; all architecture-domain tables/state documents remain unchanged.
2. Preview distinguishes reused canonical IDs from proposed temporary IDs and explains unresolved Catalog mappings.
3. Apply fails before approval, then persists only approved operations after fresh validation.
4. Current state and its domain-visible contents remain unchanged.
5. Candidate gains the approved cross-discipline trace, visible through existing traceability and discipline workbenches.
6. Existing Mapping & Tests and conformance projections validate the generated Contract structures; no test/evaluation is automatically run by proposal or apply.
7. Undo removes only unchanged change-set-owned writes; reused Catalog objects, fields, architecture objects, and Contracts remain intact.

## 12. Browser-visible acceptance workflow

Use the authenticated same-origin API (for example the existing API docs during development) to inspect context, invoke the deterministic proposal, review reused/proposed objects and unresolved decisions, validate, explicitly approve the displayed proposal hash, apply, and inspect status/operation results. Then use existing UI surfaces—Candidate selection in `web/src/components/architecture/ArchitectureTopBar.tsx`, existing enterprise/information/solution workbenches, `web/src/IntegrationWorkspace.tsx` and its `ScenarioWorkspace`, and existing trace panels—to confirm the Candidate result and Current isolation. No helper preview/approval UI is included in this phase.

## 13. Stop conditions and review gates

Every slice ends with focused tests and exactly one `make check`, followed by a human review gate. Stop and request review if a slice needs to weaken tenant/workspace/state checks, add Catalog writes, mutate reused Contracts, write Current outside the existing enrichment path, accept ambiguous field mappings, invoke a test automatically, create an arbitrary executor, or implement UI/OpenCode integration. Do not begin the next slice until the preceding slice is accepted.

## Approved decisions incorporated

1. **Self-approval:** Allowed for now. Approval remains a separate, explicit, authenticated action bound to the exact proposal hash. Store proposer and approver independently even when they are the same user; do not imply separation of duties.
2. **Catalog:** Reuse existing Catalog systems, objects, and fields only. Never create or modify Catalog records in this phase. Unmapped/ambiguous logical attributes or Contract fields remain unresolved with an explained gap.
3. **Existing Contracts:** Reused Contracts are read-only. Reuse only when endpoints, interaction type, interfaces, purpose, schemas, mappings, resilience, and behavior satisfy the proposal. Otherwise propose a new draft with an explicit alternative/replacement relationship. Match endpoints, interaction type, interfaces, and purpose to avoid duplicates.
4. **Proposal persistence:** “Persists nothing” means no architecture-domain changes. Helper lifecycle, operation, validation, approval, and audit records may persist. Only `apply_change_set` performs approved architecture-domain writes.

## Remaining ambiguity

No blocking policy ambiguity remains from the four decisions. Implementation should still confirm exact supported relationship labels/types for “alternative to” and “proposed replacement for” against current relationship constraints, and define a deterministic “purpose” matching normalization for Contract deduplication before Slice 3. If the existing relationship model cannot represent these Contract links safely, propose a narrowly typed extension for review rather than overloading an unrelated relationship type.
