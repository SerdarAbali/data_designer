# Development assumptions

- The root `MASTER-SPEC.md` is authoritative; no separate product specification
  is required.
- `/home/sedu/architect` is the supplied project directory and is used as the
  repository rather than creating a second `~/datadesigner` tree that would
  separate the implementation from its supplied specification and planning
  documents.
- The initial stack is local/internal development: React/Vite, FastAPI, and
  PostgreSQL in Docker Compose.
- Compose development credentials are local-only defaults. Production secrets,
  TLS, and deployment configuration are not part of this skeleton.
- PostgreSQL data persists in a named volume. Stopping containers does not
  delete it.
- Health reports API and database readiness; it does not expose connection
  strings or database error details.
- Python and JavaScript dependencies are pinned for reproducibility and must be
  checked on ARM64.
- Phase 0/1 added no domain models. Phase 2 adds only the internal tenant,
  single user, and authentication/session tables; catalog, connector, and
  execution behavior remain later phases.
