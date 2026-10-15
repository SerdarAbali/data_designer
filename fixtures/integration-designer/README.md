# Integration Designer demo fixture

Deterministic demo data for the Phase 4 **Integration Designer** plus a script
that seeds it into a live API for manual verification.

| File | Purpose |
|---|---|
| `demo.json` | The complete demo model: CRM/ERP systems and objects, a solution component with provided/required interfaces and operations, the integration contract (pattern, status, retry/timeout/idempotency/security/routing/error handling, request and response mappings) and reference scenarios |
| `seed_integration_demo.py` | Creates a workspace with the `integration` and `solution` disciplines, a candidate state, the catalog/solution objects, the contract with its operating properties, and the reference scenarios over the API |

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
api/.venv/bin/python fixtures/integration-designer/seed_integration_demo.py
```

Override `INTEGRATION_DEMO_BASE_URL`, `INTEGRATION_DEMO_EMAIL`, or
`INTEGRATION_DEMO_PASSWORD` if needed. The script prints each step and the
workspace/state/contract identifiers to open in the app.

## Manual verification checklist

Run the seed script, open the web app, log in as the demo user, and select the
`Integration Demo <timestamp>` workspace in the **Integration** workbench:

1. **Landscape** – "Customer to Account sync" is listed with its CRM → ERP flow,
   the *Request / reply* pattern, the *Built* status, the linked producer
   interface and the mapped target field count.
2. **Interface & Contract** – the producer's `Customer Inbound API` shows its
   operations (`CreateCustomer`, `CustomerCreated`) alongside the request and
   success-response phases; the consumer side shows `ERP Client`.
3. **Message Flow** – the request and success-response phases list their
   transformations (`fx: upper`), routing ("Route by customer region") and the
   mapped target fields.
4. **Transformation & Mapping** – the summary mirrors the mapping engine, and
   "Open Mapping & Tests" deep-links into the existing Mapping & Tests workspace
   on the same contract and phase.
5. **Scenario & Sequence** – the happy-path, alternative and error scenarios are
   listed with their conformance status; "Open sequence designer" deep-links into
   the existing scenario/sequence workspace.
6. **Test & Conformance** – request/response/error coverage bars render, the
   scenario table reports Passing / Failing / Not run / Outdated, and editing the
   contract invalidates previously passing scenarios as *Outdated*.
7. **Properties** – change the pattern, implementation status, retry, timeout,
   idempotency, routing, orchestration role, authentication or error handling and
   save; reload the page and confirm the values persist (revision increments).
8. **Current/Candidate isolation** – the same contract is read-only in the
   Current state; duplicate to a candidate before editing properties.
9. **Shared objects** – the interfaces linked here are the same canonical
   solution objects shown by the Solution Designer and the canvas.

## Known limitations

- Interface links are validated against active tenant interfaces but stored as
  plain identifiers (no database foreign key), so archiving an interface does not
  cascade to the contract.
- Conformance reuses the scenario evaluation engine; a scenario becomes
  *Outdated* whenever the contract is saved after the scenario.
- The workbench lists interfaces tenant-wide; candidate-authored interfaces are
  visible from the Current state's read-only projection.
