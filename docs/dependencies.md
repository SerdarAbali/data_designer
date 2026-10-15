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

Feature additions:

- ExcelJS reads `.xlsx` workbooks for the guided architecture import. It is
  imported dynamically, so the spreadsheet parser is a separate chunk that is
  only fetched when a user uploads an Excel file; the initial bundle is
  unchanged. ExcelJS depends on `uuid@8`, whose advisory
  (GHSA-w5hq-g745-h8pq, missing buffer bounds check when a `buf` argument is
  supplied) does not apply to this read path, which never passes a buffer. The
  advisory is tracked here rather than pinned away, because forcing a newer
  `uuid` breaks ExcelJS's own dependency contract.

### Installing a dependency change in the dev stack

`web/node_modules` is a Docker named volume (`web_node_modules`), so a host-side
`npm install` is not visible to the `web` container. After any change to
`web/package.json` / `web/package-lock.json`, install inside the container and
restart it:

```sh
sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T web npm ci
sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml restart web
```

Alternatively remove the volume (`docker compose down --volumes`) so the next
`make up` rebuilds it. Skipping this step makes Vite fail with
`Failed to resolve import "<package>"`.

Host OS package availability and versions are recorded in
`docs/host-environment.md`. Keep dependency upgrades intentional and verify
ARM64 container builds and package support when changing pins.
