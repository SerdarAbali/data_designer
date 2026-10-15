# Enterprise Workbench demo fixture

Deterministic demo data for the Phase 4 **Enterprise Workbench** plus a script
that seeds it into a live API for manual verification.

| File | Purpose |
|---|---|
| `demo.json` | The complete demo model: strategic goals, requirements, capabilities, processes/value streams, principles/constraints/risks, roles, supporting applications, and the typed links between them |
| `seed_enterprise_demo.py` | Creates a workspace with the `enterprise` discipline, a candidate state, and the full strategy-to-execution model over the API |

## Prerequisites

The dev stack must be running (`make dev` or the compose files) and a demo user
must exist in the local development database (the Solution Designer fixture
creates the same user):

```sh
cd api
HASH=$(.venv/bin/python -c "from app.auth.security import hash_password; print(hash_password('solution-demo-password'))")
printf "INSERT INTO tenants (id, name, created_at) VALUES (gen_random_uuid(), 'Solution Demo Workspace', now()) ON CONFLICT (name) DO NOTHING;\n" \
  "INSERT INTO users (id, tenant_id, email, password_hash, is_active, created_at) SELECT gen_random_uuid(), id, 'solution-demo@example.test', :'hash', true, now() FROM tenants WHERE name='Solution Demo Workspace' ON CONFLICT DO NOTHING;\n" > /tmp/solution_demo_user.sql
sudo docker compose -f ../docker-compose.yml -f ../docker-compose.dev.yml exec -T db \
  psql -U datadesigner -d datadesigner -v hash="$HASH" < /tmp/solution_demo_user.sql
```

## Seeding

```sh
api/.venv/bin/python fixtures/enterprise-architecture/seed_enterprise_demo.py
```

Override `ENTERPRISE_DEMO_BASE_URL`, `ENTERPRISE_DEMO_EMAIL`, or
`ENTERPRISE_DEMO_PASSWORD` if needed. The script prints each step and the
workspace/state identifiers to open in the app.

## Manual verification checklist

Run the seed script, open the web app, log in as the demo user, and select the
`Enterprise Demo <timestamp>` workspace in the **Enterprise** workbench:

1. **Objects view** – goals, requirements, capabilities, processes, principles
   and roles are grouped by kind; selecting "Payment processing" opens the
   inspector with its typed relationships (has process, supports, governed by,
   owned by).
2. **Capability Map** – "Payment processing" and "Customer onboarding" each list
   their processes, supporting applications, governing principles and owner role.
3. **Process Impact** – "Card settlement" and "Customer KYC" list their
   capabilities, applications and requirements; value streams are badged.
4. **Strategy Trace** – each goal expands into requirement → capabilities →
   processes → supporting applications with no gaps.
5. **Application Support** – Core Banking, Payments Gateway and Data Warehouse
   list the capabilities, processes and requirements they support/satisfy.
6. **Impact** – a candidate built on the read-only Current reports every model
   object as **Added**; the affected applications, capabilities and processes are
   listed, and unresolved constraints/risks/gaps surface when present.
7. **Candidate editing** – edit a goal's owner or add a `drives` link from the
   inspector, then switch to Current: Current must be unchanged and read-only.
8. **Save / reload** – add an object, reload the page, and confirm it persists
   under the same identifier.
9. **Shared objects** – a requirement/capability authored here is the same
   canonical object shown by the Information Modeler and the generic canvas.

## Known limitations

- A typed link can only be created (and therefore removed) in the state it was
  authored in; a candidate cannot delete a link that belongs to Current.
- `depends_on` targets are validated against the workspace, so unresolved
  dependencies only appear for edges whose target is no longer on the candidate
  canvas.
