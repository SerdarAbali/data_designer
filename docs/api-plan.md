# Proposed API boundaries and dry-run contract

This document defines a first REST API boundary for implementation planning. Exact URL naming and pagination conventions should be confirmed in Phase 1 and then kept consistent. All routes except health/login are authenticated; domain data is scoped to the tenant derived from the server-side session.

## 1. API areas

| Area | Responsibility | Boundary rule |
|---|---|---|
| Health | API/database readiness | Does not disclose configuration or credentials |
| Auth | Login/logout/current user | Opaque server-side session, CSRF protection for mutations |
| Catalog | Systems, objects, fields | Generic CRUD; no vendor-specific routes or schema enums |
| Integrations | Endpoints, sample rows, graph, dependencies | Graph save validates stable field references and current revision |
| Simulation | Dry-run of saved/draft graph | Calls the pure engine; no external connector writes |
| Landscape/analysis | Read projections, conflicts, dependency health, positions | Derived data; tenant-safe and explainable |
| Connectors (future) | Discovery/binding and optional execution capabilities | Separate adapters; core API/domain remains functional without one |

Use consistent pagination, request IDs, error envelopes, and validation codes. API-generated TypeScript types or schema contract tests must prevent frontend/backend drift.

## 2. Catalog and integration boundaries

Catalog routes expose stable UUIDs and current mutable labels/names. Client-supplied tenant IDs are rejected; tenant context comes from the authenticated session. Lists omit archived rows by default and use bounded `limit`/`offset`; detail and restore behavior are explicit. The current routes are:

```text
GET, POST   /api/catalog/systems
GET, PATCH, DELETE /api/catalog/systems/{systemId}
POST        /api/catalog/systems/{systemId}/restore
GET, POST   /api/catalog/systems/{systemId}/objects
GET, PATCH, DELETE /api/catalog/objects/{objectId}
POST        /api/catalog/objects/{objectId}/restore
GET, POST   /api/catalog/objects/{objectId}/fields
GET, PATCH, DELETE /api/catalog/fields/{fieldId}
POST        /api/catalog/fields/{fieldId}/restore
```

All mutations require the authenticated session's CSRF token. Deletes archive rows and system/object archives transactionally archive active descendants; restores operate on one row at a time. Active-name conflicts return `409`. Catalog archive checks reject referenced endpoints/fields and return safe same-tenant reference summaries.

Integration creation accepts source and target system/object IDs, metadata, and bounded sample rows. Backend checks that each object belongs to the stated system and tenant. Graph JSON uses `version: 1`. A lightweight current revision may be used for optimistic concurrency (`If-Match` or `expectedRevision`) and returned after save; it is not a graph version. Graph validation responses identify the exact node/edge/port path with a stable code. A successful save persists the current graph and maintains whatever current field-reference data is needed for safe deletion and conflict visibility. MVP does not require graph-history snapshots or history retention.

The current integration API is:

```text
GET, POST       /api/integrations
GET, PATCH, DELETE /api/integrations/{integrationId}
PUT             /api/integrations/{integrationId}/graph
GET, POST       /api/integrations/{integrationId}/dependencies
DELETE          /api/integrations/{integrationId}/dependencies/{downstreamIntegrationId}
GET             /api/integrations/architecture
```

`GET /api/integrations/architecture` returns derived route health (draft, attention, healthy), upstream dependency details, and target-field conflicts. Mutating requests send the `dd_csrf` cookie value in the `X-CSRF-Token` header.

Create accepts tenant-owned source/target system and object IDs, name, optional description, generic trigger configuration, `version: 1` request graph, optional `version: 1` `response_graph`, `interaction_type`, and at most 100 source sample rows/64 KiB serialized. `interaction_type` is `ONE_WAY` by default and may be `REQUEST_RESPONSE` or `ASYNC_CALLBACK`. Empty graph nodes/edges are accepted when an integration is first created. Graph saves require `expected_revision`; they may atomically update both graphs, interaction type, name, and sample rows. Every successful integration or graph update increments the current revision. A stale revision returns `409` with `code: "revision_conflict"` and the current revision. Dependency endpoints represent upstream → downstream and reject cycles and duplicates.

Graph node/edge IDs are UUIDs. Edge endpoint keys use the master-spec camelCase spelling (`sourceNodeId`, `sourcePortId`, `targetNodeId`, `targetPortId`); field ports use `field:<field-uuid>`. The server validates active ownership against the selected endpoint object and persists only stable IDs, never display names. Direct source-to-target field connections require equal generic `data_type`; transformed type compatibility is checked by the engine. Graph save validates operation-specific node configuration against the engine's allowlist before persistence. Graph errors return stable codes with JSON paths. Limits are 200 nodes, 500 edges, 256 KiB per graph, and 8 KiB per node configuration. Mutations use session authentication and CSRF protection. The current request/response graph and sample field-reference index is updated in the same transaction, allowing catalog deletion to return a same-tenant `409` until its active integrations are archived or their references are removed. `response_graph` uses the same document structure as `graph`, but is validated from the integration's target object to its source object; display names do not replace field UUID references.

### Design-time scenarios

```text
GET, POST       /api/scenarios            # ?scope=all|contract|landscape, ?integration_id=
POST            /api/scenarios/evaluate
GET, PUT, DELETE /api/scenarios/{scenarioId}
```

`GET /api/scenarios?integration_id=X` returns scenarios scoped to contract X together with end-to-end scenarios that reference X. Create accepts `scope_integration_id` (optional), `name`, `category`, `description`, and the `version: 1` document. Updates require `expected_revision` and return `409` with `code: "revision_conflict"` when stale. Duplicate active names return `409`. Delete archives the row. Saving validates that every referenced system, contract, phase (allowed by the contract's interaction type), object, and field belongs to the tenant and matches the step's derived sender/receiver; violations return `422` with `code: "invalid_scenario_reference"` and an `issues` list. References that were valid when saved and were archived later are tolerated and reported as missing references.

`POST /api/scenarios/evaluate` accepts an unsaved document and runs each contract step's `sampleValues` through the same engine used by dry-run, against the referenced contract's saved phase graph (`graph`, `response_graph`, or `error_response_graph`). It returns a per-step outcome (`ok`, `mismatch`, `failed`, `skipped`, `missing_reference`, `not_evaluated`), produced values, mismatches against `expectedValues`, assertion statuses, and a summary. It never persists data, changes a contract, or contacts an external system.

## 3. Dry-run request

Endpoint:

```http
POST /api/integrations/{integrationId}/dry-run
Content-Type: application/json
```

Proposed body:

```json
{
  "expectedRevision": 7,
  "graph": null,
  "rows": [
    { "rowId": "sample-1", "values": { "<source-field-uuid>": " Ada " } }
  ],
  "responseGraph": null,
  "responsePayload": [
    { "rowId": "response-1", "values": { "<target-field-uuid>": "remote-123" } }
  ],
  "options": { "includeTraceValues": true }
}
```

- `expectedRevision` may be supplied to prevent unintentionally simulating against a stale saved integration; a mismatch returns `409` with `code: "revision_conflict"`. The API also accepts the repository's existing `expected_revision` spelling.
- `graph` is omitted/null to use the saved graph; an editor may provide an unsaved draft graph. Draft graph is validated against the saved integration endpoints/current catalog and is never persisted by simulation.
- `rows` may be supplied for this run, bounded to 100 rows/64 KiB, and keyed by source field UUID. If omitted/null, the integration's saved sample rows are used. Unknown, inactive, or non-source field IDs are validation errors.
- `responseGraph` may be supplied as an unsaved response-graph override; it is validated with endpoint ownership reversed. `responsePayload` is optional, bounded to 100 rows/64 KiB, and keyed by target-object field UUID. It is used only for non-one-way integrations; it is mock simulation input, not a live response.
- Trace values are opt-in using `options.includeTraceValues` and must not be logged. Any row/byte/graph/time limit failure is explicit.

The engine input is assembled server-side from the validated graph and current generic catalog metadata. The browser never computes transformation results.

## 4. Dry-run response

Successful execution returns `200` with:

```json
{
  "integrationId": "integration-uuid",
  "version": 1,
  "revision": 7,
  "summary": { "total": 1, "ok": 1, "skipped": 0, "failed": 0 },
  "rows": [
    {
      "rowId": "sample-1",
      "outcome": "ok",
      "targetValues": { "<target-field-uuid>": "ada" },
      "errors": [],
      "trace": [
        {
          "nodeId": "node-uuid",
          "nodeType": "fx",
          "inputs": { "input": "<redacted-or-value>" },
          "outputs": { "output": "<redacted-or-value>" },
          "outcome": "ok"
        }
      ]
    }
  ],
  "traceTruncated": false,
  "requestOutcomes": [
    {
      "rowId": "sample-1",
      "rowIndex": 0,
      "outcome": "ok",
      "targetValues": { "<target-field-uuid>": "ada" },
      "errors": [],
      "trace": [],
      "traceTruncated": false
    }
  ],
  "responseOutcomes": [
    {
      "rowId": "response-1",
      "rowIndex": 0,
      "outcome": "ok",
      "targetValues": { "<source-field-uuid>": "remote-123" },
      "errors": [],
      "trace": [],
      "traceTruncated": false
    }
  ],
  "responseSummary": { "total": 1, "ok": 1, "skipped": 0, "failed": 0 },
  "responseTraceTruncated": false
}
```

`rows`, `summary`, and `traceTruncated` retain their existing request-side
meaning for compatibility. `requestOutcomes` mirrors `rows`. Response outcomes
are empty and their summary is all zeroes when no response phase ran. Each phase
has independent row outcomes, target values, errors, traces, and truncation.

Use stable field/node/port IDs and structured error codes. Include a row result for every submitted row so counts reconcile; each row also includes `rowIndex` and `traceTruncated`. Trace values are redacted by default. An invalid graph/request is a normal validation error and does not masquerade as a successful row result. Input/graph/output size limits return an explicit `413`; other engine validation and limit failures return `422`. Use documented HTTP statuses for unauthenticated, forbidden/not-found, revision conflict, validation failure, throttling, and internal failure. Never return stack traces, credentials, or database details.

## 5. Security, bounded work, and failure behavior

- Require authenticated tenant context for all domain and simulation routes.
- Apply login rate limits, request-body limits, row count/bytes limits, graph complexity bounds, and simulation time budgets.
- Return explicit errors instead of success-shaped fallbacks. Keep raw sample values out of logs; give each request a correlation ID.
- Do not trust arbitrary forwarded headers; configure known reverse proxies explicitly.
- Apply CSRF protection to cookie-authenticated state-changing requests, restrictive CORS/host allow-lists, secure cookie settings, and secure secret configuration.
- The dry-run endpoint performs no writes to connected systems and creates no durable execution record in MVP.
- Persist only the bounded sample rows explicitly saved on the integration; do not create a separate run-history/sample-data subsystem for MVP.

## 6. Contract verification

OpenAPI/schema tests cover request and response shapes, authorization, tenant isolation, revision conflicts, stable error codes, limits, and field-ID references. A full API integration test submits sample rows and verifies target output, row counts, and node traces against engine golden fixtures.
