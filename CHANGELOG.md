# Changelog

All notable changes to Data Designer will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-alpha] - 2026-10-15

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

### Changed
- Imported integrations reuse the existing contract table with empty graphs and
  never duplicate or rewrite schemas, mappings, transformations, or tests.

## [0.1.0-alpha] - 2026-10-07

### Added
- **Catalog Management**: Systems, data objects, fields, and physical names with validation.
- **Visual Integration Canvas**: React Flow-based mapping canvas connecting sender and receiver fields.
- **Transformation Engine**: Built-in Python transformation engine executing deterministic mappings without external dependencies.
- **Scenario Studio**: Multi-step integration scenario design with interactive UML sequence diagrams.
- **Enterprise Landscape**: Visual topology and connectivity matrix of modeled enterprise integrations.
- **CSV Import/Export**: Support for importing and exporting mapping contracts as CSV.
- **Local Dev Stack**: Docker Compose setup with PostgreSQL and hot-reloading FastAPI backend and Vite/React frontend.
