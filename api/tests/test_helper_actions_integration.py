"""Slice 3 deterministic integration/contract/mapping/scenario proposal helpers."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureStateMember,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    HelperAuditEvent,
    Integration,
    IntegrationFieldRef,
    Scenario,
    Tenant,
    User,
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
        tenant = Tenant(name=f"integration-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="integration@example.test",
                password_hash=hash_password("integration-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "integration@example.test", "password": "integration-test-password"},
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
        json={"name": f"Integration {uuid4().hex[:8]}", "disciplines": disciplines or FULL},
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


def _interface(test_client, headers, workspace_id, state_id, name, direction, component_name):
    solution_id = _solution(test_client, headers, workspace_id, state_id, f"Solve {name}")
    component = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions/{solution_id}/components",
        json={"state_id": state_id, "name": component_name, "position": {"x": 0.0, "y": 0.0}},
        headers=headers,
    )
    assert component.status_code == 201, component.text
    component_id = next(
        item["object_id"]
        for item in component.json()["components"]
        if item["name"] == component_name
    )
    interface = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/components/{component_id}/interfaces",
        json={"state_id": state_id, "name": name, "direction": direction},
        headers=headers,
    )
    assert interface.status_code == 201, interface.text
    for item in interface.json()["components"]:
        if item["object_id"] != component_id:
            continue
        for iface in item["interfaces"]:
            if iface["name"] == name:
                return iface["object_id"]
    raise AssertionError(f"interface {name!r} not found in solution response")


def _operation(test_client, headers, workspace_id, state_id, interface_id, name, kind="command"):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/interfaces/{interface_id}/operations",
        json={"state_id": state_id, "name": name, "operation_kind": kind},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    for component in response.json()["components"]:
        for iface in component["interfaces"]:
            if iface["object_id"] != interface_id:
                continue
            for operation in iface["operations"]:
                if operation["name"] == name:
                    return operation["object_id"]
    raise AssertionError(f"operation {name!r} not found in solution response")


def _field_graph(pairs):
    source_node = uuid4()
    target_node = uuid4()
    nodes = [
        {"id": str(source_node), "type": "source", "position": {"x": 0.0, "y": 0.0}},
        {"id": str(target_node), "type": "target", "position": {"x": 200.0, "y": 0.0}},
    ]
    edges = [
        {
            "id": str(uuid4()),
            "sourceNodeId": str(source_node),
            "sourcePortId": f"field:{source_field}",
            "targetNodeId": str(target_node),
            "targetPortId": f"field:{target_field}",
        }
        for source_field, target_field in pairs
    ]
    return {"version": 1, "nodes": nodes, "edges": edges}


def _seed_contract(
    test_client,
    headers,
    *,
    source_system_id,
    source_object_id,
    target_system_id,
    target_object_id,
    name,
    interaction_type="REQUEST_RESPONSE",
    pattern="request_reply",
    producer_interface_id=None,
    consumer_interface_id=None,
    error_response_object_id=None,
    specification=None,
    field_refs=(),
):
    payload = {
        "source_system_id": source_system_id,
        "source_object_id": source_object_id,
        "target_system_id": target_system_id,
        "target_object_id": target_object_id,
        "name": name,
        "interaction_type": interaction_type,
        "pattern": pattern,
        "producer_interface_id": producer_interface_id,
        "consumer_interface_id": consumer_interface_id,
        "error_response_object_id": error_response_object_id,
        "specification": specification or {},
        "graph": (
            _field_graph(field_refs)
            if field_refs
            else {"version": 1, "nodes": [], "edges": []}
        ),
    }
    response = test_client.post("/api/integrations", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _contract_snapshot(sessions, contract_id):
    with sessions() as db:
        row = db.get(Integration, UUID(str(contract_id)))
        return {
            "name": row.name,
            "interaction_type": row.interaction_type,
            "pattern": row.pattern,
            "specification": dict(row.specification or {}),
            "producer_interface_id": row.producer_interface_id,
            "consumer_interface_id": row.consumer_interface_id,
            "error_response_object_id": row.error_response_object_id,
            "revision": row.revision,
        }


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


def _ops(body):
    return {op["operation_id"]: op for op in body["operations"]}


def _ops_by_temp(body):
    return {op["temporary_id"]: op for op in body["operations"] if op["temporary_id"]}


def _contract_op(body):
    for op in body["operations"]:
        if op["domain_action"] in {"reuse_contract", "create_contract"}:
            return op
    raise AssertionError("no contract operation present")


def _events(sessions, change_set_id):
    with sessions() as db:
        rows = db.scalars(
            select(HelperAuditEvent.event_type)
            .where(HelperAuditEvent.change_set_id == UUID(str(change_set_id)))
            .order_by(HelperAuditEvent.created_at, HelperAuditEvent.id)
        ).all()
        return list(rows)


def _base(workspace, candidate, source, target, **overrides):
    payload = {
        "state_id": candidate["id"],
        "summary": "Integration proposal",
        "contract": {
            "name": "CRM Customer Onboarding",
            "source_system_id": source["system_id"],
            "source_object_id": source["object_id"],
            "target_system_id": target["system_id"],
            "target_object_id": target["object_id"],
            "interaction_type": "REQUEST_RESPONSE",
            "pattern": "request_reply",
        },
    }
    payload.update(overrides)
    return payload


def _nodes(test_client, headers):
    """Create two systems with one object each and return handy ids."""
    crm = _system(test_client, headers, name=f"CRM {uuid4().hex[:6]}")
    billing = _system(test_client, headers, name=f"Billing {uuid4().hex[:6]}")
    customer = _catalog_object(test_client, headers, crm["id"], "Customer")
    account = _catalog_object(test_client, headers, billing["id"], "Billing Account")
    return {
        "crm_system": crm["id"],
        "billing_system": billing["id"],
        "customer_object": customer,
        "account_object": account,
    }


# --- Contract proposal / reuse ----------------------------------------------


def test_direct_integration_proposes_draft_without_writes(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    email = _catalog_field(
        test_client, headers, nodes["customer_object"], "Email", external_id="crm.email"
    )
    account_id = _catalog_field(
        test_client, headers, nodes["account_object"], "Account Id"
    )
    display = _catalog_field(
        test_client, headers, nodes["account_object"], "Display Name"
    )

    before = _counts(sessions)
    body = _base(
        workspace,
        candidate,
        {
            "system_id": nodes["crm_system"],
            "object_id": nodes["customer_object"],
        },
        {
            "system_id": nodes["billing_system"],
            "object_id": nodes["account_object"],
        },
        mappings=[
            {
                "key": "email-to-account",
                "phase": "request",
                "source_field_id": email,
                "target_field_id": account_id,
                "required": True,
            }
        ],
        transformations=[
            {
                "key": "account-name",
                "node_type": "concat",
                "source_field_ids": [account_id],
                "target_field_id": display,
                "config": {"separator": " "},
                "reason": "Build a display name from the account id",
            }
        ],
        resilience={
            "retry": {"max_attempts": 3, "backoff": "exponential"},
            "timeout_ms": 5000,
            "idempotent": True,
            "idempotency_key_field_id": str(email),
            "routing": "direct",
            "error_handling": "dead letter",
        },
    )
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert proposal["status"] == "draft"

    created = _contract_op(proposal)
    assert created["domain_action"] == "create_contract"
    assert created["proposed_value"]["status"] == "draft"
    assert created["proposed_value"]["runtime_mediated"] is False
    assert created["proposed_value"]["runtime_system_id"] is None
    assert created["proposed_value"]["proposal_intent"] == "independent"

    actions = [op["domain_action"] for op in proposal["operations"]]
    assert "create_mapping" in actions
    assert "create_transformation" in actions
    assert "configure_resilience" in actions

    # Proposal creation writes no integration-domain data.
    assert _counts(sessions) == before

    validated = _validate(test_client, headers, workspace["id"], proposal["id"]).json()
    assert validated["status"] == "validated", validated.get("validation_summary")
    assert validated["validation_summary"]["ready_for_approval"] is True
    assert _counts(sessions) == before

    assert _approve(test_client, headers, workspace["id"], proposal["id"]).json()["status"] == (
        "approved"
    )
    assert _counts(sessions) == before


def test_exact_existing_contract_is_reused_unchanged(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    contract_id = _seed_contract(
        test_client,
        headers,
        source_system_id=nodes["crm_system"],
        source_object_id=nodes["customer_object"],
        target_system_id=nodes["billing_system"],
        target_object_id=nodes["account_object"],
        name="CRM Customer Onboarding",
    )
    snapshot = _contract_snapshot(sessions, contract_id)
    before = _counts(sessions)

    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
    )
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 201, response.text
    proposal = response.json()

    contract_op = _contract_op(proposal)
    assert contract_op["domain_action"] == "reuse_contract"
    assert contract_op["target_id"] == str(contract_id)
    assert proposal["proposed_objects"] == []
    assert {item["target_id"] for item in proposal["reused_objects"]} == {str(contract_id)}

    assert _counts(sessions) == before
    assert _contract_snapshot(sessions, contract_id) == snapshot

    validated = _validate(test_client, headers, workspace["id"], proposal["id"]).json()
    assert validated["status"] == "validated"
    assert validated["validation_summary"]["ready_for_approval"] is True
    assert _approve(test_client, headers, workspace["id"], proposal["id"]).json()["status"] == (
        "approved"
    )
    # The reused Contract stays untouched even after approval in this slice.
    assert _contract_snapshot(sessions, contract_id) == snapshot
    assert _counts(sessions) == before

    events = _events(sessions, proposal["id"])
    assert "contract_reused" in events


def test_similar_name_alone_does_not_reuse(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    other = _catalog_object(test_client, headers, nodes["billing_system"], "Invoice")
    # Same name, different target object -> must not auto-reuse.
    _seed_contract(
        test_client,
        headers,
        source_system_id=nodes["crm_system"],
        source_object_id=nodes["customer_object"],
        target_system_id=nodes["billing_system"],
        target_object_id=other,
        name="CRM Customer Onboarding",
    )

    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
    )
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 201, response.text
    proposal = response.json()
    contract_op = _contract_op(proposal)
    assert contract_op["domain_action"] == "create_contract"
    assert contract_op["proposed_value"]["based_on_contract_id"] is None


def test_changed_design_proposes_new_draft_with_lineage(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    contract_id = _seed_contract(
        test_client,
        headers,
        source_system_id=nodes["crm_system"],
        source_object_id=nodes["customer_object"],
        target_system_id=nodes["billing_system"],
        target_object_id=nodes["account_object"],
        name="CRM Customer Onboarding",
        interaction_type="REQUEST_RESPONSE",
    )
    snapshot = _contract_snapshot(sessions, contract_id)
    before = _counts(sessions)

    # Same endpoints but a changed interaction type -> new draft with lineage.
    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
        contract_id=str(contract_id),
        proposal_intent="alternative",
    )
    body["contract"]["interaction_type"] = "ONE_WAY"
    body["contract"]["pattern"] = "point_to_point"

    response = _propose(test_client, headers, workspace["id"], "propose_contract", body)
    assert response.status_code == 201, response.text
    proposal = response.json()
    contract_op = _contract_op(proposal)
    assert contract_op["domain_action"] == "create_contract"
    assert contract_op["proposed_value"]["based_on_contract_id"] == str(contract_id)
    assert contract_op["proposed_value"]["proposal_intent"] == "alternative"

    events = _events(sessions, proposal["id"])
    assert "contract_proposed" in events
    assert "contract_lineage" in events

    assert _contract_snapshot(sessions, contract_id) == snapshot
    assert _counts(sessions) == before

    # Changed design with an explicit contract must declare a lineage intent.
    body["proposal_intent"] = "independent"
    rejected = _propose(test_client, headers, workspace["id"], "propose_contract", body)
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "lineage_intent_required"


def test_missing_contract_is_rejected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    body = {"state_id": candidate["id"], "summary": "No contract"}
    response = _propose(test_client, headers, workspace["id"], "propose_contract", body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "missing_contract"


# --- Runtime discipline ------------------------------------------------------


def test_direct_integration_forbids_runtime(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
        runtime_mediated=True,
    )
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "runtime_not_allowed"


def test_runtime_mediated_requires_a_real_runtime(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    runtime = _system(test_client, headers, name=f"Runtime {uuid4().hex[:6]}", kind="runtime")
    app = _system(test_client, headers, name=f"App {uuid4().hex[:6]}", kind="application")
    base = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
    )

    missing = _propose(
        test_client, headers, workspace["id"], "propose_runtime_mediated_integration", base
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "runtime_required"

    no_runtime = dict(base, runtime_mediated=True)
    no_runtime = _propose(
        test_client, headers, workspace["id"], "propose_runtime_mediated_integration", no_runtime
    )
    assert no_runtime.status_code == 422
    assert no_runtime.json()["detail"]["code"] == "missing_runtime_system"

    not_runtime = dict(base, runtime_mediated=True, runtime_system_id=app["id"])
    not_runtime = _propose(
        test_client, headers, workspace["id"], "propose_runtime_mediated_integration", not_runtime
    )
    assert not_runtime.status_code == 422
    assert not_runtime.json()["detail"]["code"] == "not_a_runtime"

    good = dict(base, runtime_mediated=True, runtime_system_id=runtime["id"])
    response = _propose(
        test_client, headers, workspace["id"], "propose_runtime_mediated_integration", good
    )
    assert response.status_code == 201, response.text
    proposal = response.json()
    created = _contract_op(proposal)
    assert created["proposed_value"]["runtime_mediated"] is True
    assert created["proposed_value"]["runtime_system_id"] == runtime["id"]

    validated = _validate(test_client, headers, workspace["id"], proposal["id"]).json()
    assert validated["status"] == "validated"
    assert validated["validation_summary"]["ready_for_approval"] is True


def test_file_transfer_is_distinct_from_api_and_event(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    endpoints = {
        "source": {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        "target": {
            "system_id": nodes["billing_system"],
            "object_id": nodes["account_object"],
        },
    }

    api_body = _base(workspace, candidate, endpoints["source"], endpoints["target"])
    rejected = _propose(
        test_client, headers, workspace["id"], "propose_file_transfer_integration", api_body
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "pattern_not_allowed"

    file_body = _base(workspace, candidate, endpoints["source"], endpoints["target"])
    file_body["contract"]["pattern"] = "file_transfer"
    file_body["contract"]["interaction_type"] = "ONE_WAY"
    response = _propose(
        test_client, headers, workspace["id"], "propose_file_transfer_integration", file_body
    )
    assert response.status_code == 201, response.text
    created = _contract_op(response.json())
    assert created["proposed_value"]["pattern"] == "file_transfer"
    assert created["proposed_value"]["runtime_mediated"] is False


# --- Interface direction -----------------------------------------------------


def test_interface_direction_compatibility(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    provided = _interface(
        test_client, headers, workspace["id"], candidate["id"], "Onboarding API", "provided", "CRM"
    )
    required = _interface(
        test_client, headers, workspace["id"], candidate["id"], "Billing API", "required", "Billing"
    )

    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
    )
    body["contract"]["producer_interface_id"] = provided
    body["contract"]["consumer_interface_id"] = required
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 201, response.text
    validated = _validate(
        test_client, headers, workspace["id"], response.json()["id"]
    ).json()
    assert validated["status"] == "validated"

    # Swap directions -> validation flags the incompatibility.
    swapped = dict(body)
    swapped["contract"] = dict(body["contract"])
    swapped["contract"]["producer_interface_id"] = required
    swapped["contract"]["consumer_interface_id"] = provided
    swapped_response = _propose(
        test_client, headers, workspace["id"], "propose_direct_integration", swapped
    )
    assert swapped_response.status_code == 201, swapped_response.text
    swapped_validated = _validate(
        test_client, headers, workspace["id"], swapped_response.json()["id"]
    ).json()
    assert swapped_validated["status"] == "validation_failed"
    codes = {issue["code"] for issue in swapped_validated["validation_summary"]["issues"]}
    assert "interface_direction" in codes

    # Unknown interface id is rejected at build time.
    unknown = dict(body)
    unknown["contract"] = dict(body["contract"])
    unknown["contract"]["producer_interface_id"] = str(uuid4())
    rejected = _propose(
        test_client, headers, workspace["id"], "propose_direct_integration", unknown
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "unknown_reference"


# --- Field mappings ----------------------------------------------------------


def test_exact_field_matching_and_reuse_coverage(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    email = _catalog_field(test_client, headers, nodes["customer_object"], "Email")
    account_id = _catalog_field(test_client, headers, nodes["account_object"], "Account Id")
    _seed_contract(
        test_client,
        headers,
        source_system_id=nodes["crm_system"],
        source_object_id=nodes["customer_object"],
        target_system_id=nodes["billing_system"],
        target_object_id=nodes["account_object"],
        name="CRM Customer Onboarding",
        field_refs=((email, account_id),),
    )
    before = _counts(sessions)
    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
        mappings=[
            {
                "key": "email-account",
                "phase": "request",
                "source_field_id": email,
                "target_field_id": account_id,
            }
        ],
    )
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert _contract_op(proposal)["domain_action"] == "reuse_contract"
    # Repeat mappings are already covered by the reused Contract: no mapping ops.
    assert not [
        op for op in proposal["operations"] if op["domain_action"] == "create_mapping"
    ]
    report = proposal["input_summary"]["mapping_report"]
    assert report["exact"] and report["exact"][0]["target_field_id"] == str(account_id)
    assert _counts(sessions) == before


def test_required_ambiguous_mapping_blocks_approval_optional_does_not(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    account_id = _catalog_field(test_client, headers, nodes["account_object"], "Account Id")
    endpoints = {
        "source": {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        "target": {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
    }
    before = _counts(sessions)

    required_body = _base(
        workspace,
        candidate,
        endpoints["source"],
        endpoints["target"],
        mappings=[
            {
                "key": "unknown-target",
                "phase": "request",
                "source_field_name": "Missing Source",
                "target_field_id": account_id,
                "required": True,
            }
        ],
    )
    required = _propose(
        test_client, headers, workspace["id"], "propose_direct_integration", required_body
    )
    assert required.status_code == 201, required.text
    required_body_json = required.json()
    validated = _validate(
        test_client, headers, workspace["id"], required_body_json["id"]
    ).json()
    # Structurally valid but not ready: a required mapping is unresolved.
    assert validated["status"] == "validated"
    assert validated["validation_summary"]["ready_for_approval"] is False
    assert validated["validation_summary"]["blocking_unresolved"] == 1
    assert _approve(
        test_client, headers, workspace["id"], required_body_json["id"]
    ).status_code == 409

    optional_body = _base(
        workspace,
        candidate,
        endpoints["source"],
        endpoints["target"],
        mappings=[
            {
                "key": "optional-unknown",
                "phase": "request",
                "source_field_name": "Missing Source",
                "target_field_id": account_id,
                "required": False,
            }
        ],
    )
    optional = _propose(
        test_client, headers, workspace["id"], "propose_direct_integration", optional_body
    )
    assert optional.status_code == 201, optional.text
    optional_json = optional.json()
    optional_validated = _validate(
        test_client, headers, workspace["id"], optional_json["id"]
    ).json()
    assert optional_validated["status"] == "validated"
    assert optional_validated["validation_summary"]["unresolved"] == 1
    assert optional_validated["validation_summary"]["blocking_unresolved"] == 0
    assert optional_validated["validation_summary"]["ready_for_approval"] is True
    assert _approve(
        test_client, headers, workspace["id"], optional_json["id"]
    ).json()["status"] == "approved"

    assert _counts(sessions) == before


def test_field_mappings_helper_requires_mappings(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
    )
    response = _propose(test_client, headers, workspace["id"], "propose_field_mappings", body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "missing_section"


# --- Scenarios and conformance ----------------------------------------------


def test_event_driven_runtime_mediated_scenarios_and_conformance(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    runtime = _system(test_client, headers, name=f"Runtime {uuid4().hex[:6]}", kind="runtime")
    customer_id = _catalog_field(test_client, headers, nodes["customer_object"], "Customer Id")
    _catalog_field(test_client, headers, nodes["account_object"], "Account Id")
    before = _counts(sessions)

    body = {
        "state_id": candidate["id"],
        "summary": "Customer event integration",
        "runtime_mediated": True,
        "runtime_system_id": runtime["id"],
        "contract": {
            "name": "Customer Event Stream",
            "source_system_id": nodes["crm_system"],
            "source_object_id": nodes["customer_object"],
            "target_system_id": nodes["billing_system"],
            "target_object_id": nodes["account_object"],
            "interaction_type": "ONE_WAY",
            "pattern": "publish_subscribe",
        },
        "scenarios": [
            {
                "key": "happy",
                "name": "Customer event happy path",
                "scenario_type": "happy_path",
                "phase": "request",
                "synthetic_values": {str(customer_id): "cust-1"},
            },
            {
                "key": "failure",
                "name": "Customer event delivery failure",
                "scenario_type": "event_delivery_failure",
                "phase": "request",
                "synthetic_values": {str(customer_id): "cust-2"},
            },
        ],
        "conformance": [
            {
                "key": "coverage",
                "expectation_type": "mapping_coverage",
                "phase": "request",
                "coverage_min": 1.0,
            },
            {
                "key": "success",
                "expectation_type": "success_failure",
                "phase": "request",
                "expected_success": False,
                "scenario_key": "failure",
            },
        ],
    }
    response = _propose(
        test_client, headers, workspace["id"], "propose_event_driven_integration", body
    )
    assert response.status_code == 201, response.text
    proposal = response.json()
    actions = [op["domain_action"] for op in proposal["operations"]]
    assert actions.count("create_scenario") == 2
    assert actions.count("define_conformance_expectation") == 2

    scenarios = [op for op in proposal["operations"] if op["domain_action"] == "create_scenario"]
    assert all(op["proposed_value"]["synthetic"] is True for op in scenarios)
    # Scenario documents reference the proposed contract and validate against the model.
    contract_temp = _contract_op(proposal)["temporary_id"]
    for op in scenarios:
        document = op["proposed_value"]["document"]
        assert contract_temp  # temp id present
        assert document["contractIds"] == [op["proposed_value"]["contract_uuid"]]
    assert _counts(sessions) == before

    validated = _validate(test_client, headers, workspace["id"], proposal["id"]).json()
    assert validated["status"] == "validated", validated.get("validation_summary")
    assert validated["validation_summary"]["ready_for_approval"] is True

    events = _events(sessions, proposal["id"])
    assert "scenario_proposed" in events
    assert "conformance_expectation_proposed" in events
    # Nothing executes and nothing is persisted.
    assert _counts(sessions) == before


def test_scenario_references_must_resolve(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    body = {
        "state_id": candidate["id"],
        "summary": "Bad scenario",
        "contract": {
            "name": "CRM Customer Onboarding",
            "source_system_id": nodes["crm_system"],
            "source_object_id": nodes["customer_object"],
            "target_system_id": nodes["billing_system"],
            "target_object_id": nodes["account_object"],
            "interaction_type": "REQUEST_RESPONSE",
            "pattern": "request_reply",
        },
        "scenarios": [
            {
                "key": "happy",
                "name": "Happy",
                "scenario_type": "happy_path",
                "phase": "request",
                "synthetic_values": {str(uuid4()): "x"},
            }
        ],
    }
    response = _propose(test_client, headers, workspace["id"], "propose_scenarios", body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_reference"


def test_transformation_uses_existing_engine_constructs(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    account_id = _catalog_field(test_client, headers, nodes["account_object"], "Account Id")
    display = _catalog_field(test_client, headers, nodes["account_object"], "Display Name")

    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
        transformations=[
            {
                "key": "bad",
                "node_type": "concat",
                "source_field_ids": [account_id],
                "target_field_id": display,
                "config": {"separator": " ", "expression": "x + y"},
                "reason": "attempt arbitrary config",
            }
        ],
    )
    response = _propose(
        test_client, headers, workspace["id"], "propose_transformations", body
    )
    assert response.status_code == 201, response.text
    validated = _validate(
        test_client, headers, workspace["id"], response.json()["id"]
    ).json()
    assert validated["status"] == "validation_failed"
    codes = {issue["code"] for issue in validated["validation_summary"]["issues"]}
    assert "invalid_node_config" in codes


def test_unknown_transformation_node_is_rejected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    account_id = _catalog_field(test_client, headers, nodes["account_object"], "Account Id")
    body = _base(
        workspace,
        candidate,
        {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
        transformations=[
            {
                "key": "exec",
                "node_type": "python",
                "source_field_ids": [],
                "target_field_id": account_id,
                "config": {},
                "reason": "arbitrary code",
            }
        ],
    )
    response = _propose(test_client, headers, workspace["id"], "propose_transformations", body)
    assert response.status_code == 422


# --- Resilience helper and end-to-end acceptance -----------------------------

def test_resilience_reuses_when_identical_and_proposes_draft_when_changed(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    _catalog_field(test_client, headers, nodes["account_object"], "Account Id")
    spec = {"retry": {"max_attempts": 1, "backoff": "linear"}, "timeout_ms": 1000}
    contract_id = _seed_contract(
        test_client,
        headers,
        source_system_id=nodes["crm_system"],
        source_object_id=nodes["customer_object"],
        target_system_id=nodes["billing_system"],
        target_object_id=nodes["account_object"],
        name="CRM Customer Onboarding",
        specification=spec,
    )
    snapshot = _contract_snapshot(sessions, contract_id)
    before = _counts(sessions)

    # Identical resilience -> reuse unchanged, no resilience operation emitted.
    identical = {
        "state_id": candidate["id"],
        "summary": "Keep resilience",
        "contract_id": contract_id,
        "resilience": spec,
    }
    reused = _propose(
        test_client, headers, workspace["id"], "propose_resilience_configuration", identical
    )
    assert reused.status_code == 201, reused.text
    reused_body = reused.json()
    assert _contract_op(reused_body)["domain_action"] == "reuse_contract"
    assert not [
        op for op in reused_body["operations"] if op["domain_action"] == "configure_resilience"
    ]

    # Different resilience -> new draft with lineage plus a resilience operation.
    changed = {
        "state_id": candidate["id"],
        "summary": "Change resilience",
        "contract_id": contract_id,
        "proposal_intent": "proposed_replacement",
        "resilience": {"retry": {"max_attempts": 3, "backoff": "exponential"}, "timeout_ms": 5000},
    }
    proposal = _propose(
        test_client, headers, workspace["id"], "propose_resilience_configuration", changed
    )
    assert proposal.status_code == 201, proposal.text
    proposal_body = proposal.json()
    created = _contract_op(proposal_body)
    assert created["domain_action"] == "create_contract"
    assert created["proposed_value"]["based_on_contract_id"] == contract_id
    assert created["proposed_value"]["proposal_intent"] == "proposed_replacement"
    assert [
        op for op in proposal_body["operations"] if op["domain_action"] == "configure_resilience"
    ]
    # A reused Contract is never mutated.
    assert _contract_snapshot(sessions, contract_id) == snapshot
    assert _counts(sessions) == before

    validated = _validate(test_client, headers, workspace["id"], proposal_body["id"]).json()
    assert validated["status"] == "validated"
    assert validated["validation_summary"]["ready_for_approval"] is True


def test_customer_onboarding_acceptance_proposal(client):
    """Direct CRM/Customer -> Billing/Billing Account through Onboarding/Billing APIs."""
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    error_object = _catalog_object(test_client, headers, nodes["billing_system"], "Error Response")
    provided = _interface(
        test_client, headers, workspace["id"], candidate["id"], "Onboarding API", "provided", "CRM"
    )
    required = _interface(
        test_client, headers, workspace["id"], candidate["id"], "Billing API", "required", "Billing"
    )
    customer_id = _catalog_field(
        test_client, headers, nodes["customer_object"], "Customer Id", external_id="crm.customer_id"
    )
    account_id = _catalog_field(test_client, headers, nodes["account_object"], "Account Id")
    display = _catalog_field(test_client, headers, nodes["account_object"], "Display Name")
    error_field = _catalog_field(test_client, headers, error_object, "Error Code")
    before = _counts(sessions)

    body = {
        "state_id": candidate["id"],
        "summary": "Customer onboarding direct integration",
        "contract": {
            "name": "Customer Onboarding",
            "source_system_id": nodes["crm_system"],
            "source_object_id": nodes["customer_object"],
            "target_system_id": nodes["billing_system"],
            "target_object_id": nodes["account_object"],
            "error_response_object_id": error_object,
            "interaction_type": "REQUEST_RESPONSE",
            "pattern": "request_reply",
            "producer_interface_id": provided,
            "consumer_interface_id": required,
        },
        "mappings": [
            {
                "key": "customer-to-account",
                "phase": "request",
                "source_external_identifier": "crm.customer_id",
                "target_field_id": account_id,
            }
        ],
        "transformations": [
            {
                "key": "display-name",
                "node_type": "concat",
                "source_field_ids": [account_id],
                "target_field_id": display,
                "config": {"separator": " "},
                "reason": "Compose a display name",
                "evidence": "Existing onboarding contract needs a display name",
            }
        ],
        "resilience": {
            "retry": {"max_attempts": 3, "backoff": "exponential"},
            "timeout_ms": 5000,
            "idempotent": True,
            "idempotency_key_field_id": str(customer_id),
            "security": {"auth_type": "oauth2", "notes": "Service account"},
            "routing": "api_gateway",
            "orchestration_role": "orchestration",
            "error_handling": "modelled error response",
        },
        "scenarios": [
            {
                "key": "happy",
                "name": "Customer onboarding happy path",
                "scenario_type": "happy_path",
                "phase": "request",
                "synthetic_values": {str(customer_id): "cust-1"},
                "expected_values": {str(account_id): "acct-1"},
                "assertion_text": "An account is created.",
            },
            {
                "key": "error",
                "name": "Customer onboarding error response",
                "scenario_type": "error_response",
                "phase": "error-response",
                "synthetic_values": {str(error_field): "E123"},
            },
        ],
        "conformance": [
            {
                "key": "coverage",
                "expectation_type": "mapping_coverage",
                "phase": "request",
                "coverage_min": 0.8,
                "field_ids": [customer_id, account_id],
            },
            {
                "key": "phase",
                "expectation_type": "response_phase",
                "phase": "request",
                "expected_phase": "success-response",
                "scenario_key": "happy",
            },
        ],
    }
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 201, response.text
    proposal = response.json()
    created = _contract_op(proposal)
    assert created["domain_action"] == "create_contract"
    assert created["proposed_value"]["error_response_object_id"] == error_object
    actions = [op["domain_action"] for op in proposal["operations"]]
    assert actions.count("create_mapping") == 1
    assert actions.count("create_transformation") == 1
    assert actions.count("configure_resilience") == 1
    assert actions.count("create_scenario") == 2
    assert actions.count("define_conformance_expectation") == 2

    # No architecture, contract, mapping, scenario, or test record is written.
    assert _counts(sessions) == before

    validated = _validate(test_client, headers, workspace["id"], proposal["id"]).json()
    assert validated["status"] == "validated", validated.get("validation_summary")
    assert validated["validation_summary"]["ready_for_approval"] is True
    assert _counts(sessions) == before

    assert _approve(
        test_client, headers, workspace["id"], proposal["id"]
    ).json()["status"] == "approved"
    assert _counts(sessions) == before

    events = _events(sessions, proposal["id"])
    for expected in (
        "proposal_invoked",
        "contract_proposed",
        "mapping_proposed",
        "transformation_proposed",
        "scenario_proposed",
        "conformance_expectation_proposed",
        "validation_passed",
        "approved",
    ):
        assert expected in events


# --- Phase operation intents -------------------------------------------------


def test_contract_phase_operation_intents(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    nodes = _nodes(test_client, headers)
    provided = _interface(
        test_client, headers, workspace["id"], candidate["id"], "Onboarding API", "provided", "CRM"
    )
    command_id = _operation(
        test_client, headers, workspace["id"], candidate["id"], provided, "CreateAccount", "command"
    )
    endpoints = {
        "source": {"system_id": nodes["crm_system"], "object_id": nodes["customer_object"]},
        "target": {"system_id": nodes["billing_system"], "object_id": nodes["account_object"]},
    }

    body = _base(workspace, candidate, endpoints["source"], endpoints["target"])
    body["contract"]["producer_interface_id"] = provided
    body["contract"]["request_phase"] = {
        "operation_refs": [{"operation_id": command_id, "kind": "command"}],
        "routing": "direct",
    }
    response = _propose(test_client, headers, workspace["id"], "propose_direct_integration", body)
    assert response.status_code == 201, response.text
    created = _contract_op(response.json())
    ref = created["proposed_value"]["request_phase"]["operation_refs"][0]
    assert ref["operation_id"] == command_id
    assert ref["resolved"] is True
    validated = _validate(test_client, headers, workspace["id"], response.json()["id"]).json()
    assert validated["status"] == "validated", validated.get("validation_summary")

    # A declared kind that disagrees with the operation is flagged in validation.
    mismatched = _base(workspace, candidate, endpoints["source"], endpoints["target"])
    mismatched["contract"]["producer_interface_id"] = provided
    mismatched["contract"]["request_phase"] = {
        "operation_refs": [{"operation_id": command_id, "kind": "event"}],
    }
    mismatched_response = _propose(
        test_client, headers, workspace["id"], "propose_direct_integration", mismatched
    )
    assert mismatched_response.status_code == 201, mismatched_response.text
    mismatched_validated = _validate(
        test_client, headers, workspace["id"], mismatched_response.json()["id"]
    ).json()
    assert mismatched_validated["status"] == "validation_failed"
    codes = {
        issue["code"] for issue in mismatched_validated["validation_summary"]["issues"]
    }
    assert "operation_kind_mismatch" in codes

    # An unknown operation id is rejected at build time.
    unknown = _base(workspace, candidate, endpoints["source"], endpoints["target"])
    unknown["contract"]["producer_interface_id"] = provided
    unknown["contract"]["request_phase"] = {
        "operation_refs": [{"operation_id": str(uuid4())}],
    }
    rejected = _propose(
        test_client, headers, workspace["id"], "propose_direct_integration", unknown
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "unknown_reference"
