# Data Designer

Data Designer is a design-time workspace for describing how business systems
exchange data. You model generic **systems → objects → fields**, define
**contracts** (integrations) between them with a visual mapping graph, test
the mappings against sample data, explore the result as an enterprise
**landscape**, and document end-to-end **scenarios** as UML sequence diagrams.

It deliberately does **not** connect to real systems: there are no
connectors, credentials, scheduling, or runtime execution. Every test runs the
built-in transformation engine against sample data only.

- **Using the app?** Read the [User Guide](./docs/user-guide.md).
- **Product specification:** [MASTER-SPEC.md](./MASTER-SPEC.md) (authoritative).
- **What is implemented today:** [SYSTEM_CAPABILITIES.md](./SYSTEM_CAPABILITIES.md).

## Quick start

Requirements: Docker Engine with Docker Compose v2 (ARM64-capable on the
Raspberry Pi host), Git, and — for host-side checks — Python 3.13 and
Node.js 20 / npm 9 or compatible.

1. Optionally copy `.env.example` to `.env` to override the development
   database credentials. The built-in defaults are local-only; never deploy
   with them.
2. Start PostgreSQL, the API, and the web dev server:

   ```sh
   make up
   ```

3. Create the single internal account (the password is asked at a hidden
   prompt and is not stored in the environment or shell history):

   ```sh
   sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api \
     python -m app.cli create-initial-user --email you@example.com
   ```

   The command refuses to create a second account. There is no public
   registration or user administration.
4. Open <http://localhost:5173> on the host, or `http://<HOST-LAN-IP>:5173`
   from another device on the same trusted LAN (for example
   `http://10.0.0.51:5173`; the address may change with DHCP), and sign in.
5. Optional: load a demo catalog (idempotent, never overwrites existing rows):

   ```sh
   sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api \
     python -m app.cli load-demo-catalog
   ```

The Makefile calls Docker through `sudo` because the developer account is not
in the root-equivalent `docker` group. If you have joined that group, use
`make DOCKER=docker up`.

### Network and security notes

- The web dev server listens on all interfaces so other LAN devices can reach
  it. The API is bound to host-localhost and PostgreSQL is not published.
- The development setup uses plain HTTP and a non-`Secure` cookie, so
  credentials travel unencrypted. Use it only on a trusted network. A real
  deployment needs HTTPS and `COOKIE_SECURE=true`.
- A short password is accepted for trusted-LAN testing; choose a strong one
  before exposing the app anywhere else.

## Architecture

| Layer | Technology | Notes |
|---|---|---|
| Web | React 19, TypeScript, Vite, @xyflow/react, Papa Parse | Catalog, Contract Designer, Landscape, Scenarios |
| API | FastAPI, Pydantic, SQLAlchemy, Alembic | Session auth + CSRF, tenant-scoped REST |
| Engine | Pure Python module in `api/app/engine` | Allowlisted node types and `fx` functions; no user code execution |
| Database | PostgreSQL (JSONB graphs and scenario documents) | Soft archive, stable UUIDs |
| Runtime | Docker Compose | `docker-compose.yml` + `docker-compose.dev.yml` |

All domain data is scoped to the tenant derived from the server-side session.
Mutating requests send the `dd_csrf` cookie value in the `X-CSRF-Token` header.

## Repository layout

| Path | Contents |
|---|---|
| `api/app/auth` | Login, sessions, CSRF |
| `api/app/catalog` | Systems, objects, fields |
| `api/app/integrations` | Contracts, graphs, dry-run, dependencies, architecture analysis |
| `api/app/scenarios` | Design-time scenarios and sample evaluation |
| `api/app/engine` | Transformation engine used by dry-run and scenario evaluation |
| `api/app/models` | SQLAlchemy models |
| `api/alembic/versions` | Database migrations (`0001` … `0007`) |
| `api/app/cli.py` | `create-initial-user`, `load-demo-catalog` |
| `api/tests` | pytest suite |
| `web/src` | React app (`CatalogWorkspace`, `IntegrationWorkspace`, `EnterpriseLandscape`, `components/*`) and vitest tests |
| `docs/` | User guide, data model, API plan, engine spec, implementation log |
| `backups/` | Local database dumps taken before migrations |

## Development workflow

```sh
make install     # host venv for api/ and npm ci for web/
make check       # ruff + pytest, frontend type-check + build, Compose config
make logs        # follow service logs
make down        # stop services, keep the database volume
make clean-data  # DESTRUCTIVE: delete the database volume
```

`make check` does not run the frontend unit tests; run them separately:

```sh
cd web && npm test          # vitest
```

Targeted backend runs from `api/`:

```sh
.venv/bin/python -m ruff check app tests alembic
.venv/bin/python -m pytest -q
```

### Database migrations

The API container entrypoint runs `alembic upgrade head` whenever the
container starts (`make up`). In development the API hot-reloads code without
restarting the container, so a newly added migration is applied only on the
next container start or when run manually. Back up first, then upgrade:

```sh
sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T db \
  pg_dump -U datadesigner datadesigner > backups/pre-upgrade.sql
sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T api \
  alembic upgrade head
```

## API

All routes except health and login are authenticated and tenant-scoped. The
main areas are `/api/auth`, `/api/catalog`, `/api/integrations` (including
`/dry-run`, `/dependencies`, and `/architecture`), and `/api/scenarios`.
Route lists, payloads, limits, and error codes are documented in
[docs/api-plan.md](./docs/api-plan.md) and summarised in
[SYSTEM_CAPABILITIES.md §4](./SYSTEM_CAPABILITIES.md#4-data-models--api-surface).

## Documentation map

| Document | Purpose |
|---|---|
| [docs/user-guide.md](./docs/user-guide.md) | How to use the application, with a walkthrough |
| [MASTER-SPEC.md](./MASTER-SPEC.md) | Authoritative product and technical specification |
| [SYSTEM_CAPABILITIES.md](./SYSTEM_CAPABILITIES.md) | Implemented features, API surface, test status |
| [docs/data-model.md](./docs/data-model.md) | Tables, graph and scenario document formats |
| [docs/api-plan.md](./docs/api-plan.md) | API boundaries, routes, dry-run contract |
| [docs/engine-spec.md](./docs/engine-spec.md) | Transformation engine semantics |
| [docs/IMPLEMENTATION-PLAN.md](./docs/IMPLEMENTATION-PLAN.md) | Phases and acceptance criteria |
| [docs/implementation-log.md](./docs/implementation-log.md) | Completed work log |
| [docs/assumptions.md](./docs/assumptions.md), [docs/blockers.md](./docs/blockers.md), [docs/dependencies.md](./docs/dependencies.md), [docs/host-environment.md](./docs/host-environment.md) | Planning notes |
