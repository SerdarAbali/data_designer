# Proposed data model and architectural decisions

This document records implementation defaults where the authoritative [MASTER-SPEC.md](../MASTER-SPEC.md) leaves details open. The core model is deliberately generic: provider names may appear as user-entered values or optional adapter metadata, never as entity types or core execution branches.

## 1. Dynamic catalog: System → Object → Field

Use tenant-scoped relational tables:

```text
tenants 1 ── * systems
systems 1 ── * objects
objects 1 ── * fields
```

The initial internal deployment has one user and one lightweight tenant/workspace boundary for data isolation. It does not include collaboration, roles, invitations, organizations, or SaaS administration. Each catalog row has an immutable UUID primary key, tenant ownership, created/updated timestamps, and an archive timestamp. `systems.kind`, `objects.origin`, `fields.origin`, and `fields.data_type` are strings constrained by generic validation, not vendor-enumerations. Keep arbitrary optional adapter attributes in bounded JSONB `metadata`; do not make metadata a substitute for typed relationships or IDs.

Suggested generic attributes:

| Entity | Generic attributes |
|---|---|
| System | `name`, `description`, `kind`, `icon`, `color`, landscape `position`, `binding_state`, metadata |
| Object | `system_id`, `name`, `label`, `description`, `external_identifier`, `origin`, metadata, ordering |
| Field | `object_id`, `name`, `label`, `description`, `data_type`, `required`, `nullable`, `default_value`, `external_identifier`, `origin`, metadata, ordering |

Enforce tenant consistency using composite foreign keys (for example `(object_id, tenant_id)` referencing the owning object) as well as service-level tenant filters. Scope active-name uniqueness to tenant/parent. Treat names/labels as mutable presentation and source metadata, not globally unique identifiers.

The catalog stores `data_type` as a bounded, non-empty string rather than a provider enum; the demo fixture uses generic values such as `string` and `number`. The later engine phase must explicitly reject types or conversions it does not support instead of silently coercing values. Keep nullability separate from whether a row value is missing.

The current API assigns stable integer ordering to objects and fields, while a system's optional landscape position is a JSON object of finite coordinates. `metadata` is arbitrary JSON capped at 16 KiB. Active names are unique within their tenant or parent; archived names may be reused.

## 2. Stable field identity and graph references

- Generate field UUIDs on creation and never change them on rename, label edit, reorder, or type edit.
- A graph port encodes a field UUID (for example `field:<uuid>`); source and target node context determines whether it is an input or output.
- Keep a port label only for display; never persist a field name as the canonical reference.
- Validation confirms that the UUID belongs to the integration's selected source or target object, is active, and has a compatible direction/type.
- A metadata rename updates rendered labels after refetch without rewriting graph edges. Type changes trigger compatibility revalidation.

## 3. Delete/archive semantics

Use **archive** semantics for catalog delete APIs (`deleted_at`); do not cascade physical deletion through integration records:

- Archiving a field is rejected with `409 Conflict` while the active graph reference table identifies any integration using it. Return safe IDs/names for integrations in the same tenant so the user can repair mappings first.
- Archiving an object is rejected while it is an active source/target endpoint or any field is actively referenced. Otherwise archive the object and its fields transactionally.
- Archiving a system is rejected while any contained object is used as an active endpoint or any contained field has an active graph reference. Otherwise archive its catalog descendants transactionally.
- System/object archive marks active descendants archived in the same transaction. Restore is explicit per row: restoring a parent does not implicitly restore descendants. Archived records disappear from ordinary selectors/list responses; retained IDs and metadata keep future integration graph references intelligible. Restore is allowed only when active-name constraints permit.
- Hard deletion is an administrative retention/maintenance operation outside normal CRUD, not the UI/API delete behavior.

`integration_field_refs` is a derived index for the **current** saved request and response graphs, updated atomically with graph save. It has restrictive FKs to fields and integrations. Historical graph snapshots remain JSON and keep UUID references; archived rows remain available for historical inspection. Transaction/locking behavior prevents a field from being archived between graph validation and reference persistence.

## 4. Tenant, user, and integration relationships

The initial deployment provisions one tenant and one user but scopes every request and domain row by tenant from the outset. There is no collaboration, role/permission matrix, or multi-tenant signup in MVP. Never trust a tenant ID supplied by the browser; derive it from the authenticated session.

`integrations` stores source/target system and object IDs to match the product contract. Composite foreign keys enforce that each object belongs to its stated system and tenant. An integration has a request graph (`graph`), a response graph (`response_graph`), an `interaction_type` (`ONE_WAY`, `REQUEST_RESPONSE`, or `ASYNC_CALLBACK`), bounded source sample rows, trigger configuration, and a monotonically increasing current revision. The request graph maps source fields to target fields; the response graph maps fields on the existing target object back to fields on the existing source object. Active integration names are unique within a tenant. `ONE_WAY` remains the creation default.

`integration_dependencies` points from an upstream integration to a downstream integration and is tenant constrained. Self-edges, duplicates, and dependency cycles are rejected. Archiving an integration removes its active field references and dependency edges while retaining the integration row and graph document.

`integration_field_refs` is a derived index for field UUIDs referenced by current request/response graph edges or stored source sample rows. It stores integration, field, owning object, tenant, and direction (`source`, `target`, `response_source`, or `response_target`); the response directions refer to the reversed endpoint orientation. Composite foreign keys protect ownership. Graph and sample-row saves replace this index in the same transaction as the saved data and revision. Catalog field/object/system archives query this table and active integration endpoints, return a same-tenant `409` reference summary, and serialize with graph writes using row locks. This table is only a current-reference/deletion guard, not graph history.

Integration sample rows use a stable `row_id` and a `values` object keyed by source field UUID. The API accepts up to 100 rows and 64 KiB serialized input. Trigger configuration is generic bounded JSON and does not implement scheduling.

### Design-time scenarios

`scenarios` stores documentation-only interaction scenarios. A row has `tenant_id`, nullable `scope_integration_id` (set for a Contract Designer scenario, `NULL` for a Landscape end-to-end scenario), `name` (unique among active rows per tenant), `category` (`happy_path`, `alternative`, `error`), optional `description`, a bounded JSON `document` (`version: 1`), a `revision` for optimistic concurrency, and `deleted_at` for soft archive. The scope foreign key is composite with `tenant_id`. Contract-scoped and end-to-end scenarios share this table and document format.

The document holds preconditions, trigger, participants (catalog systems or free-text actors), participating `contractIds`, before/after state entries (participant, object, and sample values keyed by field UUID), an ordered item tree, assertions, and notes. Items are steps (`contract`, `self`, `actor`) or `alt`/`opt`/`loop` blocks with guarded operands (at most three nested levels, 200 steps, 256 KiB). A contract step stores only `contractId`, `phase`, optional label/notes, `sampleValues`, and `expectedValues`; its sender/receiver are derived from the referenced integration and phase, so a scenario never copies or changes a contract definition. Scenarios add no rows to `integration_field_refs` and do not block catalog or contract archives. A reference that later becomes archived stays in the document and is reported as a missing reference.

## 5. Versioned graph persistence

Use the master-spec graph terminology:

1. `version` describes the JSON graph format; the initial format is `version: 1`.
2. A lightweight current integration `revision` may be used for optimistic concurrency (`expectedRevision` / ETag). It is not a graph schema version.

Persist the current graph JSONB on the integration. A save validates the graph and, when a revision is supplied, compares it before updating the current document. Do not add immutable graph snapshots, a graph-history table, history retention, or graph migration infrastructure to the MVP. Introduce a graph format migration only when an actual later version is required.

Both persisted graphs use the master-spec shape. The `graph` property is the request/outbound mapping; `response_graph` is the response/return mapping and uses the same versioned structure, with source and target field ownership reversed at validation time:

```json
{
  "version": 1,
  "nodes": [
    {"id": "node-uuid", "type": "source", "position": {"x": 0, "y": 0}, "config": {}},
    {"id": "node-uuid", "type": "target", "position": {"x": 400, "y": 0}, "config": {}}
  ],
  "edges": [
    {
      "id": "edge-uuid",
      "sourceNodeId": "node-uuid",
      "sourcePortId": "field:<field-uuid>",
      "targetNodeId": "node-uuid",
      "targetPortId": "field:<field-uuid>"
    }
  ]
}
```

Node/edge IDs are UUIDs; the API persists camelCase edge endpoint keys in JSON. The initial allowed node types are the generic master-spec list (`source`, `target`, `constant`, `fx`, `concat`, `ifelse`, `map`, `coalesce`, `lookup`, `filter`, `validate`). Source and target field ports use `field:<uuid>`, while transformation nodes currently use `input`/`output` ports. Direct source-to-target field connections require identical generic `data_type` strings; connections through transformation nodes are validated for operation-specific input/output types by the engine phase. Graph documents are capped at 200 nodes, 500 edges, and 256 KiB; each node config is capped at 8 KiB. This phase validates topology, directions, field ownership, duplicate target assignments, cycles, and bounded JSON; operation-specific transformation config validation remains with the engine phase.

The graph and API contracts are also defined in [engine-spec.md](./engine-spec.md) and [api-plan.md](./api-plan.md).

## 6. Security and data handling

- Store only Argon2id password hashes and hash opaque session tokens at rest.
- Cookie authentication requires CSRF protection on state-changing routes; do not trust forwarded host/protocol headers unless the proxy is explicitly configured as trusted.
- Enforce tenant ownership on every lookup and mutation, including graph field IDs, landscape positions, simulations, and archived records.
- Cap `metadata`, graph JSON, sample-row count, serialized request bytes, node count/depth, and trace response size.
- Do not log credentials, session identifiers, tokens, or sample-row values. Redact request bodies by default.
- Connector secrets (future) belong in a separate encrypted credential facility or external secret store, not system metadata or graph JSON.

## Decisions applied

The catalog stores free-form bounded `data_type`, `kind`, and `origin` values; engine-supported types and conversions will be checked explicitly in the engine phase. Metadata is capped at 16 KiB. Catalog deletion is soft archive, cascading to active descendants for system/object deletion; restore is explicit per row and must satisfy active-name uniqueness. The authenticated tenant is derived from the server-side session. Active integrations and current graph field references block unsafe catalog archives. Graph history remains out of MVP.
