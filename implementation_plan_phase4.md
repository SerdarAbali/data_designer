# Implementation Plan — Phase 4: Discipline Workbenches over the Shared Canonical Model

## Revision notes (corrections incorporated)

This revision supersedes the first draft and folds in five corrections:

1. **No polymorphic relationship endpoints.** `architecture_relationships` references
   `architecture_objects` registry IDs on *both* endpoints with composite foreign keys.
   Contracts, scenarios, catalog objects, and catalog fields participate through
   **registry-reference rows** (real typed FK columns on the registry, not `kind + UUID`
   pairs).
2. **Child objects are canonical and state-scoped by membership, not by embedded arrays.**
   Information attributes and interface operations are canonical child records. Candidate
   isolation uses an explicit **state-membership table** plus **bounded scalar property
   overrides**; child arrays are never duplicated inside `candidate_overrides`.
3. **Slice 1 is the core Information Modeler only** (entities, inline attributes, data
   types, required/optional, identifiers, cardinality, logical-to-physical field mapping).
   Ownership, stewardship, classification, quality, and lineage views are deferred.
4. **Each discipline uses a specialized visual editor** (see §1.1). The generic
   architecture-card renderer is **not** the primary editor for any of the four
   workbenches.
5. **Release/versioning removed from the sequence.** Tagging and version bumps happen only
   after Phase 4 is implemented and reviewed (§16).

---

## 0. Basis of this plan (what exists today)

- **Shared canonical layer:** `ArchitectureObject` registry
  (`api/app/models/architecture_object.py:22`) with typed tables `business_requirements`,
  `business_capabilities`, `information_objects`, `solution_boundaries`,
  `solution_components`, `architecture_interfaces`, plus `SolutionMember` (`:138`).
  Systems self-register as canonical objects via an `after_insert` hook (`:171`).
- **State/view layer:** `ArchitectureState` (`api/app/models/workspace.py:51`) stores
  `nodes[]` + `relationships[]` JSON. `ArchitectureStateNode` carries `discipline`,
  `parent_occurrence_id`, `candidate_overrides`, `display_metadata`
  (`api/app/architecture/schemas.py:19`). Current is read-only; candidates duplicate +
  isolate (`architecture/routes.py` `duplicate_architecture_state`; `update_architecture_state`
  returns 409 for `current`).
- **Frontend studio:** `ArchitectureCanvas.tsx` renders one generic React Flow graph,
  filtered per discipline by `projectStateNodes` (`architectureCanvasModel.ts:70`). Node
  renderers: `ArchitectureOccurrenceNode.tsx`, `ArchitectureBoundaryNode.tsx`. Inspector:
  `ArchitectureObjectInspector.tsx`. Discipline tabs: `ArchitectureDisciplineTabs.tsx`.
- **Integration engine:** `integrations` table (`graph`, `response_graph`,
  `error_response_graph`, `interaction_type`, `sample_rows`, `revision`,
  `integration_field_refs`, `integration_dependencies`), `IntegrationWorkspace.tsx`
  mapping editor, scenarios/sequence, CSV contract exchange, dry-run.
- **Phase 3 imports (uncommitted working tree on top of `8e57ba8`):**
  `api/app/imports/*`, `solution_members`, `include-objects` endpoint
  (`architecture/routes.py:454`), wizard `components/import/ArchitectureImportDialog.tsx`.
- **Tests:** in-memory SQLite + `StaticPool` + CSRF-cookie pattern
  (`api/tests/test_architecture_states.py:15`); vitest + jsdom for frontend.

**Core gap:** the four discipline tabs are today the *same* generic node renderer with a
`discipline` filter. The gap is not "missing graph" but missing domain structure
(attributes, responsibilities, provided/required interfaces, operations, processes, goals)
and missing discipline-specific editors and views.

---

## 1. Core architectural decisions

Two layers; every workbench reads and writes only through them.

1. **Canonical layer (state-independent, stored once):** existing catalog
   (`systems/objects/fields`), existing `ArchitectureObject` + typed tables, existing
   `integrations`, plus new typed tables, **registry-reference rows**, and **one canonical
   relationship table** (the traceability spine).
2. **View/occurrence layer (per state):** existing `ArchitectureState.nodes/relationships`
   for **membership + layout of canvas elements only**, plus a new explicit
   **state-membership table** for non-canvas child objects (attributes, operations).

Applied throughout:
- All relationship endpoints are canonical `architecture_objects` IDs (referential
  integrity enforced by composite FKs). External entities participate as registry-reference
  rows.
- Sub-elements (attributes, operations) are canonical `ArchitectureObject` rows with a
  parent FK, rendered *inside* their parent block — never as generic cards.
- Candidate isolation for canvas objects: edits to Current-resident objects are stored as
  **bounded scalar property overrides** on the candidate node (extending the existing
  `candidate_overrides` string mechanism); child-object isolation uses the state-membership
  table. Child arrays are never embedded in overrides.
- Existing integration contracts/mappings/scenarios/tests and catalog objects/fields stay
  authoritative; new tables reference them by ID only.

### 1.1 Specialized editors are mandatory (correction 4)

Each discipline is a purpose-built editor. The generic architecture-card renderer must not
remain the primary editor for any workbench.

| Discipline | Primary visual editor | Models |
|---|---|---|
| Information | Entity–Relationship modeler | Entities, inline attributes, types, keys, cardinality, physical realization |
| Solution | Hierarchical component/interface modeler | Context, decomposition, components, provided/required interfaces, repositories, deployment |
| Enterprise | Capability/process/strategy modeler | Goals, requirements, capabilities, processes/value streams, roles, principles |
| Integration | Contract/message-flow modeler | Producers/consumers, interfaces, operations/events, request/success/error flow, mappings, tests |

The existing generic canvas remains available as an overview (systems + integration routes),
but it is not the editor surface for the four workbenches.

---

## 2. Gap analysis per discipline

### Enterprise
| Required | Exists | Gap |
|---|---|---|
| Business requirements, capabilities | typed tables | No goals, processes, principles, roles |
| Applications/solutions supporting capabilities/processes | systems + `SolutionBoundary` + `SolutionMember` | No typed support edges / application-support projection |
| Current-to-Candidate impact | candidate duplication | No diff/impact API or view |
| Dependencies, risks, gaps | integration deps | No risk/gap/constraint model or view |
| Strategy-to-execution trace | — | No goal/process chain |

### Information
| Required | Exists | Gap |
|---|---|---|
| Conceptual/logical entities | `InformationObject` (owner, authoritative system, classification) | No attributes, no conceptual/logical distinction |
| Attributes in blocks, data types, required, keys | — | Entire attribute model missing |
| Entity relationships + cardinality | generic state edges only | No ER semantics |
| Logical→physical mapping | Catalog objects/fields exist | No attribute→field link |

### Solution
| Required | Exists | Gap |
|---|---|---|
| Context, boundaries | `SolutionBoundary` + members + envelope geometry | No context view |
| Components, responsibilities | `SolutionComponent` (name/description only) | No responsibility/technology/type |
| Provided/required interfaces | `ArchitectureInterface` (name only); generic arrows | Interfaces not explicit elements |
| Operations/events | — | Missing |
| Repositories, deployment, trust boundaries, quality attrs | — | Missing |
| Drill-down | parent_occurrence_id + boundary geometry | No hierarchical navigation |

### Integration
| Required | Exists | Gap |
|---|---|---|
| Producer/consumer, interfaces, operations/events | systems + interactions | No explicit interfaces/operations links |
| Contracts, flows, schemas, mappings, transformations, routing, tests | authoritative | No pattern/resilience/security/status model, no flow workbench |
| Message-flow / interface-contract views | Landscape + Mapping drawer | Not discipline-scoped; no flow view |

---

## 3. Reusable existing structures

**Backend:** `architecture/objects.py` (`KIND_MODELS`, `KIND_DISCIPLINE`, `_object_response`,
`_enabled`, `_get_active_system`), `architecture/routes.py` (`get_accessible_workspace`,
`_validate_state_nodes`, `duplicate_architecture_state`, `include_objects_in_state`,
`_placement`), `imports/service.py` (`normalize_name`, `build_index`, `_create_record`,
snapshot helpers), `integrations/routes.py` (`resolve_endpoint`, `active_fields`,
`graph_references`, `replace_field_refs`), `scenarios/evaluate`, `catalog/service.py`.

**Frontend:** `architectureCanvasModel.ts` (`resolveOccurrence`, `resolveRelationships`,
`projectStateNodes`, `solutionBoundaryGeometry`, mutation helpers),
`components/architecture/*`, `components/landscape/FieldLineageExplorer.tsx` +
`landscapeMappingModel.ts`, `components/mapper/*` + `contractGraphTypes.ts` +
`mappingGraphModel.ts`, `components/scenarios/ScenarioWorkspace.tsx` +
`SequenceDiagram.tsx` + `scenarioSequenceLayout.ts`, `architectureTypes.ts`,
`designLabels.ts`, `styles/studio.css` + `style.css` tokens.

**Refactor for reuse:** extract the loading block in `ArchitectureCanvas.tsx:287-316` into
`web/src/workbench/useArchitectureModel.ts` so all workbenches share one fetched model and
one save queue.

---

## 4. New canonical object types and properties

All new kinds are added to `ArchitectureObjectKind`
(`api/app/architecture/schemas.py:9`), `KIND_MODELS`/`KIND_DISCIPLINE`
(`api/app/architecture/objects.py:53`), `KIND_DISCIPLINE_FOR_INCLUDE`
(`api/app/architecture/routes.py:438`), and frontend `architectureTypes.ts`. Each new typed
table follows the `_TypedArchitectureObject` pattern (`object_id` PK/FK, `tenant_id`,
`name`, `description`).

| Kind | Table | Extra columns |
|---|---|---|
| `business_goal` | `business_goals` | `owner`, `outcome_metric`, `horizon`, metadata |
| `business_process` | `business_processes` | `owner`, `process_type` (process/value_stream), metadata |
| `architecture_principle` | `architecture_principles` | `principle_type` (principle/constraint/quality), `rationale`, metadata |
| `organization_role` | `organization_roles` | `role_type` (organization/role), metadata |
| `information_attribute` | `information_attributes` | `entity_object_id` (FK→`architecture_objects`), `data_type`, `required`, `nullable`, `is_key`, `is_identifier`, `ordinal`, `definition`, metadata |
| `data_repository` | `data_repositories` | `owner`, `repository_type`, `technology`, metadata |
| `interface_operation` | `interface_operations` | `interface_object_id` (FK→`architecture_objects`), `operation_kind` (operation/event/command/query), `request_object_id`, `response_object_id`, metadata |
| `deployment_node` | `deployment_nodes` | `technology`, `environment`, `hosting`, metadata |
| `trust_boundary` | `trust_boundaries` | `security_level`, metadata |

Existing tables extended additively:
- `solution_components`: `responsibility` (Text), `component_type`, `technology`, metadata.
- `architecture_interfaces`: `interface_kind` (sync/async), `protocol`, `technology`, metadata.
- `integrations`: `pattern`, `implementation_status` (check `draft|in_progress|built|verified`),
  `producer_interface_id`, `consumer_interface_id` (nullable), and a bounded `specification`
  JSON validated by a strict Pydantic model holding `retry{max_attempts,backoff}`,
  `timeout_ms`, `idempotent`, `idempotency_key_field_id`, `security{auth_type,notes}`,
  `routing`, `orchestration_role`.

`information_attribute` and `interface_operation` are **child objects**: they are not canvas
nodes and render inside their parent block.

### 4.1 Registry-reference mechanism (correction 1)

External entities that must appear in traceability are materialized as **registry-reference
rows** in `architecture_objects`, each backed by a real FK column so referential integrity
is enforced by the database. No `kind + UUID` loose pairs are ever stored.

`architecture_objects` gains nullable typed reference columns:

| Column | FK target | Registry kind | Dedup unique (active) |
|---|---|---|---|
| `system_id` (existing) | `systems(id, tenant_id)` | `system` | existing |
| `catalog_object_id` | `objects(id, tenant_id)` | `catalog_object_ref` | `(tenant_id, catalog_object_id)` |
| `catalog_field_id` | `fields(id, tenant_id)` | `catalog_field_ref` | `(tenant_id, catalog_field_id)` |
| `integration_id` | `integrations(id, tenant_id)` | `contract_ref` | `(tenant_id, integration_id)` |
| `scenario_id` | `scenarios(id, tenant_id)` | `scenario_ref` | `(tenant_id, scenario_id)` |

Constraints: composite FKs with `(id, tenant_id)`; a `CHECK` that at most one reference
column is populated; partial unique indexes per column where the column is non-null and the
row is active. Reference rows are created on demand (e.g., when an attribute is realized to
a field) and reused thereafter. Deletion of the referenced entity cascades/restricts through
the real FK, never leaving a dangling traceability endpoint.

---

## 5. New typed relationships (canonical spine)

`architecture_relationships` is the single traceability edge table. **Both endpoints are
registry IDs**; composite FKs enforce integrity.

```
id UUID pk
tenant_id UUID FK tenants
source_object_id UUID
target_object_id UUID
relationship_type String(60)
properties JSON bounded            # scalar/list metadata only (never child objects)
created_at, updated_at
FK (source_object_id, tenant_id) -> architecture_objects(id, tenant_id) ON DELETE CASCADE
FK (target_object_id, tenant_id) -> architecture_objects(id, tenant_id) ON DELETE CASCADE
Unique (tenant_id, source_object_id, target_object_id, relationship_type)
Index (tenant_id, source_object_id) and (tenant_id, target_object_id)
CHECK source_object_id <> target_object_id
```

**Containment is not stored here** — it is derived from parent FKs
(`information_attributes.entity_object_id`, `interface_operations.interface_object_id`,
`solution_members`, node `parent_occurrence_id`). This avoids duplicate edges.

Cross-link relationship types (extend `SEMANTIC_RELATIONSHIP_TYPES` in
`architectureTypes.ts`):
- Enterprise: `has_process` (capability→process), `supports` (application→capability/process),
  `affects` (change→capability/process), `governed_by` (→principle), `owned_by`
  (→organization_role), `depends_on`, `impacts`, `satisfies` (system→requirement).
- Information: `references` (entity→entity; ER cardinality + optionality in `properties`),
  `realizes` (attribute→`catalog_field_ref`), `authoritative_for` (system→information object),
  `stewarded_by`.
- Solution: `provides`/`requires` (component→interface), `implements`
  (component→requirement/capability/process), `uses_repository`, `deployed_on`,
  `crosses` (interface→trust_boundary).
- Integration: `produces`/`consumes` (contract→interface), `invokes`
  (contract→`interface_operation`), `verified_by` (contract→`scenario_ref`).

State `relationships[]` remain presentation edges and gain an **optional**
`relationship_id` reference to a canonical edge (backwards compatible).

---

## 6. State membership and property overrides for child objects (correction 2)

Child objects (attributes, operations) are canonical but must be isolatable per state
without duplicating arrays.

New table `architecture_state_members`:

```
id UUID pk
tenant_id UUID FK tenants
workspace_id UUID FK workspaces
state_id UUID FK architecture_states ON DELETE CASCADE
object_id UUID                                # child registry id
membership String CHECK (membership IN ('included','excluded'))
property_overrides JSON bounded               # scalar presentation/property deltas ONLY
created_at, updated_at
FK (object_id, tenant_id) -> architecture_objects(id, tenant_id) ON DELETE CASCADE
Unique (state_id, object_id)
Index (tenant_id, state_id, object_id)
```

Child tables gain `created_in_state_id` (nullable FK→`architecture_states`; `SET NULL` on
delete) so a child authored in a candidate is not implicitly visible in Current.

**Effective children for a state** =
`canonical children where created_in_state_id IS NULL OR created_in_state_id = state`
`minus excluded` `∪ included` `with bounded property_overrides applied`.

`property_overrides` may contain only scalar keys valid for that child kind (e.g. `name`,
`data_type`, `required`, `nullable`, `is_key`, `ordinal`, `definition` for attributes;
`name`, `operation_kind`, `description` for operations), enforced and size-bounded by a
Pydantic validator. Existing node `candidate_overrides` remains limited to the current
scalar node presentation keys (`name`, `description`); **no child arrays are ever added to
it.** The backend information/solution endpoints compute effective children server-side; the
frontend does not merge arrays client-side.

---

## 7. Required database changes (migrations, additive)

- `0012_information_modeler`: registry reference columns on `architecture_objects`
  (`catalog_object_id`, `catalog_field_id`, `integration_id`, `scenario_id`, with FKs,
  checks, partial unique indexes); `architecture_relationships`; `information_attributes`
  (+ `created_in_state_id`); `architecture_state_members`.
- `0013_solution_designer`: alter `solution_components`, `architecture_interfaces`; add
  `interface_operations` (+ `created_in_state_id`), `data_repositories`,
  `deployment_nodes`, `trust_boundaries`.
- `0014_enterprise_workbench`: add `business_goals`, `business_processes`,
  `architecture_principles`, `organization_roles`.
- `0015_integration_designer`: alter `integrations` (pattern, status, spec JSON, interface
  links).
- `0016_traceability`: only additional indexes on `architecture_relationships` if needed.

Follow `0011_import_provenance.py` style: `json_type = JSON().with_variant(JSONB(),
"postgresql")`, partial indexes with `sqlite_where` (tests run on SQLite), composite
`(id, tenant_id)` FKs, complete `downgrade()`.

---

## 8. Required API changes

All workspace-scoped, `get_auth_session` + `require_csrf`, tenant via
`get_accessible_workspace`, discipline gating mirroring `_enabled`.

**Information** (`api/app/architecture/information.py`, new router):
- `GET /workspaces/{id}/information/model?state_id=` — effective entities + children +
  relationships (membership/overrides applied).
- `POST/PATCH/DELETE .../information/entities/{entity_id}/attributes[/{attribute_id}]`
  (writes canonical child + membership row when authored in a candidate).
- `POST/PATCH/DELETE .../information/relationships` (ER edges).
- `PUT .../information/attributes/{attribute_id}/realization` — create/reuse
  `catalog_object_ref`/`catalog_field_ref` registry rows and write `realizes`.

**Solution** (`api/app/architecture/solution.py`):
- `GET .../solutions/{solution_object_id}/design?state_id=`.
- CRUD for components, interfaces, operations, repositories; `PUT
  .../interfaces/{id}/provide|require`; drill-down
  `GET .../solutions/{id}/components/{component_object_id}`.

**Enterprise** (`api/app/architecture/enterprise.py`):
- CRUD for goals/processes/principles/roles; link endpoints writing canonical relationships.
- `GET .../enterprise/capability-map`, `.../process-impact?state_id=`,
  `.../application-support?state_id=`, `.../strategy-trace`.
- `GET .../states/{candidate_id}/impact?baseline=current` (shared diff).

**Integration** (extend `api/app/integrations/routes.py` + `integration_design.py`):
- Extend `IntegrationCreate/Update/GraphUpdate/Response` additively for `pattern`,
  `implementation_status`, `specification`, interface links (bounded, `extra="forbid"`
  preserved).
- `GET .../integration-design/landscape?state_id=`,
  `GET .../integration-design/{integration_id}/flow`.
- Mapping/transform/test continue to use the existing endpoints.

**Traceability** (Slice 5, `api/app/architecture/traceability.py`):
- `GET .../architecture-graph?state_id=` — unified canonical graph with
  `used_in_disciplines` and state membership.
- `GET .../trace?object_id=&direction=&depth=` — canonical edges + derived edges.
- `GET .../objects/{object_id}/usages`.

Register new routers in `api/app/main.py`.

---

## 9. Required frontend editors and views

New `web/src/workbench/` module:
- `WorkbenchHost.tsx` — keeps `ArchitectureTopBar`, discipline tabs, state selector, save
  status; routes to the discipline's specialized editor (replaces the single generic render
  inside the `ArchitectureCanvas` host).
- `useArchitectureModel.ts` — shared loader (systems, architecture objects, canonical
  relationships, catalog objects/fields, integrations, states) + save queue.
- `architectureModel.ts` / `workbenchTypes.ts` — typed canonical graph + effective-design
  resolver (server-provided effective children; client only merges node scalar overrides as
  today).

Per discipline (specialized editors — see §1.1):
- **InformationWorkbench** — ER modeler: `InformationERCanvas.tsx`,
  `InformationEntityNode.tsx` (attributes inline with type/required/key badges),
  `InformationRelationshipEdge.tsx` (crow's-foot cardinality), `AttributeEditorPanel.tsx`,
  `RealizationPanel.tsx` (catalog object/field picker → registry refs).
- **SolutionWorkbench** — hierarchical modeler: `SolutionContextNode`, `ComponentNode`,
  `InterfaceNode` (provided/required sockets), `RepositoryNode`, `TrustBoundaryNode`,
  `DeploymentNode`; drill-down breadcrumb; reuse `solutionBoundaryGeometry`; dynamic view
  reuses `SequenceDiagram`/`scenarioSequenceLayout`.
- **EnterpriseWorkbench** — capability/process/strategy modeler: Goal, Requirement,
  Capability, Process, Role, Principle nodes; capability map; strategy-to-execution trace;
  application support; Current-vs-Candidate impact diff.
- **IntegrationWorkbench** — contract/message-flow modeler: Landscape, Interface & contract,
  Message flow, Transformation & mapping, Scenario/sequence, Test & conformance; deep-links
  into the existing `IntegrationWorkspace` for the same `Integration` row.

Shared: `components/architecture/ObjectTracePanel.tsx` (in every inspector) and
`TraceView.tsx`.

---

## 10. How cross-discipline traceability works

- Explicit typed edges live in `architecture_relationships` (registry IDs both ends).
- **Derived edges** (never duplicated): entity→attribute and interface→operation from parent
  FKs; solution→application from `solution_members`; attribute→contract mapping via
  `integration_field_refs`; contract→mapping via graph edge ids; contract→test via
  `scenarios.document.contractIds` + dry-run coverage + `revision`.
- `GET .../architecture-graph` and `GET .../trace` merge stored + derived edges and annotate
  each node with incoming/outgoing relationships, disciplines that render it,
  Current/Candidate/Target membership, governing principles/decisions, physical
  implementation refs, and test/evidence. `ObjectTracePanel` renders the summary;
  `TraceView` renders the full chain with deep links that switch workbench + select object.

---

## 11. Current / Candidate / Target isolation

- Canonical rows are state-independent; canvas membership/layout is per `ArchitectureState`.
- Direct canonical edits are allowed only when an object is **not** a node in Current
  (existing rule at `architecture/objects.py:314-325`); otherwise edits become bounded scalar
  overrides on the candidate node.
- Child objects (attributes/operations) use `architecture_state_members` + bounded
  `property_overrides` and `created_in_state_id` (§6); no child arrays in overrides.
- Effective design is computed server-side for the requested state.
- Target behaves like Candidate but flagged. `include-objects` remains the only Current
  enrichment path.

---

## 12. Phase 3 imports connection

- Imported systems → Enterprise applications, Solution members, Integration endpoints (by
  canonical ID; no copies).
- Imported `information_objects` (owner/authoritative system/classification) → conceptual
  entities; attributes are authored and realized to imported catalog objects/fields in the
  Information workbench.
- Imported `solution_boundaries` + `solution_members` → Solution context/membership.
- Imported `integrations` (empty graphs) → Integration workbench contracts to flesh out via
  the existing mapping/test engine.
- `include-objects` already places imported objects on a state; workbenches read that
  membership. Optional later extension (out of scope): `information_attribute` import kind.

---

## 13. Migration & compatibility strategy

- All migrations additive; no removals; complete `downgrade()`.
- Generic canvas keeps working; new kinds get fallback rendering/filtering and are hidden
  from palette paths they don't belong to. Workbenches are additional editors.
- State JSON backward-compatible (`extra="ignore"`; `relationship_id` optional). New
  membership/override data lives in dedicated tables, not in existing JSON blobs.
- Existing tests are the preservation gate.

---

## 14. Specialized-editor mandate (correction 4, restated)

The generic architecture-card renderer (`ArchitectureOccurrenceNode` /
`ArchitectureBoundaryNode`) must not remain the primary editor for Enterprise, Information,
Solution, or Integration. Each discipline is rendered by its specialized editor listed in
§1.1 and §9; the generic renderer is retained only as a systems/integration overview.

---

## 15. Implementation sequence (vertical slices) + acceptance criteria

### Slice 1 — Core Information Modeler
Files: `api/alembic/versions/0012_information_modeler.py`;
`api/app/models/architecture_object.py` (registry ref columns, `information_attributes`,
`architecture_relationships`, `architecture_state_members`);
`api/app/architecture/{schemas,information}.py`; `api/app/main.py`;
`web/src/workbench/{WorkbenchHost,useArchitectureModel,architectureModel}.tsx|ts`,
`InformationWorkbench.tsx`, `InformationERCanvas.tsx`, `InformationEntityNode.tsx`,
`InformationRelationshipEdge.tsx`, `AttributeEditorPanel.tsx`, `RealizationPanel.tsx`;
tests `api/tests/test_information_modeler.py`, `InformationEntityNode.test.tsx`.

Acceptance (browser):
- Entity blocks render inline attributes with data type, required/optional, and key/identifier
  badges; add/edit/delete/reorder attributes inline.
- Draw entity relationships with 1:1, 1:N, M:N cardinality (crow's-foot labels); persisted.
- Map a logical attribute to an existing Catalog object/field; realization uses registry
  reference rows; **no new catalog rows are created** (assert field/object counts unchanged).
- Effective children isolate correctly between Current and Candidate (candidate add/override
  never alters Current; no attribute arrays in `candidate_overrides`).
- Existing suites green.
Deferred from this slice (see §16): ownership, stewardship, classification, quality, and
lineage views.

### Slice 2 — Solution Designer
Files: `0013_solution_designer.py`; component/interface model changes;
`interface_operations`, `data_repositories`, `deployment_nodes`, `trust_boundaries`;
`api/app/architecture/solution.py`; `SolutionWorkbench.tsx` + specialized nodes +
drill-down breadcrumb; tests.

Acceptance: context view lists boundary + actors/external systems + members; drill-down
Solution→component→interface→operation/event with stable object IDs (no duplicates);
responsibilities editable; provided vs required interfaces are distinct elements with typed
links; repository/deployment/trust views; dynamic sequence renders from operations; candidate
isolation.

### Slice 3 — Enterprise Workbench
Files: `0014_enterprise_workbench.py`; new enterprise tables;
`api/app/architecture/enterprise.py` + impact endpoint; `EnterpriseWorkbench.tsx` + node
renderers + impact/diff view; tests.

Acceptance: create/link goals, requirements, capabilities, processes, roles, principles;
capability map; process/value-stream impact; strategy-to-execution trace
(goal→requirement→capability→process→application); application-support map;
Current-vs-Candidate impact diff with affected systems; risks/gaps/dependencies surfaced.

### Slice 4 — Integration Designer
Files: `0015_integration_designer.py`; `integrations` model/schemas extension;
`api/app/integrations/{routes,integration_design,schemas}.py`; `IntegrationWorkbench.tsx` +
flow renderer + deep links to the existing editor; tests. **No second mapping/scenario/test
engine.**

Acceptance: landscape of producers/consumers/interfaces/operations; interface & contract
view; message flow with request/success/error; transformation & mapping view opens the
existing Mapping & Tests on the same contract; pattern/retry/timeout/idempotency/security
persisted and validated; scenario/sequence and test/conformance show real dry-run/revision
status.

### Slice 5 — Cross-discipline traceability (+ deferred Information views)
Files: `0016_traceability.py` (indexes); `api/app/architecture/traceability.py` + unified
graph/trace/usages endpoints; `ObjectTracePanel.tsx`, `TraceView.tsx`, `workbenchTypes.ts`;
wire into all inspectors; tests. Deferred Information views land here: Information ownership/
stewardship, classification/sensitivity, and the Information lineage view (attribute→field→
contract via traceability).

Acceptance: from any object see incoming/outgoing relationships, disciplines using it, state
membership, related decisions/constraints, physical refs, tests/evidence; full chain
Goal→…→Test with deep-link navigation into the correct workbench; unified graph + trace
endpoints covered by tests; Information ownership/classification/lineage views available and
derived from canonical data.

**Validation gate each slice:** `make check` (ruff, pytest, `tsc --noEmit`, vite build,
compose config) + `npm test`, plus a browser walkthrough of the slice's acceptance list.

---

## 16. Release (deferred)

Release handling is **explicitly out of the implementation sequence** and happens only after
Phase 4 is fully implemented and reviewed. At that time: decide the alpha increment per
`AGENTS.md` (never a major/1.0.0 bump), synchronize `web/package.json`, `api/app/main.py`,
`api/pyproject.toml`, add the `CHANGELOG.md` entry, and create a pre-release tag. Update
`docs/user-guide.md`, `docs/api-plan.md`, `docs/data-model.md`,
`docs/implementation-log.md`, `SYSTEM_CAPABILITIES.md`, and `README.md` as part of that
review. The Phase 3 (0.2.0-alpha) imports work in the working tree should be committed/
released first.

---

## 17. Risks

- **Catalog:** registry-reference FKs must respect archive safeguards
  (`api/app/catalog/service.py`); guard `catalog_field_ref`/attribute realization against
  field/object archive; keep all schema changes nullable/additive.
- **Canvas:** `ArchitectureCanvas.tsx` is large; extract the shared model loader without
  behavior change; ensure new kinds have fallback rendering/filtering so sub-elements never
  appear as cards.
- **Contracts/mappings:** extend integration schemas additively without changing
  `GraphDocument` handling or `integration_field_refs` semantics; the engine is untouched.
- **Scenarios/tests:** read-only reuse; no document changes; keep evaluation/dry-run green.
- **State JSON growth:** bounded membership `property_overrides` and integration
  `specification` validators prevent oversized rows.
- **Phase 3 uncommitted:** migrations chain from `0011`; the 0.2.0-alpha entry is not yet
  labeled/released.

---

## 18. Testing strategy

- Mirror `test_architecture_states.py` fixtures (SQLite, `StaticPool`, FK pragma, CSRF).
  New coverage: attribute CRUD + realization with no catalog duplication; registry-reference
  dedup and integrity (deleting a referenced field cannot orphan an edge); ER cardinality
  persistence; `architecture_state_members` effective-child isolation (candidate vs Current,
  no child arrays in overrides); provided/required interface distinctness; drill-down ID
  stability; impact diff correctness; integration spec validation bounds; trace traversal
  across stored + derived edges; tenant/CSRF negatives.
- Frontend vitest/jsdom: entity-node rendering with attributes, cardinality edge labels,
  workbench editor switching, trace panel, deep-link navigation; keep `npm test` /
  `npm run check` green.
- Preserve `test_catalog.py`, `test_integrations.py`, `test_scenarios.py`, `test_imports.py`,
  `test_workspaces.py`.
