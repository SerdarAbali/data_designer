# Proposed graph and transformation-engine contract

The engine is a deterministic Python component with no dependency on FastAPI, SQLAlchemy, PostgreSQL, React, HTTP, or filesystem APIs. API code resolves database rows into plain typed engine inputs, validates graph/catalog references, invokes the engine, and serializes the result.

## 1. Graph document

Use the master-spec graph terminology and initial schema version:

```json
{
  "version": 1,
  "nodes": [
    { "id": "source-node-uuid", "type": "source", "position": { "x": 0, "y": 0 }, "config": {} },
    { "id": "transform-node-uuid", "type": "fx", "position": { "x": 240, "y": 0 },
      "config": { "function": "lower", "errorPolicy": "fail" } },
    { "id": "target-node-uuid", "type": "target", "position": { "x": 480, "y": 0 }, "config": {} }
  ],
  "edges": [
    { "id": "source-edge-uuid", "sourceNodeId": "source-node-uuid", "sourcePortId": "field:<source-field-uuid>",
      "targetNodeId": "transform-node-uuid", "targetPortId": "input" },
    { "id": "target-edge-uuid", "sourceNodeId": "transform-node-uuid", "sourcePortId": "output",
      "targetNodeId": "target-node-uuid", "targetPortId": "field:<target-field-uuid>" }
  ]
}
```

Node and edge IDs are stable UUIDs. Only server-supported node types and bounded JSON configuration are accepted at graph-save time; operation-specific configuration is validated by the engine boundary before execution. Source and target field references occur in field-port IDs, not names or labels. Source node output ports are generated from active source-object fields; target node input ports are generated from active target-object fields. The initial editor contract uses `input` and `output` ports for transformation nodes and an `output` port for `constant`; node-specific config/arity is defined alongside engine operations. UI coordinates are presentation-only and do not affect execution.

Initial allowlist: `source`, `target`, `constant`, `fx`, `concat`, `ifelse`, `map`, `coalesce`, `lookup`, `filter`, `validate`. The graph-save API checks node/edge IDs, node types, basic endpoint/config shape, edge endpoints/directions, field ownership, port compatibility, duplicate target-field assignments, graph cycles, and configured complexity bounds. Engine execution additionally validates operation-specific configuration. Errors carry stable codes and JSON paths.

## 2. Engine input and output

The implementation is `app.engine.run_graph`. The engine package uses only the Python standard library and accepts plain mappings/rows plus immutable field specifications; API routes resolve ORM rows and parse the persisted graph before calling it. The public boundary is:

```python
run_graph(
    graph: Mapping[str, JsonValue],
    source_fields: Sequence[FieldSpec],
    target_fields: Sequence[FieldSpec],
    rows: Sequence[Mapping[str, JsonValue]],
    limits: EngineLimits | None = None,
) -> SimulationResult
```

`FieldSpec` contains `id`, free-form `data_type`, `required`, `nullable`, `has_default`, and `default_value`. Row shape is `{ "rowId": "...", "values": { "<source-field-uuid>": value } }`. Source/target field IDs are canonical UUID strings. The engine independently checks graph structure and input bounds rather than trusting ORM or framework objects.

Output contains:

- Per-input-row stable index/ID, outcome `ok | skipped | failed`, and target values keyed by target field UUID. A result is returned for every input row.
- Aggregate counts for each outcome and total processed rows.
- Structured errors with stable code, row index, node ID, safe message, and a `recovered` flag; no stack trace or raw sensitive sample value.
- Ordered node trace entries per row, including node ID/type, input/output port IDs, safe value representation, and error/skip state.
- Explicit per-row and aggregate trace truncation indicators. If serialized result output exceeds its hard cap, execution returns an explicit `EngineLimitError`, never a partial success.

All execution is side-effect-free and deterministic for the same normalized graph, field specs, rows, and options. It cannot execute user-supplied source code, perform network/filesystem access, or mutate catalog state.

### Request-response orchestration

`run_graph` remains a single-direction, integration-agnostic operation. The API
owns two-phase orchestration for `REQUEST_RESPONSE` and `ASYNC_CALLBACK`
integrations: it runs the request graph with source-object fields, target-object
fields, and source rows, then—when mock response rows are supplied—runs the
response graph with those field sets reversed. The response graph's source
ports therefore belong to the integration's target object, and its target
ports belong to the source object. Each phase returns a normal
`SimulationResult`; no external system is contacted and no request-phase output
is implicitly treated as a response payload.

The dry-run DTO preserves the existing request `rows` and `summary` properties
and adds `requestOutcomes`, `responseOutcomes`, `responseSummary`, and
`responseTraceTruncated`. If a one-way integration is simulated, or no mock
`responsePayload` is provided, response outcomes are empty with zero summary
counts. Response input rows are keyed by target-object field UUIDs and follow
the same row-count, serialized-size, validation, and trace-value controls as
request rows.

## 3. Operation and error semantics

Implement the roadmap functions and policies only: node types `constant`, `fx`, `concat`, `ifelse`, `map`, `coalesce`, `lookup`, `filter`, `validate`; `fx` functions `trim`, `title`, `lower`, `upper`, `e164`, `date`, `toInt`, `toNumber`, `toString`, `toBoolean`, `parseDate`, and `formatDate`; policies `fail`, `skip`, `default`. Explicit scalar/date converters are available to canvas connection assist.

The implemented MVP semantics are:

- Missing source keys use an internal missing sentinel distinct from explicit JSON null. Transformations that preserve a missing input keep it missing. A target field with a missing value uses its configured catalog default, otherwise fails if `required`, otherwise remains absent. Explicit null is accepted only when `nullable`; `required` means the field must be present, and does not by itself reject null. Defaults and results are checked as JSON-compatible values. Graph nodes do not implicitly coerce between types. At final target validation only, obvious scalar values may be normalized to the declared target type: numeric strings to numbers/integers (only exact integers to integer), booleans and 0/1 to boolean, and finite numbers/booleans to strings. Invalid or ambiguous values still fail validation.
- `fail` records a safe node error, marks the row failed, and stops that row. `skip` records the error, marks the row skipped, and stops that row. `default` requires node `defaultValue`, records a recovered error and trace outcome, substitutes the value, and continues. A `filter` result of false marks the row skipped without an error.
- `constant` emits `config.value`. `fx`, `map`, `lookup`, `filter`, and `validate` take one input. `concat` takes one or more inputs and joins string values in edge-list order; missing and null contribute an empty string. `ifelse` takes condition/true/false inputs in edge-list order and requires a boolean condition. `coalesce` returns the first value that is neither missing nor null, or null when none exists.
- `map` requires an exact string-keyed `mapping`; string inputs match exactly, while boolean and numeric inputs are converted to their canonical text representation only for the key lookup. An unmatched key returns optional `fallback`, otherwise the original input. `lookup` uses a bounded, local string-keyed `table`; a miss returns optional `fallback`, otherwise it is an operation error. Neither accesses another system.
- `validate` accepts `rules` containing any of `required` (boolean), `type` (supported generic type), `min`/`max` (numeric bounds), and `allowedValues` (exact JSON values). It returns the input unchanged when all supplied rules pass.
- Supported generic target types are `string`/`text`, `number`/`float`/`decimal`, `integer`/`int`, `boolean`/`bool`, ISO `date`, ISO `datetime`, `object`/`json`, and `array`. Integer and boolean are not conflated. Unsupported `data_type` values fail explicitly at target validation. Direct source-to-target connections require the same case-insensitive generic `data_type` value.
- `trim`, `title`, `lower`, and `upper` use Python's locale-independent Unicode string operations. `toInt` accepts integer strings and integral finite numbers; `toNumber` accepts finite numeric strings and numbers; `toBoolean` accepts booleans, 0/1, and case-insensitive `true`/`false`/`0`/`1` strings. `toString` preserves strings, converts booleans to lowercase `true`/`false`, numbers to text, and arrays/objects to compact JSON; missing and null values remain unchanged. `parseDate` requires `inputFormat`, validates an exact round-trip, and returns ISO date or datetime text. `formatDate` parses ISO date/datetime text and requires `outputFormat`; neither performs timezone conversion. The legacy `date` function still requires both formats. Timezone-aware values are rejected. `e164` accepts an international `+` number or requires explicit `countryCallingCode` for a national significant number; it strips only common visual separators and does not guess country or remove national trunk prefixes.
- Config keys are allowlisted per node; arbitrary expression/code execution is not supported. Graph edge order defines multi-input ordering and is persisted as supplied.

## 4. Execution safety and trace limits

Default limits are 100 rows; 1,000 source and target catalog fields combined; 200 nodes; 500 edges; 256 KiB serialized graph; 64 KiB serialized input rows in total; 64 KiB per value; 8 KiB per node configuration; 256 KiB cumulative trace; 1 MiB serialized output; and a two-second synchronous execution budget. Values are restricted to finite JSON types, string object keys, and nesting depth at most 64. `EngineLimits` can lower or raise these explicit caps for a caller. Exceeding row/field/node/edge/input/output/time limits raises a typed `EngineLimitError`; excess trace is omitted with explicit truncation flags. The engine remains synchronous and pure; do not add workers or job infrastructure absent measured need.

Trace values are for local debugging and may include user sample data. Never emit them to application logs or telemetry by default. The API may omit or mask values when configured, while retaining node/port/outcome linkage and accurate counts.

## 5. Required verification

- Unit test each function, node, coercion, null/missing case, and error policy.
- Golden fixture tests verify full outputs/traces for representative graphs.
- Property tests verify determinism, row-count accounting, no unknown output field IDs, and error-policy invariants.
- API contract tests verify DTO JSON serialization and mapping from resolved catalog data.
- Import-boundary test proves the engine runs without database, web framework, UI, or filesystem imports.
- Tests verify `version: 1` graph validation and explicitly reject unsupported graph versions. Add graph-version migration tests only when a later version is introduced.
