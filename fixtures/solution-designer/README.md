# Solution Designer demo fixture

Deterministic demo data for the Phase 4 **Solution Designer** workbench plus a
script that seeds it into a live API for manual verification.

| File | Purpose |
|---|---|
| `demo.json` | The complete demo design: solution, member systems, components, provided/required interfaces, operations/events, repositories, deployment nodes, trust boundaries, and cross-links |
| `seed_solution_demo.py` | Creates a workspace with the `solution` discipline, a candidate state, and the full demo design over the API |

## Prerequisites

The dev stack must be running (`make dev` or the compose files) and a demo user
must exist in the local development database:

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
api/.venv/bin/python fixtures/solution-designer/seed_solution_demo.py
```

Override `SOLUTION_DEMO_BASE_URL`, `SOLUTION_DEMO_EMAIL`, or
`SOLUTION_DEMO_PASSWORD` if needed. The script prints each step and the
workspace/state/solution identifiers to open in the app.

## Manual verification checklist

Run the seed script, open the web app, log in as the demo user, and select the
`Solution Demo <timestamp>` workspace in the **Solution** workbench:

1. **Context view** – the solution boundary shows "Payments Platform" with owner
   "Payments Team" and both member systems (Core Banking, Payments Gateway).
2. **Decomposition** – two components (Payment API, Payment Worker) appear with
   their responsibility text and technology.
3. **Interfaces** – Payment API shows one *provided* interface (Payments API) and
   one *required* interface (Ledger Client); Payment Worker shows the reverse mix.
4. **Operations and events** – drilling into Payments API lists CreatePayment,
   GetPaymentStatus (operations) and PaymentCreated (event); Ledger Client lists
   PostLedgerEntry (command).
5. **Drill-down** – clicking Solution → Component → Interface → Operation updates
   the breadcrumb and can be navigated back up.
6. **Repositories / deployment / trust** – Payments DB, Production Cluster, and
   Public DMZ are present and their links resolve to the expected components and
   interfaces.
7. **Dynamic view** – the sequence/interaction view lays out the provided and
   required interfaces as lifelines without errors.
8. **Candidate editing** – edit a component from the candidate state, then switch
   to Current: Current must be unchanged and read-only.
9. **Stable IDs** – reload the design repeatedly; component, interface, and
   operation identifiers must not change and must not duplicate.
10. **Save / reload** – create a new component and interface, reload the page, and
    confirm both persist under the same identifiers.
