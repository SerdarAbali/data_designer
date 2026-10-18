# Changelog

All notable changes to Data Designer will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-alpha] - 2026-10-19

### Added
- **Guided architecture import**: one shared Excel/CSV wizard for Systems,
  Information objects, Integrations, and Solutions, opened from **Catalog**.
  Column mapping with suggestions and templates, row-level validation, layered
  matching (external ID → exact normalized name → alias → confirmed
  similar-name suggestion), per-row decisions (use existing / create / update /
  skip), a full change preview, and created/updated/matched/skipped/blocked/
  failed counts.
- **Import provenance and batch undo**: `import_batches` and
  `import_row_results` store source file, sheet, row number, external ID, and
  before/after snapshots; row-level errors download as CSV; undo reverses one
  batch only and reports conflicts instead of deleting referenced records or
  overwriting later edits, with retry once the reference is removed.
- **Canonical model additions**: `systems.external_identifier` (unique while
  active), system aliases in bounded metadata,
  `information_objects.external_identifier`/`classification`,
  `solution_boundaries.external_identifier`/`owner`, `integrations.
  external_identifier` plus bounded metadata, and the `solution_members`
  membership table that references canonical systems.
- **Current-view enrichment**: `POST …/states/{state_id}/include-objects` adds
  only the imported objects the user selects to an architecture state; nothing
  is placed automatically and the general Current update path stays read-only.
- ExcelJS for `.xlsx` parsing, loaded on demand.
- **Architecture facts**: canonical fact columns with per-state overrides —
  state-member overrides for systems and `IntegrationStateOverride` rows for
  Contracts — so a Candidate can restate facts without touching Current.
- **Contract mediator**: a Contract names a mediator system and responsibility,
  revalidated on every write against the contract's business endpoints.
- **Architecture evidence**: an exclusive five-FK arc (system, object, field,
  contract, dependency) plus the evidence panel, so modelled relationships cite
  the record they came from.
- **Integration Landscape**: an obstacle-aware projection of the tenant's
  contracts and systems, filtered client-side with `il_*` URL keys.
- **Solution ↔ Contract associations**: a boundary can own, participate in, or
  depend on a Contract, reported in the Contracts panel.
- **Solution Landscape**: a cross-solution projection of boundaries, members,
  components, interfaces, repositories and deployment nodes.
- **Assistant refinement proposals**: the embedded Assistant proposes bounded
  refinements for review instead of writing to the canonical model directly.
- **Governed Excel Contract workbook**: one preview/apply workbook for contract
  metadata, request/success/error mappings and transformations, with the same
  validation as the mapping canvas.
- **Current baseline lifecycle**: a Current state is either a `draft`
  (editable) or `locked` (read-only). Migration `0028_current_baseline`, one
  central write policy in `app/architecture/state_scope.py`, an explicit
  `lock-baseline` endpoint, and workspace creation options. Canonical Contract
  mutations are refused while the Contract is anchored in a locked Current
  baseline; a Contract the baseline does not describe stays editable.
- **Workspace bundle portability**: export, import and fork carry the baseline
  status, so a locked Current stays locked, a draft stays draft, and a bundle
  written before the field existed imports as locked.
- **Hover focus on the architecture canvases**: hovering a node or a connector
  dims everything outside that connection.

### Changed
- Imported integrations reuse the existing contract table with empty graphs and
  never duplicate or rewrite schemas, mappings, transformations, or tests.
- **Branding**: the application UI is renamed from Data Designer to
  **Collatecht**; the header logo mark is removed and the wordmark is sized to
  sit on the same axis as the rest of the header.

### Fixed
- **Connector legibility**: the shared orthogonal router takes a single bend
  when two handles are nearly aligned, rounds corners along the real segment
  direction instead of bulging on shallow joints, and assigns corridor lanes so
  parallel connectors stop stacking. Edge labels anchor onto a clear point of
  their own connector instead of hiding behind nodes, and the Solution
  decomposition places every interface port on the side facing the component it
  connects to, so `connects_to` links no longer loop around the diagram.
- **Hover flicker**: hover focus settles briefly before dimming, and dimmed
  labels leave the hit-testing tree, so sweeping across a bundle of connectors
  no longer flashes the canvas.
- The React Flow attribution is hidden consistently on every canvas.

## [0.1.0-alpha] - 2026-10-07

### Added
- **Catalog Management**: Systems, data objects, fields, and physical names with validation.
- **Visual Integration Canvas**: React Flow-based mapping canvas connecting sender and receiver fields.
- **Transformation Engine**: Built-in Python transformation engine executing deterministic mappings without external dependencies.
- **Scenario Studio**: Multi-step integration scenario design with interactive UML sequence diagrams.
- **Enterprise Landscape**: Visual topology and connectivity matrix of modeled enterprise integrations.
- **CSV Import/Export**: Support for importing and exporting mapping contracts as CSV.
- **Local Dev Stack**: Docker Compose setup with PostgreSQL and hot-reloading FastAPI backend and Vite/React frontend.
