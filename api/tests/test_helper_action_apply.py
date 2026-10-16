"""Slice 4 transactional apply, conflict-safe undo, and composite acceptance."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.helper_actions import service as helper_service
from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    ArchitectureStateMember,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    HelperAuditEvent,
    HelperChangeOperation,
    HelperChangeSet,
    Integration,
    IntegrationFieldRef,
    Scenario,
    Tenant,
    User,
    Workspace,
)

FULL = ["enterprise", "information", "solution", "integration"]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("app.config.settings.cookie_secure", False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with testing_sessions() as db:
            yield db

    main.app.dependency_overrides[get_session] = override_session
    with testing_sessions.begin() as db:
        tenant = Tenant(name=f"apply-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="apply@example.test",
                password_hash=hash_password("apply-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "apply@example.test", "password": "apply-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _workspace(test_client, headers, disciplines=None):
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": f"Apply {uuid4().hex[:8]}", "disciplines": disciplines or FULL},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _system(test_client, headers, name="CRM", kind="application"):
    response = test_client.post(
        "/api/catalog/systems", json={"name": name, "kind": kind}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _catalog_object(test_client, headers, system_id, name):
    response = test_client.post(
        f"/api/catalog/systems/{system_id}/objects",
        json={"name": name, "label": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _catalog_field(
    test_client, headers, object_id, name, data_type="string", required=False, external_id=None
):
    payload = {"name": name, "label": name, "data_type": data_type, "required": required}
    if external_id is not None:
        payload["external_identifier"] = external_id
    response = test_client.post(
        f"/api/catalog/objects/{object_id}/fields", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _solution(test_client, headers, workspace_id, state_id, name):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions",
        json={"state_id": state_id, "name": name, "position": {"x": 0.0, "y": 0.0}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["solution"]["solution_object_id"]


def _component(test_client, headers, workspace_id, state_id, solution_id, name):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions/{solution_id}/components",
        json={"state_id": state_id, "name": name, "position": {"x": 0.0, "y": 0.0}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return next(item["object_id"] for item in response.json()["components"] if item["name"] == name)


def _interface(test_client, headers, workspace_id, state_id, component_id, name, direction):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/components/{component_id}/interfaces",
        json={"state_id": state_id, "name": name, "direction": direction},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    for component in response.json()["components"]:
        if component["object_id"] != component_id:
            continue
        for iface in component["interfaces"]:
            if iface["name"] == name:
                return iface["object_id"]
    raise AssertionError("interface not found")


def _propose(test_client, headers, workspace_id, helper, body):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/helper-actions/proposals/{helper}",
        json=body,
        headers=headers,
    )


def _validate(test_client, headers, workspace_id, change_set_id):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/validate",
        headers=headers,
    )


def _approve(test_client, headers, workspace_id, change_set_id):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/approve",
        headers=headers,
    )


def _apply(test_client, headers, workspace_id, change_set_id):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/apply",
        headers=headers,
    )


def _undo(test_client, headers, workspace_id, change_set_id):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/helper-actions/change-sets/{change_set_id}/undo",
        headers=headers,
    )


def _approve_and_apply(test_client, headers, workspace_id, body):
    assert _validate(test_client, headers, workspace_id, body["id"]).json()["status"] == "validated"
    assert _approve(test_client, headers, workspace_id, body["id"]).status_code == 200
    return _apply(test_client, headers, workspace_id, body["id"])


def _counts(sessions):
    with sessions() as db:
        return {
            "architecture_objects": db.scalar(select(func.count(ArchitectureObject.id))),
            "relationships": db.scalar(select(func.count(ArchitectureRelationship.id))),
            "state_members": db.scalar(select(func.count(ArchitectureStateMember.id))),
            "systems": db.scalar(select(func.count(CatalogSystem.id))),
            "catalog_objects": db.scalar(select(func.count(CatalogObject.id))),
            "catalog_fields": db.scalar(select(func.count(CatalogField.id))),
            "integrations": db.scalar(select(func.count(Integration.id))),
            "scenarios": db.scalar(select(func.count(Scenario.id))),
            "field_refs": db.scalar(select(func.count(IntegrationFieldRef.id))),
        }


def _events(sessions, change_set_id):
    with sessions() as db:
        rows = db.scalars(
            select(HelperAuditEvent.event_type)
            .where(HelperAuditEvent.change_set_id == UUID(str(change_set_id)))
            .order_by(HelperAuditEvent.created_at, HelperAuditEvent.id)
        ).all()
        return list(rows)


def _state_json(sessions, state_id):
    with sessions() as db:
        state = db.get(ArchitectureState, UUID(str(state_id)))
        return {"nodes": state.nodes, "relationships": state.relationships}


def _tenant_id(sessions, workspace_id):
    with sessions() as db:
        return db.get(Workspace, UUID(str(workspace_id))).tenant_id


def _strategy_body(
    candidate, names=("Reduce Churn", "Faster Onboarding", "Billing", "Invoice Run")
):
    return {
        "state_id": candidate["id"],
        "summary": "Customer onboarding strategy",
        "nodes": [
            {"key": "goal", "kind": "business_goal", "name": names[0]},
            {"key": "req", "kind": "business_requirement", "name": names[1]},
            {"key": "cap", "kind": "business_capability", "name": names[2]},
            {"key": "proc", "kind": "business_process", "name": names[3]},
        ],
        "links": [
            {"relationship_type": "drives", "source_key": "goal", "target_key": "req"},
            {"relationship_type": "needs", "source_key": "req", "target_key": "cap"},
            {"relationship_type": "has_process", "source_key": "cap", "target_key": "proc"},
        ],
    }


# --- apply preconditions -----------------------------------------------------


def test_apply_requires_approved_status(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client, headers, workspace["id"], "propose_strategy_chain", _strategy_body(candidate)
    ).json()
    before = _counts(sessions)
    response = _apply(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_approved"
    assert _counts(sessions) == before


def test_apply_rejects_stale_hash(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client, headers, workspace["id"], "propose_strategy_chain", _strategy_body(candidate)
    ).json()
    assert _validate(test_client, headers, workspace["id"], body["id"]).status_code == 200
    assert _approve(test_client, headers, workspace["id"], body["id"]).status_code == 200
    with sessions.begin() as db:
        op = db.scalar(
            select(HelperChangeOperation).where(
                HelperChangeOperation.change_set_id == UUID(body["id"])
            )
        )
        op.proposed_value = {**op.proposed_value, "tampered": True}
    before = _counts(sessions)
    response = _apply(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"proposal_stale", "approval_hash_mismatch"}
    assert _counts(sessions) == before


def test_apply_rejects_current_target(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client, headers, workspace["id"], "propose_strategy_chain", _strategy_body(candidate)
    ).json()
    assert _validate(test_client, headers, workspace["id"], body["id"]).status_code == 200
    assert _approve(test_client, headers, workspace["id"], body["id"]).status_code == 200
    with sessions.begin() as db:
        change_set = db.get(HelperChangeSet, UUID(body["id"]))
        operations = helper_service.load_operations(db, change_set.id)
        change_set.state_id = UUID(current["id"])
        change_set.proposal_hash = helper_service.compute_proposal_hash(change_set, operations)
        change_set.approved_hash = change_set.proposal_hash
    before = _counts(sessions)
    response = _apply(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert _counts(sessions) == before


def test_apply_rejects_unresolved_required_decisions(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    account_field = _catalog_field(test_client, headers, account, "Account Id")
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_direct_integration",
        {
            "state_id": candidate["id"],
            "summary": "Integration with an unresolved mapping",
            "contract": {
                "name": "CRM Customer Onboarding",
                "source_system_id": crm["id"],
                "source_object_id": customer,
                "target_system_id": billing["id"],
                "target_object_id": account,
                "interaction_type": "REQUEST_RESPONSE",
                "pattern": "request_reply",
            },
            "mappings": [
                {
                    "key": "unknown",
                    "phase": "request",
                    "source_field_name": "Missing",
                    "target_field_id": account_field,
                    "required": True,
                }
            ],
        },
    ).json()
    assert _validate(test_client, headers, workspace["id"], body["id"]).status_code == 200
    with sessions.begin() as db:
        change_set = db.get(HelperChangeSet, UUID(body["id"]))
        change_set.status = "approved"
        change_set.approved_by = change_set.proposed_by
        change_set.approved_hash = change_set.proposal_hash
    before = _counts(sessions)
    response = _apply(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"unresolved_decisions", "validation_failed"}
    assert _counts(sessions) == before


def test_apply_rejects_unknown_operation_types(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client, headers, workspace["id"], "propose_strategy_chain", _strategy_body(candidate)
    ).json()
    assert _validate(test_client, headers, workspace["id"], body["id"]).status_code == 200
    assert _approve(test_client, headers, workspace["id"], body["id"]).status_code == 200
    with sessions.begin() as db:
        change_set = db.get(HelperChangeSet, UUID(body["id"]))
        db.add(
            HelperChangeOperation(
                change_set_id=change_set.id,
                tenant_id=change_set.tenant_id,
                workspace_id=change_set.workspace_id,
                operation_id="op-bogus",
                ordinal=99,
                domain_action="execute_sql",
                target_type="architecture_object",
                proposed_value={"payload": "DROP TABLE users"},
                depends_on=[],
                validation_status="valid",
                validation_issues=[],
                explanation="not allowed",
            )
        )
        db.flush()
        operations = helper_service.load_operations(db, change_set.id)
        change_set.proposal_hash = helper_service.compute_proposal_hash(change_set, operations)
        change_set.approved_hash = change_set.proposal_hash
    before = _counts(sessions)
    response = _apply(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "unknown_operation"
    assert _counts(sessions) == before


# --- enterprise apply / undo -------------------------------------------------


def test_enterprise_apply_persists_and_undo_reverses(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace(test_client, headers)
    current_before = _state_json(sessions, current["id"])
    body = _propose(
        test_client, headers, workspace["id"], "propose_strategy_chain", _strategy_body(candidate)
    ).json()
    before = _counts(sessions)

    result = _approve_and_apply(test_client, headers, workspace["id"], body)
    assert result.status_code == 200, result.text
    applied = result.json()
    assert applied["change_set"]["status"] == "applied"
    assert applied["applied_operation_count"] == len(body["operations"])
    # Temporary ids resolved deterministically to canonical ids.
    for temp, real in applied["resolution_map"].items():
        assert temp.startswith("tmp:")
        assert UUID(real)

    after = _counts(sessions)
    assert after["architecture_objects"] == before["architecture_objects"] + 4
    assert after["relationships"] == before["relationships"] + 3
    # Current state is byte-identical.
    assert _state_json(sessions, current["id"]) == current_before

    # Ownership metadata recorded on every operation.
    detail = test_client.get(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{body['id']}"
    ).json()
    for op in detail["operations"]:
        assert op["apply_status"] == "applied"
        assert op["applied_id"] is not None
        assert op["ownership"].get("role")
        assert op["post_fingerprint"]

    events = _events(sessions, body["id"])
    for expected in (
        "apply_requested",
        "apply_started",
        "operation_applied",
        "apply_completed",
    ):
        assert expected in events

    # Undo restores the workspace.
    undo = _undo(test_client, headers, workspace["id"], body["id"])
    assert undo.status_code == 200, undo.text
    assert undo.json()["change_set"]["status"] == "undone"
    assert _counts(sessions) == before
    assert _state_json(sessions, current["id"]) == current_before
    # Idempotent rejection after completion.
    second = _undo(test_client, headers, workspace["id"], body["id"])
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "not_applied"


def test_apply_rolls_back_on_operation_failure(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    # An existing active scenario whose name collides with the proposed one.
    existing = test_client.post(
        "/api/scenarios",
        json={
            "name": "Colliding scenario",
            "category": "happy_path",
            "document": {
                "version": 1,
                "preconditions": "p",
                "trigger": "t",
                "participants": [],
                "items": [],
            },
        },
        headers=headers,
    )
    assert existing.status_code == 201, existing.text

    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_direct_integration",
        {
            "state_id": candidate["id"],
            "summary": "A scenario name that collides at apply time",
            "contract": {
                "name": "CRM Customer Onboarding",
                "source_system_id": crm["id"],
                "source_object_id": customer,
                "target_system_id": billing["id"],
                "target_object_id": account,
                "interaction_type": "REQUEST_RESPONSE",
                "pattern": "request_reply",
            },
            "scenarios": [
                {"key": "a", "name": "Colliding scenario", "scenario_type": "happy_path"}
            ],
        },
    ).json()
    validated = _validate(test_client, headers, workspace["id"], body["id"]).json()
    assert validated["status"] == "validated", validated.get("validation_summary")
    assert _approve(test_client, headers, workspace["id"], body["id"]).status_code == 200
    before = _counts(sessions)
    response = _apply(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    # Nothing was written: no contract, no new scenario, no field refs.
    assert _counts(sessions) == before
    events = _events(sessions, body["id"])
    assert "apply_rolled_back" in events


def test_canonical_object_reuse_is_unchanged_and_preserved_on_undo(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    # Create a canonical entity directly, then propose an attribute over it.
    entity = test_client.post(
        f"/api/workspaces/{workspace['id']}/information/entities",
        json={
            "state_id": candidate["id"],
            "name": "Customer",
            "position": {"x": 0.0, "y": 0.0},
            "owner": "Ops",
            "authoritative_system_id": _system(test_client, headers, name=f"S {uuid4().hex[:5]}")[
                "id"
            ],
        },
        headers=headers,
    )
    assert entity.status_code == 201, entity.text
    entity_id = entity.json()["entity"]["object_id"]
    before = _counts(sessions)
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_information_model",
        {
            "state_id": candidate["id"],
            "summary": "Reuse the existing entity",
            "nodes": [
                {
                    "key": "ent",
                    "kind": "information_object",
                    "name": "Customer",
                    "existing_object_id": entity_id,
                },
                {
                    "key": "attr",
                    "kind": "information_attribute",
                    "name": "Email",
                    "parent_key": "ent",
                    "data_type": "string",
                },
            ],
        },
    ).json()
    result = _approve_and_apply(test_client, headers, workspace["id"], body)
    assert result.status_code == 200, result.text
    with sessions() as db:
        entity_row = db.get(ArchitectureObject, UUID(entity_id))
        assert entity_row is not None  # reused object still present
    # Undo removes only the created attribute, not the reused entity.
    assert _undo(test_client, headers, workspace["id"], body["id"]).status_code == 200
    with sessions() as db:
        assert db.get(ArchitectureObject, UUID(entity_id)) is not None
    after = _counts(sessions)
    # Undo removed only the created attribute; the reused entity remains.
    assert after["architecture_objects"] == before["architecture_objects"]


def test_catalog_creation_is_impossible(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    entity = test_client.post(
        f"/api/workspaces/{workspace['id']}/information/entities",
        json={
            "state_id": candidate["id"],
            "name": "Customer",
            "position": {"x": 0.0, "y": 0.0},
            "owner": "Ops",
            "authoritative_system_id": crm["id"],
        },
        headers=headers,
    ).json()
    entity_id = entity["entity"]["object_id"]
    before = _counts(sessions)
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_information_model",
        {
            "state_id": candidate["id"],
            "summary": "No Catalog creation",
            "nodes": [
                {"key": "sys", "kind": "catalog_system", "name": "CRM", "system_id": crm["id"]},
                {
                    "key": "ent",
                    "kind": "information_object",
                    "name": "Customer",
                    "existing_object_id": entity_id,
                },
                {
                    "key": "attr",
                    "kind": "information_attribute",
                    "name": "Email",
                    "parent_key": "ent",
                },
            ],
        },
    ).json()
    assert _approve_and_apply(test_client, headers, workspace["id"], body).status_code == 200
    after = _counts(sessions)
    assert after["systems"] == before["systems"]
    assert after["catalog_objects"] == before["catalog_objects"]
    assert after["catalog_fields"] == before["catalog_fields"]


# --- integration apply / undo ------------------------------------------------


def _seed_contract(
    test_client,
    headers,
    *,
    source_system_id,
    source_object_id,
    target_system_id,
    target_object_id,
    name,
    producer_interface_id=None,
    consumer_interface_id=None,
):
    response = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": source_system_id,
            "source_object_id": source_object_id,
            "target_system_id": target_system_id,
            "target_object_id": target_object_id,
            "name": name,
            "interaction_type": "REQUEST_RESPONSE",
            "pattern": "request_reply",
            "producer_interface_id": producer_interface_id,
            "consumer_interface_id": consumer_interface_id,
            "graph": {"version": 1, "nodes": [], "edges": []},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _contract_snapshot(sessions, contract_id):
    with sessions() as db:
        row = db.get(Integration, UUID(str(contract_id)))
        return {
            "name": row.name,
            "revision": row.revision,
            "interaction_type": row.interaction_type,
            "pattern": row.pattern,
            "specification": dict(row.specification or {}),
        }


def test_existing_contract_reuse_is_byte_identical(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    contract_id = _seed_contract(
        test_client,
        headers,
        source_system_id=crm["id"],
        source_object_id=customer,
        target_system_id=billing["id"],
        target_object_id=account,
        name="CRM Customer Onboarding",
    )
    snapshot = _contract_snapshot(sessions, contract_id)
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_direct_integration",
        {
            "state_id": candidate["id"],
            "summary": "Reuse the existing contract",
            "contract": {
                "name": "CRM Customer Onboarding",
                "source_system_id": crm["id"],
                "source_object_id": customer,
                "target_system_id": billing["id"],
                "target_object_id": account,
                "interaction_type": "REQUEST_RESPONSE",
                "pattern": "request_reply",
            },
        },
    ).json()
    assert body["operations"][0]["domain_action"] == "reuse_contract"
    assert _approve_and_apply(test_client, headers, workspace["id"], body).status_code == 200
    assert _contract_snapshot(sessions, contract_id) == snapshot
    assert _undo(test_client, headers, workspace["id"], body["id"]).status_code == 200
    assert _contract_snapshot(sessions, contract_id) == snapshot


def test_new_contract_scenario_apply_records_revision_and_undo(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    customer_field = _catalog_field(test_client, headers, customer, "Customer Id")
    account_field = _catalog_field(test_client, headers, account, "Account Id")
    display = _catalog_field(test_client, headers, account, "Display Name")
    before = _counts(sessions)
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_direct_integration",
        {
            "state_id": candidate["id"],
            "summary": "New contract",
            "contract": {
                "name": "Customer Onboarding",
                "source_system_id": crm["id"],
                "source_object_id": customer,
                "target_system_id": billing["id"],
                "target_object_id": account,
                "interaction_type": "REQUEST_RESPONSE",
                "pattern": "request_reply",
            },
            "mappings": [
                {
                    "key": "src-tgt",
                    "phase": "request",
                    "source_field_id": customer_field,
                    "target_field_id": account_field,
                }
            ],
            "transformations": [
                {
                    "key": "display",
                    "node_type": "concat",
                    "source_field_ids": [customer_field],
                    "target_field_id": display,
                    "config": {"separator": " "},
                    "reason": "Compose a display name",
                }
            ],
            "resilience": {
                "retry": {"max_attempts": 2, "backoff": "linear"},
                "timeout_ms": 3000,
                "idempotent": True,
                "idempotency_key_field_id": str(customer_field),
            },
            "scenarios": [
                {
                    "key": "happy",
                    "name": "Onboarding happy path",
                    "scenario_type": "happy_path",
                    "phase": "request",
                    "synthetic_values": {str(customer_field): "cust-1"},
                }
            ],
            "conformance": [
                {
                    "key": "cov",
                    "expectation_type": "mapping_coverage",
                    "phase": "request",
                    "coverage_min": 1.0,
                }
            ],
        },
    ).json()
    result = _approve_and_apply(test_client, headers, workspace["id"], body)
    assert result.status_code == 200, result.text
    applied = result.json()
    contract_revision = applied["contract_revisions"][0]
    assert contract_revision["revision"] == 1
    after = _counts(sessions)
    assert after["integrations"] == before["integrations"] + 1
    assert after["scenarios"] == before["scenarios"] + 1
    assert after["field_refs"] >= before["field_refs"] + 2

    # Mapping & Tests can load and validate the created graph.
    from app.integrations.graph import GraphDocument

    with sessions() as db:
        contract = db.get(Integration, UUID(contract_revision["contract_id"]))
        graph = GraphDocument.model_validate(contract.graph)
        assert graph.nodes  # the transformation was persisted
        assert (
            db.scalar(
                select(func.count(IntegrationFieldRef.id)).where(
                    IntegrationFieldRef.integration_id == contract.id
                )
            )
            >= 2
        )

    # No scenario was executed automatically (no evaluation state persisted).
    events = _events(sessions, body["id"])
    assert "apply_completed" in events

    undo = _undo(test_client, headers, workspace["id"], body["id"])
    assert undo.status_code == 200, undo.text
    assert _counts(sessions) == before


# --- undo conflicts ----------------------------------------------------------


def _approved_enterprise(client, discipline_names=None):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_strategy_chain",
        _strategy_body(
            candidate,
            discipline_names or ("Reduce Churn", "Faster Onboarding", "Billing", "Invoice Run"),
        ),
    ).json()
    assert _approve_and_apply(test_client, headers, workspace["id"], body).status_code == 200
    return test_client, sessions, headers, workspace, current, candidate, body


def test_undo_conflict_when_object_changed(client):
    test_client, sessions, headers, workspace, _current, _candidate, body = _approved_enterprise(
        client
    )
    with sessions.begin() as db:
        op = db.scalar(
            select(HelperChangeOperation)
            .where(HelperChangeOperation.change_set_id == UUID(body["id"]))
            .where(HelperChangeOperation.domain_action == "create_object")
        )
        from app.models import BusinessGoal

        typed = db.scalar(select(BusinessGoal).where(BusinessGoal.object_id == op.applied_id))
        typed.name = "Renamed after apply"
    before = _counts(sessions)
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "undo_conflict"
    assert any(item["code"] == "object_modified" for item in response.json()["detail"]["conflicts"])
    assert _counts(sessions) == before  # all-or-nothing


def test_undo_conflict_when_relationship_changed(client):
    test_client, sessions, headers, workspace, _current, _candidate, body = _approved_enterprise(
        client
    )
    with sessions.begin() as db:
        op = db.scalar(
            select(HelperChangeOperation)
            .where(HelperChangeOperation.change_set_id == UUID(body["id"]))
            .where(HelperChangeOperation.domain_action == "create_link")
        )
        edge = db.get(ArchitectureRelationship, op.applied_id)
        edge.properties = {"tampered": True}
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert any(
        item["code"] == "relationship_modified" for item in response.json()["detail"]["conflicts"]
    )


def test_undo_conflict_when_external_reference_added(client):
    test_client, sessions, headers, workspace, _current, candidate, body = _approved_enterprise(
        client
    )
    with sessions.begin() as db:
        op = db.scalar(
            select(HelperChangeOperation)
            .where(HelperChangeOperation.change_set_id == UUID(body["id"]))
            .where(HelperChangeOperation.domain_action == "create_object")
        )
        created_id = op.applied_id
    other = _system(test_client, headers, name=f"Ext {uuid4().hex[:5]}")
    # An external relationship referencing the created object.
    with sessions.begin() as db:
        registry = db.get(ArchitectureObject, created_id)
        state = db.get(ArchitectureState, UUID(candidate["id"]))
        db.add(
            ArchitectureRelationship(
                id=uuid4(),
                tenant_id=registry.tenant_id,
                source_object_id=created_id,
                target_object_id=UUID(other["id"]),
                relationship_type="depends_on",
                properties={},
                created_in_state_id=state.id,
            )
        )
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert any(
        item["code"] == "external_reference" for item in response.json()["detail"]["conflicts"]
    )


def test_undo_conflict_when_contract_revision_changes(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_contract",
        {
            "state_id": candidate["id"],
            "summary": "New contract",
            "contract": {
                "name": "Customer Onboarding",
                "source_system_id": crm["id"],
                "source_object_id": customer,
                "target_system_id": billing["id"],
                "target_object_id": account,
                "interaction_type": "REQUEST_RESPONSE",
                "pattern": "request_reply",
            },
        },
    ).json()
    applied = _approve_and_apply(test_client, headers, workspace["id"], body).json()
    contract_id = applied["contract_revisions"][0]["contract_id"]
    with sessions.begin() as db:
        contract = db.get(Integration, UUID(contract_id))
        contract.revision = 2
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert any(
        item["code"] == "contract_modified" for item in response.json()["detail"]["conflicts"]
    )


def test_undo_conflict_when_scenario_references_contract(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_contract",
        {
            "state_id": candidate["id"],
            "summary": "New contract",
            "contract": {
                "name": "Customer Onboarding",
                "source_system_id": crm["id"],
                "source_object_id": customer,
                "target_system_id": billing["id"],
                "target_object_id": account,
                "interaction_type": "REQUEST_RESPONSE",
                "pattern": "request_reply",
            },
        },
    ).json()
    applied = _approve_and_apply(test_client, headers, workspace["id"], body).json()
    contract_id = applied["contract_revisions"][0]["contract_id"]
    scenario = test_client.post(
        "/api/scenarios",
        json={
            "name": "External scenario",
            "category": "happy_path",
            "scope_integration_id": contract_id,
            "document": {
                "version": 1,
                "preconditions": "p",
                "trigger": "t",
                "participants": [
                    {"id": "source", "kind": "system", "systemId": crm["id"]},
                    {"id": "target", "kind": "system", "systemId": billing["id"]},
                ],
                "contractIds": [contract_id],
                "items": [
                    {
                        "id": "step-1",
                        "kind": "contract",
                        "contractId": contract_id,
                        "phase": "request",
                    }
                ],
            },
        },
        headers=headers,
    )
    assert scenario.status_code == 201, scenario.text
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert any(
        item["code"] == "external_reference" for item in response.json()["detail"]["conflicts"]
    )


# --- composite orchestration -------------------------------------------------


def test_composite_respects_disciplines_and_makes_no_writes(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_end_to_end_architecture",
        {
            "state_id": candidate["id"],
            "summary": "Composite",
            "business_intent": "Onboard customers faster",
            "requested_disciplines": ["enterprise"],
            "enterprise": {
                "nodes": [
                    {"key": "goal", "kind": "business_goal", "name": "Onboard"},
                    {"key": "proc", "kind": "business_process", "name": "Process"},
                ],
                "links": [],
            },
        },
    ).json()
    assert body["input_summary"]["disciplines_built"] == ["enterprise"]
    before = _counts(sessions)
    assert _validate(test_client, headers, workspace["id"], body["id"]).status_code == 200
    assert _counts(sessions) == before  # zero architecture-domain writes
    assert "composite_proposal_created" in _events(sessions, body["id"])

    # A disabled discipline requested explicitly is rejected.
    solution_only = _workspace(test_client, headers, disciplines=["solution", "integration"])
    disabled = _propose(
        test_client,
        headers,
        solution_only[0]["id"],
        "propose_end_to_end_architecture",
        {
            "state_id": solution_only[2]["id"],
            "summary": "Disabled",
            "requested_disciplines": ["enterprise"],
        },
    )
    assert disabled.status_code == 422
    assert disabled.json()["detail"]["code"] == "disabled_discipline"


def test_apply_respects_dependency_order(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client, headers, workspace["id"], "propose_strategy_chain", _strategy_body(candidate)
    ).json()
    result = _approve_and_apply(test_client, headers, workspace["id"], body).json()
    order = [item["operation_id"] for item in result["applied_operations"]]
    by_id = {op["operation_id"]: op for op in body["operations"]}
    object_positions = [
        order.index(op["operation_id"])
        for op in body["operations"]
        if op["domain_action"] == "create_object"
    ]
    link_positions = [
        order.index(op["operation_id"])
        for op in body["operations"]
        if op["domain_action"] == "create_link"
    ]
    assert max(object_positions) < min(link_positions)
    assert by_id  # sanity


def test_undo_conflict_when_mapping_graph_changes(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    source_field = _catalog_field(test_client, headers, customer, "Customer Id")
    target_field = _catalog_field(test_client, headers, account, "Account Id")
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_direct_integration",
        {
            "state_id": candidate["id"],
            "summary": "Mapping change conflict",
            "contract": {
                "name": "Customer Onboarding",
                "source_system_id": crm["id"],
                "source_object_id": customer,
                "target_system_id": billing["id"],
                "target_object_id": account,
                "interaction_type": "REQUEST_RESPONSE",
                "pattern": "request_reply",
            },
            "mappings": [
                {
                    "key": "m",
                    "phase": "request",
                    "source_field_id": source_field,
                    "target_field_id": target_field,
                }
            ],
        },
    ).json()
    _approve_and_apply(test_client, headers, workspace["id"], body)
    with sessions.begin() as db:
        ref = db.scalar(
            select(IntegrationFieldRef).where(IntegrationFieldRef.direction == "target")
        )
        db.delete(ref)
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert any(
        item["code"] == "mapping_modified" for item in response.json()["detail"]["conflicts"]
    )


def test_undo_conflict_when_state_membership_changes(client):
    test_client, sessions, headers, workspace, _current, _candidate, body = _approved_enterprise(
        client
    )
    with sessions.begin() as db:
        op = db.scalar(
            select(HelperChangeOperation)
            .where(HelperChangeOperation.change_set_id == UUID(body["id"]))
            .where(HelperChangeOperation.domain_action == "create_object")
        )
        state = db.get(ArchitectureState, UUID(op.ownership["state_id"]))
        state.nodes = [
            node for node in state.nodes if str(node.get("object_id")) != str(op.applied_id)
        ]
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert any(
        item["code"] == "membership_modified" for item in response.json()["detail"]["conflicts"]
    )


def test_undo_refuses_when_proposal_becomes_stale(client):
    test_client, sessions, headers, workspace, _current, _candidate, body = _approved_enterprise(
        client
    )
    with sessions.begin() as db:
        op = db.scalar(
            select(HelperChangeOperation).where(
                HelperChangeOperation.change_set_id == UUID(body["id"])
            )
        )
        op.proposed_value = {**op.proposed_value, "tampered_after_apply": True}
    response = _undo(test_client, headers, workspace["id"], body["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "proposal_stale"


def test_end_to_end_acceptance(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace(test_client, headers)
    current_before = _state_json(sessions, current["id"])

    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:5]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:5]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    email_field = _catalog_field(test_client, headers, customer, "Email")
    account_field = _catalog_field(test_client, headers, account, "Account Id")

    solution_id = _solution(
        test_client, headers, workspace["id"], candidate["id"], "Onboarding Solution"
    )
    component_id = _component(
        test_client, headers, workspace["id"], candidate["id"], solution_id, "Onboarding Service"
    )
    provided = _interface(
        test_client,
        headers,
        workspace["id"],
        candidate["id"],
        component_id,
        "Onboarding API",
        "provided",
    )
    required = _interface(
        test_client,
        headers,
        workspace["id"],
        candidate["id"],
        component_id,
        "Billing API",
        "required",
    )
    catalog_counts = _counts(sessions)

    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_end_to_end_architecture",
        {
            "state_id": candidate["id"],
            "summary": "Customer onboarding end to end",
            "business_intent": "Onboard customers faster with less manual work",
            "requested_disciplines": ["enterprise", "information", "solution", "integration"],
            "desired_outcomes": ["Faster onboarding", "Fewer errors"],
            "enterprise": {
                "nodes": [
                    {"key": "goal", "kind": "business_goal", "name": "Faster Onboarding"},
                    {"key": "req", "kind": "business_requirement", "name": "Automate KYC"},
                    {"key": "cap", "kind": "business_capability", "name": "Customer Onboarding"},
                    {"key": "proc", "kind": "business_process", "name": "Onboarding Process"},
                ],
                "links": [
                    {"relationship_type": "drives", "source_key": "goal", "target_key": "req"},
                    {"relationship_type": "needs", "source_key": "req", "target_key": "cap"},
                    {"relationship_type": "has_process", "source_key": "cap", "target_key": "proc"},
                ],
            },
            "information": {
                "nodes": [
                    {
                        "key": "entity",
                        "kind": "information_object",
                        "name": "Customer",
                        "owner": "Ops",
                        "system_id": crm["id"],
                    },
                    {
                        "key": "acct",
                        "kind": "information_object",
                        "name": "Account",
                        "owner": "Finance",
                        "system_id": billing["id"],
                    },
                    {
                        "key": "email",
                        "kind": "information_attribute",
                        "name": "Email",
                        "parent_key": "entity",
                        "data_type": "string",
                        "required": True,
                    },
                ],
                "links": [
                    {
                        "relationship_type": "references",
                        "source_key": "entity",
                        "target_key": "acct",
                    }
                ],
                "realizations": [{"key": "email", "catalog_field_id": email_field}],
            },
            "solution": {
                "nodes": [
                    {"key": "sol", "kind": "solution_boundary", "name": "Onboarding Domain"},
                    {
                        "key": "comp",
                        "kind": "component",
                        "name": "Onboarding Service",
                        "parent_key": "sol",
                    },
                    {
                        "key": "iface",
                        "kind": "interface",
                        "name": "Management API",
                        "parent_key": "comp",
                        "direction": "provided",
                    },
                    {
                        "key": "op",
                        "kind": "interface_operation",
                        "name": "CreateCustomer",
                        "parent_key": "iface",
                        "operation_kind": "command",
                    },
                    {
                        "key": "repo",
                        "kind": "data_repository",
                        "name": "Onboarding DB",
                        "parent_key": "sol",
                    },
                ],
                "links": [
                    {
                        "relationship_type": "uses_repository",
                        "source_key": "comp",
                        "target_key": "repo",
                    }
                ],
            },
            "integration": {
                "contract": {
                    "name": "Customer Onboarding",
                    "source_system_id": crm["id"],
                    "source_object_id": customer,
                    "target_system_id": billing["id"],
                    "target_object_id": account,
                    "interaction_type": "REQUEST_RESPONSE",
                    "pattern": "request_reply",
                    "producer_interface_id": provided,
                    "consumer_interface_id": required,
                },
                "mappings": [
                    {
                        "key": "acct",
                        "phase": "request",
                        "source_field_id": email_field,
                        "target_field_id": account_field,
                    }
                ],
                "scenarios": [
                    {
                        "key": "happy",
                        "name": "Onboarding happy path",
                        "scenario_type": "happy_path",
                        "phase": "request",
                        "synthetic_values": {str(email_field): "a@b.test"},
                    }
                ],
                "conformance": [
                    {
                        "key": "cov",
                        "expectation_type": "mapping_coverage",
                        "phase": "request",
                        "coverage_min": 1.0,
                    }
                ],
            },
        },
    ).json()

    # Proposal makes zero architecture-domain writes.
    assert _counts(sessions)["architecture_objects"] == catalog_counts["architecture_objects"]
    assert _counts(sessions)["integrations"] == catalog_counts["integrations"]

    # Apply is impossible before approval.
    assert _apply(test_client, headers, workspace["id"], body["id"]).status_code == 409

    assert _validate(test_client, headers, workspace["id"], body["id"]).status_code == 200
    assert _approve(test_client, headers, workspace["id"], body["id"]).status_code == 200
    applied = _apply(test_client, headers, workspace["id"], body["id"])
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["change_set"]["status"] == "applied"
    assert set(result["affected_workbenches"]) == {
        "enterprise",
        "information",
        "solution",
        "integration",
    }
    assert result["resolution_map"]

    after = _counts(sessions)
    assert after["architecture_objects"] > catalog_counts["architecture_objects"]
    assert after["relationships"] > catalog_counts["relationships"]
    assert after["integrations"] == catalog_counts["integrations"] + 1
    assert after["scenarios"] == catalog_counts["scenarios"] + 1
    # Catalog inventory untouched.
    assert after["systems"] == catalog_counts["systems"]
    assert after["catalog_objects"] == catalog_counts["catalog_objects"]
    assert after["catalog_fields"] == catalog_counts["catalog_fields"]
    # Current is byte-identical.
    assert _state_json(sessions, current["id"]) == current_before

    # Cross-discipline result: enterprise intent, information, solution, and the
    # integration contract + scenario evidence coexist in the candidate.
    from app.models import BusinessGoal, InformationObject, SolutionBoundary

    with sessions() as db:
        tenant_id = _tenant_id(sessions, workspace["id"])
        assert (
            db.scalar(
                select(BusinessGoal).where(
                    BusinessGoal.tenant_id == tenant_id, BusinessGoal.name == "Faster Onboarding"
                )
            )
            is not None
        )
        assert (
            db.scalar(
                select(InformationObject).where(
                    InformationObject.tenant_id == tenant_id, InformationObject.name == "Customer"
                )
            )
            is not None
        )
        assert (
            db.scalar(
                select(SolutionBoundary).where(
                    SolutionBoundary.tenant_id == tenant_id,
                    SolutionBoundary.name == "Onboarding Domain",
                )
            )
            is not None
        )
        scenario = db.scalar(
            select(Scenario).where(
                Scenario.tenant_id == tenant_id, Scenario.name == "Onboarding happy path"
            )
        )
        assert scenario is not None
        assert str(scenario.scope_integration_id) in result["resolution_map"].values()

    # Undo removes only change-set-owned data.
    undo = _undo(test_client, headers, workspace["id"], body["id"])
    assert undo.status_code == 200, undo.text
    assert undo.json()["change_set"]["status"] == "undone"
    reverted = _counts(sessions)
    assert reverted["integrations"] == catalog_counts["integrations"]
    assert reverted["scenarios"] == catalog_counts["scenarios"]
    assert reverted["systems"] == catalog_counts["systems"]
    assert _state_json(sessions, current["id"]) == current_before
