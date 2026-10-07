# Data Designer — Implementation Roadmap

This document defines the implementation order for Data Designer.

The authoritative product and architecture specification is:

`docs/MASTER-SPEC.md`

Read that document before implementing any phase.

This document defines **when** things should be built.

---

# Development Philosophy

Build the product from the inside out:

```text
DOMAIN MODEL
    ↓
INTEGRATION MODEL
    ↓
TRANSFORMATION ENGINE
    ↓
SIMULATION
    ↓
DESIGNER UI
    ↓
VISUAL GRAPH EDITOR
    ↓
ENTERPRISE LANDSCAPE
    ↓
ARCHITECTURE ANALYSIS
    ↓
CONNECTORS
```

Do not start with connectors.

Do not start with visual polish.

Do not build Salesforce-specific functionality before the generic model is proven.

The application must be useful with manually designed systems before any external connector exists.

---

# Phase 0 — Development Environment

## Objective

Prepare the Raspberry Pi development environment and create the repository.

The human has already installed:

* Raspberry Pi OS
* SSH

Everything else may need to be installed.

## Tasks

Inspect:

* OS version
* architecture
* CPU
* RAM
* disk space
* Git
* Docker
* Docker Compose
* Python
* Node.js

Install missing development prerequisites.

Use current official documentation.

Everything must support ARM64.

Create:

```text
~/datadesigner
```

Initialize Git.

Create:

```text
docs/
api/
web/
fixtures/
```

Create:

```text
docs/host-environment.md
docs/assumptions.md
docs/blockers.md
docs/dependencies.md
```

## Deliverable

A clean development machine and Git repository.

## Gate

The following work:

```text
git
docker
docker compose
python
node
```

and the project directory exists.

No application functionality yet.

---

# Phase 1 — Application Skeleton

## Objective

Create the smallest complete application stack.

Architecture:

```text
Browser
   ↓
React/Vite
   ↓
FastAPI
   ↓
PostgreSQL
```

## Backend

Create:

```text
api/
  app/
    main.py
    config.py
    db.py
```

Configure:

* FastAPI
* SQLAlchemy
* PostgreSQL
* Pydantic
* Alembic

Create:

```text
GET /health
```

Health response must indicate:

```text
API running
database reachable
```

## Frontend

Create React/Vite application.

Verify:

```text
browser
  ↓
web container
```

works.

## Docker

Create:

```text
docker-compose.yml
docker-compose.dev.yml
```

Services:

```text
db
api
web
```

PostgreSQL must use a named volume.

All images must support ARM64.

## Deliverable

The entire application starts with one documented command.

## Gate

```text
make up
```

starts everything.

```text
make check
```

passes.

---

# Phase 2 — Authentication

## Objective

Protect the application before building domain functionality.

Implement:

* login
* logout
* current user
* password hashing
* session cookie
* rate limiting
* protected API routes

Use Argon2id.

Use secure cookie settings.

Do not build multi-user functionality yet.

The initial architecture should support a single application tenant/user.

## Deliverable

A user can:

```text
login
  ↓
access application
  ↓
logout
  ↓
lose access
```

## Gate

Unauthenticated users cannot access protected API endpoints.

Tests cover:

* successful login
* invalid password
* logout
* protected endpoint
* rate limiting

---

# Phase 3 — Dynamic System/Object/Field Catalog

## OBJECTIVE

This is the first major architectural milestone.

Build the generic data catalog.

```text
System
  ↓
Object
  ↓
Field
```

There must be no vendor-specific domain model.

## System

Implement:

```text
System
```

with:

* id
* tenant_id
* name
* description
* kind
* icon
* color
* position
* binding_state
* metadata
* timestamps

## Object

Implement:

```text
Object
```

with:

* id
* tenant_id
* system_id
* name
* label
* description
* external_identifier
* origin
* metadata
* timestamps

## Field

Implement:

```text
Field
```

with:

* id
* tenant_id
* object_id
* name
* label
* description
* data_type
* required
* nullable
* default_value
* external_identifier
* position
* origin
* metadata
* timestamps

## CRUD

Implement APIs for:

```text
Systems
Objects
Fields
```

Users must be able to create completely arbitrary structures.

Example:

```text
System:
    "My Legacy Application"

Object:
    "CustomerRecord"

Fields:
    "CUST_ID"
    "CUSTOMER_NAME"
    "PHONE"
```

No code change should be necessary.

## Safety

Prevent deletion of objects/fields that are still referenced by integrations once integrations exist.

Prepare the service layer for these checks.

## Tests

Test:

* create system
* update system
* delete system
* create object
* update object
* delete object
* create field
* update field
* delete field
* ordering
* validation
* arbitrary names
* arbitrary system kinds
* data types

## Gate

The API can create an entirely new system/object/field structure without application code changes.

This phase must contain **zero Salesforce-specific behavior**.

---

# Phase 4 — Integration Domain

## Objective

Connect two objects through an integration.

Implement:

```text
Integration
```

with:

```text
source_system_id
source_object_id
target_system_id
target_object_id
name
description
trigger information
graph
sample rows
graph version
timestamps
```

Also implement:

```text
IntegrationDependency
```

## Integration creation

The user must be able to select:

```text
Source System
    ↓
Source Object
    ↓
Target System
    ↓
Target Object
```

## Graph schema

Define a versioned graph representation.

Example:

```json
{
  "version": 1,
  "nodes": [],
  "edges": []
}
```

Source and target fields must be referenced by stable IDs.

Do not use field names as canonical identifiers.

## Graph validation

Validate:

* node types
* ports
* source fields
* target fields
* duplicate target connections
* cycles
* invalid configurations

## Gate

A valid integration can be created and persisted entirely through the API.

---

# Phase 5 — Transformation Engine

## Objective

Build the pure Python execution engine.

The engine must not know about:

* FastAPI
* SQLAlchemy
* PostgreSQL
* React
* HTTP
* filesystem

It receives data and a validated graph.

It returns results.

Conceptually:

```text
input rows
    +
graph
    ↓
engine
    ↓
output rows
+
trace
+
errors
```

## Node types

Implement:

```text
constant
fx
concat
ifelse
map
coalesce
lookup
filter
validate
```

## fx functions

Implement:

```text
trim
title
lower
upper
e164
date
```

## Error policies

Implement:

```text
fail
skip
default
```

## Row outcomes

Implement:

```text
ok
skipped
failed
```

## Trace

Every evaluated node should be traceable.

Example:

```text
source.Email
    ↓
trim
    ↓
lower
    ↓
target.EMAIL
```

## Testing

Use:

* unit tests
* golden fixtures
* property-based tests

Test every transformation.

## Gate

The engine can run independently of the API.

The engine has strong automated coverage.

---

# Phase 6 — Dry-Run API

## Objective

Expose the engine through the API.

Implement:

```text
POST /api/integrations/{id}/dry-run
```

Input:

```text
sample rows
```

Output:

```text
row results
counts
target values
trace
errors
```

Example:

```text
12 OK
3 SKIPPED
2 FAILED
```

The frontend must not execute transformations.

## Live simulation

Support debounced simulation from the editor later.

## Gate

An integration can be simulated entirely through the API.

---

# Phase 7 — System/Object/Field Designer UI

## Objective

Make the dynamic catalog usable.

Create:

```text
System Designer
Object Designer
Field Designer
```

## System UI

Users can:

* create
* edit
* delete
* reposition
* inspect

systems.

## Object UI

Users can:

* create
* rename
* delete
* reorder

objects.

## Field UI

Users can:

* create
* rename
* delete
* reorder
* change type
* mark required
* edit metadata

## Critical requirement

When the user creates:

```text
System A
  Object A
    Field A
```

that structure must immediately be available to integration design.

No frontend hardcoded field lists.

## Gate

A user can build a complete architecture from an empty database.

---

# Phase 8 — Integration Editor

## Objective

Build the core visual mapping experience.

Use:

```text
@xyflow/react
```

## Source

The selected source object dynamically produces source field ports.

## Target

The selected target object dynamically produces target field ports.

## Mapping

Allow:

```text
source field
    ↓
target field
```

and:

```text
source field
    ↓
transformer
    ↓
target field
```

## Nodes

Add visual nodes for:

* source
* target
* constant
* fx
* concat
* ifelse
* map
* coalesce
* lookup
* filter
* validate

## Inspector

Selecting a node opens its configuration.

## Live simulation

After graph changes:

```text
wait ~300ms
    ↓
dry-run API
    ↓
update results
```

## Trace

Selecting a result row shows the value at each node.

## Gate

A user can create an integration entirely through the UI and watch sample data flow through it.

---

# Phase 9 — Enterprise Landscape

## Objective

Build the high-level architecture view.

Systems become React Flow nodes.

Integrations become edges.

Example:

```text
Salesforce
     │
     ├──────────── Customer Sync ────────► SAP
     │
     └──────────── Marketing Sync ───────► Mailchimp
```

## Features

Implement:

* system nodes
* integration edges
* animated edges
* node positioning
* saved positions
* integration labels
* status
* row counts
* navigation to integration editor

## Gate

The user can zoom out from field-level mapping to an enterprise-level integration landscape.

---

# Phase 10 — Architecture Intelligence

## Objective

Add the features that make this more than a generic diagram editor.

## Field conflicts

Detect:

```text
same target object
+
same target field
+
multiple integrations
```

Show warnings.

## Dependencies

Implement:

```text
Integration A
     ↓
Integration B
```

Detect:

* self dependencies
* cycles

## Health/status

Display:

```text
draft
attention
healthy
```

based on defined application rules.

## Upstream warnings

If an integration depends on an unhealthy integration, show the dependency warning.

## Gate

The landscape provides useful architectural information rather than only drawing boxes and arrows.

---

# Phase 11 — Hardening and Polish

## Objective

Make the MVP reliable.

Review:

* error handling
* loading states
* empty states
* optimistic updates
* API validation
* graph persistence
* migration safety
* authentication
* logging
* test coverage
* TypeScript strictness
* mypy strictness
* accessibility
* responsive behavior

Add:

* useful error messages
* confirmation dialogs
* broken mapping indicators
* unsaved changes indicators
* saving state
* simulation state
* clear validation feedback

## Performance

Check:

* large object schemas
* large graphs
* many integrations
* repeated dry runs

Avoid unnecessary re-renders.

## Gate

The MVP should feel stable enough for real internal use.

---

# Phase 12 — Connector Architecture

DO NOT implement real connectors yet.

First establish the connector abstraction.

Conceptually:

```text
Connector
    ├── discover system
    ├── discover objects
    ├── discover fields
    ├── bind metadata
    └── optionally execute
```

The generic catalog remains the source of truth.

Connectors populate or bind it.

---

# Phase 13 — CSV Connector

Contract mapping exchange is implemented separately in the contract editor.
It exchanges only the active mapping tab's draft through version-1,
spreadsheet-friendly CSV: direct field mappings or one independent `fx` node
per target, with scalar settings and fail/skip policies. Preview, column/field
resolution, add-only/default conflict handling, explicit replace-matching,
confirmation, and Undo precede the normal revision-protected Save.
Unsupported graph shapes/settings block export rather than lose information.
Other phases and catalog/sample data are unchanged.

Mapping exchange accepts UTF-8 CSV (1 MiB / 500 records) subject to existing
graph limits, rejects formula-like text and invalid records, and never partially
applies an import. See the README for the format and user workflow. This does
not implement the connector responsibilities below.

First real connector.

Support:

* upload CSV
* inspect headers
* create object
* create fields
* import sample rows
* map CSV data to the generic model

CSV should require no special behavior in the integration engine.

---

# Phase 14 — Excel Connector

Support:

* workbook
* worksheet
* columns
* sample rows

Again:

```text
Excel
  ↓
generic System/Object/Field model
```

---

# Phase 15 — Salesforce Connector

Implement later.

Potential functionality:

* OAuth 2.0 + PKCE
* state validation
* secure token storage
* metadata discovery
* objects
* fields
* custom objects
* sandbox/prod
* reconciliation

Do not let Salesforce-specific concepts leak into the generic domain model.

---

# Phase 16 — Real Execution

Only after simulation is mature.

Possible execution model:

```text
trigger
  ↓
fetch
  ↓
transform
  ↓
validate
  ↓
write
  ↓
execution results
```

Every execution should have:

* run ID
* timestamps
* row counts
* errors
* retries
* logs
* audit trail

Production execution should require explicit configuration/confirmation.

---

# Phase 17 — Scheduling and Monitoring

Later:

* schedules
* execution history
* retry policies
* monitoring
* alerts
* dashboards

---

# PHASE GATES

Never skip gates.

After each major phase:

```text
implementation
    ↓
tests
    ↓
make check
    ↓
manual verification
    ↓
commit
    ↓
next phase
```

If a gate fails, fix the current phase before continuing.

---

# CRITICAL ARCHITECTURAL GATES

## Gate A — Dynamic Catalog

Must prove:

```text
User creates arbitrary system
        ↓
User creates arbitrary object
        ↓
User creates arbitrary fields
        ↓
Data persists
        ↓
No code changes required
```

---

## Gate B — Generic Integration

Must prove:

```text
Any object
     ↓
Any object
```

can be connected.

Not:

```text
Salesforce → Salesforce only
```

Not:

```text
Salesforce → Mailchimp only
```

---

## Gate C — Engine Independence

Must prove:

```text
engine
```

can run without:

* database
* FastAPI
* browser
* React

---

## Gate D — Dynamic Graph

Must prove:

Adding a field to an object causes the integration editor to expose that field without changing frontend code.

---

## Gate E — Connector Independence

Must prove:

The core application remains functional with zero external connectors installed.

---

# WHAT NOT TO BUILD DURING MVP

Do NOT get distracted by:

* Salesforce OAuth
* Meta APIs
* Mailchimp APIs
* real execution
* scheduling
* distributed workers
* Kubernetes
* microservices
* multi-user collaboration
* custom JavaScript nodes
* arbitrary Python execution
* marketplace
* plugin architecture
* billing
* SaaS deployment

Those are later.

The MVP is:

```text
Dynamic systems
       ↓
Dynamic objects
       ↓
Dynamic fields
       ↓
Integrations
       ↓
Visual mappings
       ↓
Transformations
       ↓
Simulation
       ↓
Trace
       ↓
Enterprise landscape
       ↓
Conflict/dependency analysis
```

---

# FIRST PLANNER TASK

Before writing application code, DeepSeek Planner must:

1. Read `docs/MASTER-SPEC.md`.
2. Read this roadmap.
3. Inspect the current repository.
4. Inspect the actual installed environment.
5. Identify conflicts between the existing repository and this specification.
6. Produce:

```text
docs/IMPLEMENTATION-PLAN.md
```

The implementation plan must break each phase into concrete tasks.

For each task specify:

```text
Task ID
Objective
Files/components affected
Database changes
API changes
Frontend changes
Tests
Dependencies
Acceptance criteria
```

Example:

```text
Phase 3
Task 3.1

Create System model

Files:
api/app/models/system.py
api/app/schemas/system.py
api/app/routes/systems.py

Database:
systems table

Tests:
test_system_crud.py

Acceptance:
POST /api/systems creates arbitrary systems.
```

The planner must identify dependencies between tasks.

Do not implement anything during planning.

---

# AGENT MODE RULE

Once planning is complete, Agent mode works on ONE task at a time.

The agent must:

1. Read `MASTER-SPEC.md`.
2. Read `IMPLEMENTATION-ROADMAP.md`.
3. Read the relevant section of `IMPLEMENTATION-PLAN.md`.
4. Implement only the requested task.
5. Run relevant tests.
6. Run `make check`.
7. Fix failures.
8. Report what changed.
9. Stop.

Do not silently begin the next phase.

Do not redesign unrelated systems.

Do not "improve" unrelated code unless required by the current task.

---

# MODEL STRATEGY

Use the stronger/reasoning-oriented model for:

* initial planning
* architecture decisions
* difficult debugging
* database redesign
* graph schema changes
* major refactoring

Use the cheaper/faster model for:

* straightforward implementation
* CRUD
* boilerplate
* tests
* simple UI components
* documentation
* repetitive refactors

The model selection must use whatever current DeepSeek models are actually available in Cline.

Do not hard-code obsolete model names into the project documentation.

---

# FINAL MVP DEFINITION

The MVP is complete when a user can start with an empty database and do this:

```text
Create System
    ↓
Create Object
    ↓
Create Fields
    ↓
Create another System
    ↓
Create another Object
    ↓
Create Fields
    ↓
Create Integration
    ↓
Open visual editor
    ↓
Map fields
    ↓
Insert transformation
    ↓
Provide sample rows
    ↓
Run simulation
    ↓
Inspect trace
    ↓
Save integration
    ↓
Return to landscape
    ↓
See systems and integration
    ↓
See conflicts/dependencies
```

And none of this requires a Salesforce, SAP, Mailchimp, CSV, or other connector.

That is the MVP.

Everything after that builds on the generic foundation.
