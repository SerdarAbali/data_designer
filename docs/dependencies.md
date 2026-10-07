# Runtime and development dependencies

The application containers target ARM64-capable upstream images. Exact Python
package versions are pinned in `api/requirements.txt` and
`api/requirements-dev.txt`; frontend versions and their resolved dependency
tree are pinned by `web/package.json` and `web/package-lock.json`.

Phase 1 runtime:

- FastAPI and Uvicorn for the API/ASGI server.
- SQLAlchemy and Psycopg for PostgreSQL connectivity.
- Pydantic Settings for configuration.
- Alembic for schema migration management.
- Argon2id password hashing for the single internal account.
- React, React DOM, Vite, and TypeScript for the web skeleton.
- Rollup is pinned through an npm override to a build-verified, security-fixed
  version compatible with the pinned Vite; the ARM64 production build and
  `npm audit` are part of the check gate.

Development/test tools:

- Pytest and Ruff for the Python test/lint gate.
- TypeScript compiler and Vite production build for frontend validation.
- Docker Engine and Docker Compose v2 for ARM64 multi-service execution.

Host OS package availability and versions are recorded in
`docs/host-environment.md`. Keep dependency upgrades intentional and verify
ARM64 container builds and package support when changing pins.
