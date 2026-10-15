# Implementation Plan — Phase 3: Import Existing Architecture into the Shared Canonical Model

## Overview

Add one shared, guided import experience that brings existing architecture data (Systems, Information Objects, Integrations, Solutions with system membership) from Excel (`.xlsx`) or CSV into the shared canonical model, with column mapping, validation, layered matching against canonical objects, per-row decisions (use existing / create / update / skip), a full change preview, batch commit with counts, row-level error download, batch-scoped undo, provenance tracking, and a controlled follow-up step that places user-selected imported objects onto the Current architecture view.

The design deliberately **reuses what already exists** instead of building a second import framework:

- **Parsing**: the Papa Parse client-side table pipeline from `web/src/contractMappingCsv.ts` (delimiter/header detection, 1 MiB / 500-row limits, `isFormulaLike` rejection, BOM handling). Excel support is added in the same client-side pipeline via `exceljs`, producing the identical `{ headers, rows }` table shape so the rest of the wizard is format-agnostic.
- **UI patterns**: the guided wizard reuses the `ContractCsvDialog` flow (upload → column mapping → preview with row issues → confirm checkbox → apply → issue-report download) and its CSS classes (`.contract-csv-dialog`, `.csv-*` in `web/src/style.css`).
- **Issue reporting / downloads**: reuse the exported `downloadCsv()` and `issueReportCsv()` helpers from `web/src/contractMappingCsv.ts`.
- **Creation paths**: imports create records through the same SQLAlchemy models the Catalog and Architecture APIs use, so imported systems auto-register as canonical `architecture_objects` via the existing `after_insert` event in `api/app/models/architecture_object.py`, and catalog name-uniqueness, archive, CSRF, and session-auth rules apply unchanged.
- **Undo pattern**: batch undo generalizes the existing client-side "Undo import" in `IntegrationWorkspace.tsx`, but is persisted server-side per batch so it survives refresh.

All new API routes follow the established workspace-scoped pattern (`/api/workspaces/{workspace_id}/…`) with `get_auth_session` + `require_csrf`, tenant scoping via `get_accessible_workspace`, and Pydantic schemas with explicit bounds. Current/Candidate isolation, the four discipline views, contracts, mappings, transformations, tests, and existing Catalog workflows are preserved; the only deliberate, narrow exception is a new controlled "include objects into state" endpoint that can enrich the read-only Current state (see Functions).

## Types

### Backend (Pydantic, `api/app/imports/schemas.py` — new)

```python
ImportType = Literal["system", "information_object", "integration", "solution"]
RowDecision = Literal["create", "update", "use_existing", "skip"]
MatchMethod = Literal["external_id", "exact_name", "alias", "similar_name", "none"]
RowStatus = Literal["created", "updated", "matched", "skipped", "blocked", "failed"]
BatchStatus = Literal["applied", "undone", "undo_blocked"]

class ImportColumnMapping(BaseModel):
    # canonical field name -> source column header (exact header text)
    model_config = ConfigDict(extra="forbid")

class ImportPreviewRequest(BaseModel):
    import_type: ImportType
    headers: list[str]                       # <= 64 headers, each <= 200 chars
    rows: list[list[str]]                    # <= 500 rows, <= 64 cells/row, cell <= 2000 chars
    column_mapping: ImportColumnMapping
    source_filename: str = Field(max_length=255)
    sheet_name: str = Field(max_length=120, default="")

class ImportMatchCandidate(BaseModel):
    id: UUID
    kind: str                                # "system" | "information_object" | "integration" | "solution_boundary"
    name: str
    method: MatchMethod
    score: float | None = None               # similarity ratio for similar_name, else None

class ImportIssue(BaseModel):
    row: int
    column: str
    message: str

class ImportRowPreview(BaseModel):
    row_number: int                          # 1-based data row number, excluding header
    external_id: str | None
    name: str | None
    values: dict[str, str]                   # mapped canonical field -> trimmed cell value
    issues: list[ImportIssue]                # blocking problems
    warnings: list[ImportIssue]              # non-blocking (e.g. similar-name suggestion)
    matches: list[ImportMatchCandidate]      # ordered by method priority
    suggested_decision: RowDecision          # create when no match; use_existing when matched

class ImportPreviewResponse(BaseModel):
    import_type: ImportType
    rows: list[ImportRowPreview]
    blocked_count: int
    resolved_reference_counts: dict[str, int]  # e.g. {"systems_resolved": 3}

class ImportRowDecision(BaseModel):
    row_number: int
    decision: RowDecision
    target_id: UUID | None = None            # required for update / use_existing

class ImportCommitRequest(ImportPreviewRequest):
    decisions: list[ImportRowDecision]       # one per row; unknown row numbers rejected

class ImportRowResult(BaseModel):
    row_number: int
    status: RowStatus
    target_kind: str | None
    target_id: UUID | None
    message: str | None
    issues: list[ImportIssue] = []

class ImportBatchResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    source_filename: str
    sheet_name: str
    import_type: ImportType
    status: BatchStatus
    counts: dict[str, int]                   # created/updated/matched/skipped/blocked/failed
    rows: list[ImportRowResult]
    imported_at: datetime
    undone_at: datetime | None

class IncludeObjectsRequest(BaseModel):
    system_ids: list[UUID] = []
    architecture_object_ids: list[UUID] = []   # information objects / solutions
    integration_ids: list[UUID] = []
    visualize_solution_membership: bool = True

class IncludeObjectsResponse(BaseModel):
    state: ArchitectureStateResponse
    added_occurrences: int
    added_relationships: int
    skipped: list[ImportIssue]               # e.g. integration skipped because endpoint not on canvas
```

### Frontend (TypeScript, `web/src/architectureImport.ts` — new)

```ts
export type ImportKind = "system" | "information_object" | "integration" | "solution";
export type RowDecision = "create" | "update" | "use_existing" | "skip";
export type MatchMethod = "external_id" | "exact_name" | "alias" | "similar_name" | "none";

export type ImportFieldSpec = {
  key: string;            // canonical field, e.g. "external_id", "authoritative_system"
  label: string;          // UI label
  required: boolean;
  aliases: string[];      // accepted header synonyms, lowercased, e.g. ["system", "system name"]
  multiple?: boolean;     // semicolon-separated list cells (aliases, included systems)
};
export const IMPORT_KIND_FIELDS: Record<ImportKind, ImportFieldSpec[]>;

export type SheetTable = { headers: string[]; rows: string[][] };   // same shape as CsvTable
export type ParsedWorkbook = {
  filename: string;
  sheets: { name: string; table: SheetTable }[];
  issues: ImportIssue[];
};

export async function parseImportFile(file: File): Promise<ParsedWorkbook>;  // CSV -> papaparse; .xlsx -> exceljs
export function suggestColumnMapping(headers: string[], fields: ImportFieldSpec[]): Record<string, string>;
export function normalizeName(value: string): string;                // NFKC, trim, collapse whitespace, casefold
export function buildTemplateCsv(fields: ImportFieldSpec[]): string; // reuses serializeCsv
export type ImportIssue = { row: number; column: string; message: string };
export function issueReportCsv(issues: ImportIssue[]): string;       // thin wrapper over contractMappingCsv
export function downloadIssues(issues: ImportIssue[], filename: string): void;
```

Client-side matching only pre-renders suggestions; the **backend is authoritative** for validation, matching, and decisions (same principle as "React Flow is a view/editor, not the validation authority").

### Database changes (migration `api/alembic/versions/0011_import_provenance.py` — new)

Follow existing migration style (`json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")`, `sqlite_where` for partial indexes — the test suite runs on SQLite).

1. `systems` — add `external_identifier sa.String(255) nullable`; partial unique index `uq_systems_active_external_id` on `(tenant_id, external_identifier)` where `deleted_at IS NULL AND external_identifier IS NOT NULL` (mirrors `objects.external_identifier` conventions). System **aliases** live in the existing bounded `metadata` JSON under key `"aliases": string[]` — no new column, covered by the existing 16 KiB metadata validator.
2. `information_objects` — add `external_identifier sa.String(255) nullable`, `classification sa.String(100) nullable`.
3. `solution_boundaries` — add `external_identifier sa.String(255) nullable`, `owner sa.String(160) nullable`.
4. `integrations` — add `external_identifier sa.String(255) nullable` and a `metadata` JSON column (mapped as `extra_metadata`, default `{}`, matching catalog naming).
5. New table `solution_members`: `id` UUID pk, `tenant_id` FK tenants RESTRICT, `solution_object_id` UUID, `system_id` UUID, composite FKs `(solution_object_id, tenant_id) -> solution_boundaries(object_id, tenant_id)` and `(system_id, tenant_id) -> systems(id, tenant_id)` both `ON DELETE CASCADE`, `created_at`, `UniqueConstraint(solution_object_id, system_id, name="uq_solution_members_pair")`, index on `(tenant_id, solution_object_id)`. This is the canonical "solution includes system" membership — no system copies inside solutions.
6. New table `import_batches`: `id` UUID pk, `tenant_id` FK RESTRICT, `workspace_id` FK workspaces CASCADE, `source_filename sa.String(255)`, `sheet_name sa.String(120)`, `import_type sa.String(40)`, `status sa.String(32)` (check in `('applied','undone','undo_blocked')`), `counts sa.JSON`, `imported_at`/`undone_at` timezone timestamps. Index `(tenant_id, workspace_id, imported_at)`.
7. New table `import_row_results`: `id` UUID pk, `tenant_id`, `batch_id` FK import_batches CASCADE, `row_number int`, `external_id sa.String(255) nullable`, `action sa.String(32)`, `target_kind sa.String(40) nullable`, `target_id UUID nullable`, `status sa.String(32)`, `message sa.Text nullable`, `before sa.JSON nullable`, `after sa.JSON nullable` (snapshots for undo), `UniqueConstraint(batch_id, row_number)`. Index `(tenant_id, target_id)` for reverse lookup during undo safety checks.

`downgrade()` drops the new tables and removes added columns/indexes.

## Files

### New files

| Path | Purpose |
|---|---|
| `api/alembic/versions/0011_import_provenance.py` | Schema: external IDs, classification/owner columns, integration metadata, `solution_members`, `import_batches`, `import_row_results` |
| `api/app/imports/__init__.py` | Package marker |
| `api/app/imports/schemas.py` | Pydantic request/response models listed under Types |
| `api/app/imports/service.py` | Name normalization, layered matching, per-kind row validation, create/update application with before/after snapshots, batch commit orchestration, undo execution |
| `api/app/imports/routes.py` | `router = APIRouter(prefix="/api/workspaces/{workspace_id}/imports", tags=["imports"])` — preview, commit, batch list/detail, undo |
| `api/app/models/import_batch.py` | `ImportBatch`, `ImportRowResult` SQLAlchemy models |
| `api/tests/test_imports.py` | Backend tests (see Testing) |
| `web/src/architectureImport.ts` | Client table pipeline (CSV + Excel), field specs per import kind, mapping suggestion, normalization, template/error-report helpers |
| `web/src/architectureImport.test.ts` | Vitest for the pure logic |
| `web/src/components/import/ArchitectureImportDialog.tsx` | The shared guided wizard dialog |
| `web/src/components/import/ArchitectureImportDialog.test.tsx` | jsdom flow test |
| `fixtures/architecture-import/*.csv` (+ generated `.xlsx`) | Sample import files for the 12-step verification |

### Existing files to modify

| Path | Changes |
|---|---|
| `api/app/models/catalog.py` | `CatalogSystem.external_identifier: Mapped[str \| None]` (String 255) |
| `api/app/models/architecture_object.py` | `InformationObject.external_identifier`, `InformationObject.classification`; `SolutionBoundary.external_identifier`, `SolutionBoundary.owner`; new `SolutionMember` model |
| `api/app/models/integration.py` | `Integration.extra_metadata` (column `metadata`, JSON, default `{}`), `Integration.external_identifier` |
| `api/app/models/__init__.py` | Export `SolutionMember`, `ImportBatch`, `ImportRowResult` |
| `api/app/catalog/schemas.py` | `SystemCreate`/`SystemUpdate`/`SystemResponse`: add optional `external_identifier` (max 255); `extra="forbid"` and metadata validator unchanged |
| `api/app/architecture/schemas.py` | `ArchitectureObjectResponse`: add `external_identifier: str \| None = None`, `classification: str \| None = None`; add `IncludeObjectsRequest`/`IncludeObjectsResponse` |
| `api/app/architecture/routes.py` | New controlled endpoint `POST /{state_id}/include-objects` (see Functions); reuse `get_accessible_workspace`, `_validate_state_nodes` |
| `api/app/main.py` | `app.include_router(imports_router)`; bump `version="0.2.0-alpha"` |
| `api/pyproject.toml` | `version = "0.2.0-alpha"` |
| `web/package.json` | Add `"exceljs": "^4.4.0"`; bump `"version": "0.2.0-alpha"` |
| `web/src/CatalogWorkspace.tsx` | Add **Import** button in the Systems panel header (next to `Add system`), open `ArchitectureImportDialog`, handle post-commit "Use in Current architecture" action, refresh systems/objects after commit |
| `web/src/style.css` | Reuse existing `.csv-*`/`.contract-csv-dialog` classes; append small additions for the wizard step indicator, per-row decision selects, and results summary (studio tokens only) |
| `web/src/architectureTypes.ts` | Add `ImportBatch` view type used by the dialog; existing types unchanged |
| `docs/user-guide.md` | New section: Import architecture from Excel/CSV (workflow, field tables, matching rules, undo, re-import) |
| `docs/api-plan.md`, `docs/data-model.md`, `SYSTEM_CAPABILITIES.md`, `docs/implementation-log.md` | Document new endpoints, tables, and capability |
| `CHANGELOG.md` | New `## [0.2.0-alpha]` entry |

### Files that must NOT change behavior

`web/src/contractMappingCsv.ts`, `web/src/components/ContractCsvDialog.tsx`, the `IntegrationWorkspace.tsx` CSV flow, `api/app/engine/*`, `api/app/workspaces/service.py` bundle import/export, catalog archive/cascade logic, scenario evaluation. They may be imported-from (helpers/types) but not behaviorally modified.

## Functions

### Backend — `api/app/imports/service.py`

- `normalize_name(value: str) -> str` — NFKC normalize, strip, collapse internal whitespace, casefold; used for all name comparisons.
- `match_rows(db, workspace, import_type, rows, column_mapping) -> list[RowMatchState]` — layered matching per row, in order:
  1. **External ID** — exact match on the kind's `external_identifier` column (active records only).
  2. **Exact normalized name** — `normalize_name` equality against active record names (systems: `CatalogSystem.name`; integrations: `Integration.name`; typed tables: `name`).
  3. **Existing alias** — systems only: scan `CatalogSystem.extra_metadata["aliases"]` (string list) for a normalized hit. (Aliases are a system concept in Phase 3; the scan is bounded by tenant system count, which is already list-limited.)
  4. **Similar name suggestion** — `difflib.SequenceMatcher(None, norm_a, norm_b).ratio() >= 0.90` → emitted as a **warning + match candidate with `method="similar_name"`**, never auto-merged. A `similar_name` match requires the user to explicitly confirm `update`/`use_existing` with that `target_id`.
- `validate_import_row(db, workspace, import_type, values, field_specs) -> list[ImportIssue]` — required fields, cell-length bounds, per-kind rules:
  - **system**: name required; lifecycle/status/technology/owner/business_domain optional → stored in `metadata`.
  - **information_object**: name, owner, authoritative_system required; the authoritative system must resolve to an active `CatalogSystem` (reuse `active_system` from `api/app/catalog/routes.py`); otherwise the row is **blocked**.
  - **integration**: name, source_system, target_system required; endpoints resolve to systems, then objects via optional `source_object`/`target_object` columns; when absent, reuse the system's single active `CatalogObject`; **block the row when either endpoint remains unresolved** (zero or multiple objects and no object column). `integration_type` maps synonyms onto `ONE_WAY`/`REQUEST_RESPONSE`/`ASYNC_CALLBACK`; unrecognized non-empty values block the row with the allowed values listed. `contract_reference` matches an existing `Integration` by external ID or exact name and converts the row into an update/use_existing of that contract instead of a duplicate. Imported integrations get empty graphs — they never duplicate or modify schemas, mappings, transformations, or tests.
  - **solution**: solution name required; `included_systems` (semicolon-separated names or external IDs) each resolved via the same layered match (external ID → name → alias); **any unresolved member blocks the row**; membership is stored as `solution_members` rows referencing canonical systems.
- `apply_commit(db, workspace, request, user) -> ImportBatch` — for each non-skipped row inside one transaction:
  - `create`: build the model row (systems via `CatalogSystem` — the existing `after_insert` event registers the canonical architecture object; information objects/solutions create `ArchitectureObject(kind=…)` + typed row; integrations create `Integration` with `revision=1`, empty graphs, `metadata={owner, lifecycle}`). Stores an `after` snapshot.
  - `update`: apply only mapped, non-empty fields onto the matched record; store `before` (only changed keys) and `after`. Systems updates merge `metadata` keys without clobbering unmapped metadata; aliases replace `metadata["aliases"]` only when the aliases column was mapped.
  - `use_existing`: no mutation; status `matched`.
  - `skip`: status `skipped`.
  - Per-row failures (e.g. `IntegrityError` from a concurrent name change) are captured as `failed` with a message; other rows still apply (row-level, not all-or-nothing — required by the created/updated/matched/skipped/blocked/failed count contract). Blocked rows never partially apply.
  - Persist `import_batches` + `import_row_results`, commit once.
- `undo_import_batch(db, workspace, batch_id) -> ImportBatch` — reverses **only this batch**, row by row, newest first:
  - `create` rows → delete typed row + registry row for architecture objects (`SolutionMember` rows cascade); soft-delete for `CatalogSystem`/`Integration` (`deleted_at = now`, consistent with archive conventions). If a created record is referenced elsewhere (system used as an authoritative system or integration endpoint added after the batch; object present in any state's nodes), that row is reported `conflict` with the referencing names — remaining reversible rows still reverse; `batch.status = "undone"` only when every created/updated row is reversed, else `"undo_blocked"`.
  - `update` rows → restore `before` values, but only when the record's current values still equal the `after` snapshot; otherwise report `conflict` (edited after import) and leave the record untouched.
  - `use_existing`/`skip` rows → no-op.
  - Set `batch.undone_at` / `batch.status`.

### Backend — `api/app/imports/routes.py`

- `POST /api/workspaces/{workspace_id}/imports/preview` → `ImportPreviewResponse`. CSRF + session auth; discipline gating: `information_object` requires `"information"` in `workspace.disciplines`, `solution` requires `"solution"` (422 otherwise, mirroring `_enabled` in `api/app/architecture/objects.py`); systems/integrations always allowed. Bounded payload (500 rows / 2 MiB JSON) → 413/422 when exceeded. Stateless preview (no writes, no batch row).
- `POST /api/workspaces/{workspace_id}/imports/commit` → `ImportBatchResponse` (201). Re-validates everything (never trusts the preview), applies decisions, returns counts.
- `GET /api/workspaces/{workspace_id}/imports` → `list[ImportBatchResponse]` (rows omitted/truncated to issues-only in the list; the detail endpoint returns full rows). Powers "Undo a previous import" after refresh.
- `GET /api/workspaces/{workspace_id}/imports/{batch_id}` → full `ImportBatchResponse` for row-level error downloads.
- `POST /api/workspaces/{workspace_id}/imports/{batch_id}/undo` → `ImportBatchResponse` with status `undone`/`undo_blocked` and per-row undo outcomes.

### Backend — `api/app/architecture/routes.py`

- `POST /api/workspaces/{workspace_id}/states/{state_id}/include-objects` → `IncludeObjectsResponse`. This is the **controlled enrichment path** for the read-only Current state (the general `PUT` on `current` stays blocked):
  - Validates all ids belong to the tenant and are active.
  - For each selected system / architecture object without an existing occurrence in the state, append an `ArchitectureStateNode` at a free grid position (placement approach of `auto_initialize_current_state`, offset below existing nodes) with `discipline` set for typed objects.
  - For each selected integration, add an `ArchitectureStateRelationship` (`integration_id` set, `type="Consumes"`) **only when both endpoint system occurrences exist** (selected or already on the canvas); otherwise add to `skipped` with a message — the user chose exactly which systems appear, so nothing is auto-placed.
  - With `visualize_solution_membership`, for each selected solution also ensure member systems (from `solution_members`) have occurrences and add `Contains` relationships from the boundary occurrence to member occurrences.
  - Idempotent: re-including the same objects is a no-op counted as skipped.
  - Commits the updated state once; Current remains non-editable through every other path.

### Frontend — `web/src/architectureImport.ts`

- `parseImportFile(file: File): Promise<ParsedWorkbook>` — `.csv`/`.txt` → Papa Parse (reuse `parseMappingCsv` options: `delimitersToGuess`, `skipEmptyLines: "greedy"`, BOM strip, `isFormulaLike` cell rejection, 1 MiB / 500-row caps); `.xlsx` → `exceljs` `workbook.xlsx.load(await file.arrayBuffer())`, one `ParsedWorkbook` entry per worksheet, values stringified for display, formula cells rejected via the same `isFormulaLike` check on formula text; unsupported extensions produce a file-level issue.
- `suggestColumnMapping(headers, fields)` — case/space-insensitive match of each header against `field.label` and `field.aliases`.
- `buildTemplateCsv(fields)` / `downloadIssues(issues, filename)` — wrap `serializeCsv`/`downloadCsv` from `contractMappingCsv.ts` (keeping the JSON-quote guard against CSV formula injection).

### Frontend — `web/src/components/import/ArchitectureImportDialog.tsx`

Single shared wizard component parameterized by `ImportKind`, modeled on `ContractCsvDialog` (`<dialog>` + `showModal()`, focus restore, stale-preview guard):

1. **Upload** — file input (`.csv`, `.xlsx`), size/row-limit feedback, issue list.
2. **Sheet & type** — sheet select (auto-skipped for CSV), import-type select (systems / information objects / integrations / solutions).
3. **Column mapping** — grid of canonical field selects pre-filled by `suggestColumnMapping`, required fields marked, template download.
4. **Preview** — calls `POST …/imports/preview`; table mirrors the contract-CSV preview: row number, name, mapped values, match badges (`external ID`, `name`, `alias`, `similar — confirm?`), per-row issues, and a per-row decision select (**Use existing** with candidate picker when several/similar, **Create new**, **Update existing**, **Skip**). Similar-name matches require explicitly picking the candidate — never preselected.
5. **Review changes** — one summary line per row (`create X`, `update Y: description, lifecycle`, `skip`) plus totals; confirm checkbox ("I reviewed the proposed changes") gates commit exactly like the contract CSV dialog.
6. **Commit & results** — calls `POST …/imports/commit`; shows created / updated / matched / skipped / blocked / failed counts; "Download row errors" button; **Undo import** button (calls the undo endpoint and remains available after refresh via the batch list); **Use in Current architecture…** button that opens a compact object picker of this batch's created/matched records and calls `POST …/states/{current}/include-objects` (if no Current state exists yet, the dialog explains that canvas auto-initialization still governs and offers to open the Canvas).

### Frontend — `web/src/CatalogWorkspace.tsx`

- Add an **Import** button beside the `Add system` `<details>` in the Systems panel (`activeView === "catalog"`), opening the dialog with an `onCommitted` callback that reloads systems/objects (existing loaders) and surfaces a status message.

## Classes

No new Python or TypeScript classes beyond Pydantic models and three SQLAlchemy models:

- `SolutionMember(Base)` — `api/app/models/architecture_object.py`, `__tablename__ = "solution_members"`, composite FKs per the migration; exported from `api/app/models/__init__.py`.
- `ImportBatch(Base)` / `ImportRowResult(Base)` — `api/app/models/import_batch.py` (new), `json_type` reused from `app.models.catalog`; exported from `api/app/models/__init__.py`.

Existing models receive only additive mapped columns (listed under Files); no inheritance changes, no removed classes.

## Dependencies

- **New frontend dependency**: `exceljs@^4.4.0` (pure JS, ARM64-safe, browser read path `workbook.xlsx.load(arrayBuffer)`; pinned via `package-lock.json`, installed with the existing `npm ci` flow; ships its own TypeScript types).
- **Backend**: none — `difflib` and `unicodedata` are stdlib; matching and undo need no new packages.
- Version synchronization per `AGENTS.md`: bump to `0.2.0-alpha` in `web/package.json`, `api/app/main.py`, `api/pyproject.toml`, plus a `CHANGELOG.md` entry, in the same change set. All releases stay pre-releases; no major bump.

## Testing

### Backend — `api/tests/test_imports.py` (new; fixture pattern copied from `test_architecture_states.py`: in-memory SQLite, `StaticPool`, CSRF via `dd_csrf` cookie)

1. **Preview/match cascade** — seed a system with `external_identifier`, one with `metadata.aliases`; assert rows match by external ID, then name, then alias; a near-identical name yields a `similar_name` warning candidate and is never auto-matched as an update.
2. **System import commit** — create 2, update 1 (before/after snapshots persisted), skip 1; assert counts, `import_batches`/`import_row_results` rows, provenance (filename, sheet, row number, external ID), and that imported systems are canonical (`architecture_objects` registry rows exist, kind `system`).
3. **Re-import idempotency** — commit the same file again with `use_existing`/auto decisions; assert no duplicate systems and statuses are `matched`/`updated`, not `created`.
4. **Information object import** — resolvable authoritative system → created; unknown authoritative system → row `blocked`, nothing written for that row.
5. **Integration import** — endpoints resolved via single-object systems → created with empty graphs; ambiguous endpoint (two objects, no object column) → blocked; `contract_reference` pointing at an existing contract → update of that contract, no duplicate.
6. **Solution import** — `solution_members` rows reference canonical systems; no new system rows created; unresolved member blocks the row.
7. **Discipline gating** — information-object import into a workspace without the `information` discipline returns 422.
8. **Undo** — undo reverses only the target batch (a second batch and pre-existing records untouched); a created information object disappears (registry + typed row); an updated system restores to `before`; a record edited after import yields `conflict`/`undo_blocked` without clobbering.
9. **Include-objects endpoint** — enriches the Current state idempotently; an integration with an unselected endpoint system is skipped with a message; solution membership renders as `Contains` relationships; regression assertion that the general `PUT` on `current` stays blocked.
10. **Auth/CSRF** — commit/undo/include without a CSRF token → 403; wrong-tenant workspace → 404.

System responses now include `external_identifier` (nullable default) — assert compatibility so existing `test_catalog.py`/`test_architecture_states.py` stay green.

### Frontend

- `web/src/architectureImport.test.ts` — CSV parse caps and formula rejection; Excel parse of a generated workbook (construct an `exceljs` buffer in-test); `suggestColumnMapping` with synonym headers; `normalizeName` (case/whitespace/NFKC); template CSV round-trip; issue-report download content.
- `web/src/components/import/ArchitectureImportDialog.test.tsx` (`// @vitest-environment jsdom`) — happy path with mocked `fetch`: upload CSV → mapping prefilled → preview renders match badges → choosing a "similar name" candidate enables update → confirm checkbox gates commit → results counts render; blocked rows cannot be committed as create; undo button calls the undo endpoint.
- Existing suites stay green unchanged (`npm test`, `npm run check`, `pytest`, `ruff`) — this is the preservation gate.

### Manual verification (the required 12-step flow)

Fixture files under `fixtures/architecture-import/` (CSV committed; `.xlsx` generated from the same data via a one-off `exceljs` node script during implementation and committed):

1. Import 4 systems from `systems.xlsx` (one matching an existing system, one new, one update, one row to skip).
2–5. In the wizard: confirm the match (external ID), create, update, and skip decisions; commit; verify counts.
6. Import `information-objects.csv` with an authoritative system resolved by alias.
7. Import `integrations.csv` whose endpoints resolve to canonical systems (plus one deliberately ambiguous row to verify blocking and error download).
8. Import `solutions.csv` containing existing systems; verify `solution_members` and no system copies.
9. Re-import `systems.xlsx` unchanged; verify zero `created`, statuses `matched`/`updated`, no duplicates.
10. Use in Current architecture: select a subset of imported systems + one integration + one solution; verify only the selection appears and the integration/solution relationships render.
11. Full browser refresh; verify catalog records, provenance (batch listed under Import history), and Current-view membership persist.
12. Undo the batch; verify only that batch's changes reverse (imported objects removed/restored, other batches untouched).

Validation gate at the end: `make check` (ruff, pytest, `tsc --noEmit`, vite build, compose config) plus `npm test`, then the browser walkthrough.

## Implementation Order

1. **Migration `0011_import_provenance.py`** + model additions (`CatalogSystem.external_identifier`, `InformationObject`/`SolutionBoundary` columns, `Integration` metadata/external id, `SolutionMember`, `ImportBatch`, `ImportRowResult`) + `models/__init__.py` exports. Run pytest to confirm existing suites pass against the new schema.
2. **Schema surface updates**: `SystemCreate/Update/Response.external_identifier`; additive `ArchitectureObjectResponse` fields. Re-run `test_catalog.py`/`test_architecture_states.py`.
3. **`api/app/imports/schemas.py`** (pure types, no behavior).
4. **`api/app/imports/service.py`** — normalization + matching first (db access only for lookups), then per-kind validation, then `apply_commit` with snapshots, then `undo_import_batch`.
5. **`api/app/imports/routes.py`** + register the router in `main.py`. Write `api/tests/test_imports.py` alongside steps 4–5 and keep it green incrementally.
6. **`POST …/states/{state_id}/include-objects`** in `architecture/routes.py` + tests.
7. **Frontend `web/src/architectureImport.ts`** + `architectureImport.test.ts` (parse pipeline, mapping suggestion, helpers); add `exceljs` via `npm install`.
8. **`ArchitectureImportDialog.tsx`** + test — wizard steps 1–6 wired to preview/commit/undo endpoints.
9. **Wire into `CatalogWorkspace.tsx`** (Import button, refresh, status) + small CSS additions in `style.css` reusing `.csv-*` classes.
10. **Fixtures** (`fixtures/architecture-import/`) and run the full 12-step manual verification against the running stack (`make up`, migrate, browser).
11. **Docs + version bump**: user-guide section, api-plan, data-model, SYSTEM_CAPABILITIES, implementation-log entry, CHANGELOG `0.2.0-alpha`, version sync in `web/package.json`, `api/app/main.py`, `api/pyproject.toml`; final `make check` + `npm test`; commit as a pre-release per `AGENTS.md`.

### Assumptions and deliberate constraints

- System "Owner / Business domain / Lifecycle / Status / Technology" and integration "Owner / Lifecycle" are stored in the bounded `metadata` JSON (no new columns) — consistent with the catalog's generic-metadata philosophy; External ID and Aliases get first-class treatment because matching depends on them (aliases via `metadata["aliases"]`).
- Alias matching applies to systems in Phase 3 (the only import kind that lists Aliases as a field).
- Undo is batch-scoped, persisted, and conservative: it refuses to delete or restore records that were modified or referenced after the batch, reporting conflicts instead of risking data loss.
- Current-state enrichment is append-only through the new endpoint; the general Current read-only rule is preserved.
- Excel support covers `.xlsx` (not legacy `.xls`); formula-like text is rejected rather than modified, same as the CSV contract exchange.
- Import commits are row-level (partial success allowed and reported per row), unlike the all-or-nothing contract-mapping CSV import — required by the created/updated/matched/skipped/blocked/failed count contract.
- `web/vite.config.ts` already contains an uncommitted local dev-server tweak (`allowedHosts` for Tailscale); it is unrelated to Phase 3 and left as-is.
