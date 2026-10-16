"""Slice 2 deterministic domain proposal helpers (Enterprise/Information/Solution)."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.helper_actions import service
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
        tenant = Tenant(name=f"domain-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="domain@example.test",
                password_hash=hash_password("domain-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "domain@example.test", "password": "domain-test-password"},
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
        json={"name": f"Domain {uuid4().hex[:8]}", "disciplines": disciplines or FULL},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _system(test_client, headers, name="CRM"):
    response = test_client.post(
        "/api/catalog/systems", json={"name": name, "kind": "application"}, headers=headers
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


def _catalog_field(test_client, headers, object_id, name, data_type="string"):
    response = test_client.post(
        f"/api/catalog/objects/{object_id}/fields",
        json={"name": name, "label": name, "data_type": data_type},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


_ENTERPRISE_GROUP = {
    "goal": "goals",
    "requirement": "requirements",
    "capability": "capabilities",
    "process": "processes",
    "principle": "principles",
    "role": "roles",
}


def _enterprise_object(test_client, headers, workspace_id, state_id, kind, name):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/enterprise/objects",
        json={"state_id": state_id, "kind": kind, "name": name, "position": {"x": 0.0, "y": 0.0}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    for item in response.json()[_ENTERPRISE_GROUP[kind]]:
        if item["name"] == name:
            return item["object_id"]
    raise AssertionError(f"{kind} {name!r} not found in enterprise model")


def _information_entity(test_client, headers, workspace_id, state_id, name):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities",
        json={"state_id": state_id, "name": name, "position": {"x": 0.0, "y": 0.0}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["entity"]["object_id"]


def _solution(test_client, headers, workspace_id, state_id, name):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions",
        json={"state_id": state_id, "name": name, "position": {"x": 0.0, "y": 0.0}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["solution"]["solution_object_id"]


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
        }


def _ops_by_id(body):
    return {op["operation_id"]: op for op in body["operations"]}


def _ops_by_temp(body):
    return {op["temporary_id"]: op for op in body["operations"] if op["temporary_id"]}


# --- Enterprise --------------------------------------------------------------


def test_strategy_chain_reuses_existing_and_creates_missing(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    goal_id = _enterprise_object(
        test_client, headers, workspace["id"], candidate["id"], "goal", "Reduce Churn"
    )
    capability_id = _enterprise_object(
        test_client, headers, workspace["id"], candidate["id"], "capability", "Billing"
    )

    before = _counts(sessions)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_strategy_chain",
        {
            "state_id": candidate["id"],
            "summary": "Customer onboarding strategy",
            "nodes": [
                {"key": "goal", "kind": "business_goal", "name": "Reduce Churn"},
                {"key": "req", "kind": "business_requirement", "name": "Faster Onboarding"},
                {"key": "cap", "kind": "business_capability", "name": "Billing"},
                {"key": "proc", "kind": "business_process", "name": "Invoice Run"},
            ],
            "links": [
                {"relationship_type": "drives", "source_key": "goal", "target_key": "req"},
                {"relationship_type": "needs", "source_key": "req", "target_key": "cap"},
                {"relationship_type": "has_process", "source_key": "cap", "target_key": "proc"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"

    reused_ids = {item["target_id"] for item in body["reused_objects"]}
    assert reused_ids == {goal_id, capability_id}
    proposed_ids = {item["temporary_id"] for item in body["proposed_objects"]}
    assert proposed_ids == {
        "tmp:business_requirement:faster-onboarding",
        "tmp:business_process:invoice-run",
    }

    ops = _ops_by_id(body)
    created = [op for op in ops.values() if op["domain_action"] == "create_object"]
    assert {op["proposed_value"]["kind"] for op in created} == {
        "business_requirement",
        "business_process",
    }
    link_types = [
        op["proposed_value"]["relationship_type"]
        for op in ops.values()
        if op["domain_action"] == "create_link"
    ]
    assert link_types == ["drives", "needs", "has_process"]

    # Proposal creation writes no architecture-domain data.
    assert _counts(sessions) == before

    validated = _validate(test_client, headers, workspace["id"], body["id"]).json()
    assert validated["status"] == "validated"
    assert validated["validation_summary"]["ready_for_approval"] is True
    assert _counts(sessions) == before

    approved = _approve(test_client, headers, workspace["id"], body["id"]).json()
    assert approved["status"] == "approved"
    assert _counts(sessions) == before


def test_strategy_chain_relationship_direction_follows_link_rules(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_strategy_chain",
        {
            "state_id": candidate["id"],
            "summary": "Wrong direction",
            "nodes": [
                {"key": "goal", "kind": "business_goal", "name": "G"},
                {"key": "req", "kind": "business_requirement", "name": "R"},
                {"key": "cap", "kind": "business_capability", "name": "C"},
                {"key": "proc", "kind": "business_process", "name": "P"},
            ],
            "links": [
                {"relationship_type": "drives", "source_key": "cap", "target_key": "goal"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    validated = _validate(test_client, headers, workspace["id"], response.json()["id"]).json()
    assert validated["status"] == "validation_failed"
    codes = {issue["code"] for issue in validated["validation_summary"]["issues"]}
    assert "relationship_direction" in codes


# --- Information -------------------------------------------------------------


def test_information_attributes_are_children_and_realizations_unresolved(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    system = _system(test_client, headers, "Customer Master")
    catalog_object = _catalog_object(test_client, headers, system["id"], "Customer")
    customer_id_field = _catalog_field(test_client, headers, catalog_object, "customer_id")
    _catalog_field(test_client, headers, catalog_object, "email")

    before = _counts(sessions)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_information_entity",
        {
            "state_id": candidate["id"],
            "summary": "Customer entity",
            "nodes": [
                {"key": "e", "kind": "information_object", "name": "Customer Account"},
                {
                    "key": "custid",
                    "kind": "information_attribute",
                    "name": "customer_id",
                    "parent_key": "e",
                    "data_type": "string",
                    "is_key": True,
                },
                {
                    "key": "email",
                    "kind": "information_attribute",
                    "name": "email",
                    "parent_key": "e",
                },
                {
                    "key": "tier",
                    "kind": "information_attribute",
                    "name": "loyalty_tier",
                    "parent_key": "e",
                },
            ],
            "realizations": [
                {"key": "custid", "catalog_field_id": customer_id_field},
                {"key": "email", "catalog_object_name": "Customer", "field_name": "email"},
                {
                    "key": "tier",
                    "catalog_object_name": "Customer",
                    "field_name": "nonexistent",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    ops = _ops_by_id(body)

    entity_temp = "tmp:information_object:customer-account"
    attr_op = ops["op-2"]
    assert attr_op["domain_action"] == "create_object"
    assert attr_op["target_type"] == "information_attribute"
    assert attr_op["target_id"] is None
    assert attr_op["proposed_value"]["parent_ref"] == entity_temp
    assert attr_op["depends_on"] == ["op-1"]
    # Attributes are canonical child operations, never generic state nodes.
    assert all(
        op["proposed_value"].get("kind") != "architecture_object"
        for op in ops.values()
        if op["domain_action"] == "create_object"
    )

    realized = {
        op["proposed_value"]["attribute_ref"]: op
        for op in ops.values()
        if op["domain_action"] == "set_realization"
    }
    custid = realized["tmp:information_attribute:customer-id"]
    assert custid["proposed_value"]["catalog_field_id"] == customer_id_field
    assert custid["proposed_value"].get("resolved") is True
    email = realized["tmp:information_attribute:email"]
    assert email["proposed_value"].get("resolved") is True
    tier = realized["tmp:information_attribute:loyalty-tier"]
    assert tier["proposed_value"]["unresolved"] is True
    assert "nonexistent" in tier["proposed_value"]["reason"]

    # No Catalog records created.
    assert _counts(sessions) == before

    validated = _validate(test_client, headers, workspace["id"], body["id"]).json()
    assert validated["status"] == "validated"
    assert validated["validation_summary"]["ready_for_approval"] is False
    assert validated["validation_summary"]["unresolved"] == 1

    blocked = _approve(test_client, headers, workspace["id"], body["id"])
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "unresolved_decisions"
    assert _counts(sessions) == before


def test_information_proposal_approves_when_realizations_resolve(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    system = _system(test_client, headers, "Orders")
    catalog_object = _catalog_object(test_client, headers, system["id"], "Order")
    field_id = _catalog_field(test_client, headers, catalog_object, "order_id")

    before = _counts(sessions)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_information_entity",
        {
            "state_id": candidate["id"],
            "summary": "Order entity",
            "nodes": [
                {"key": "e", "kind": "information_object", "name": "Order"},
                {
                    "key": "id",
                    "kind": "information_attribute",
                    "name": "order_id",
                    "parent_key": "e",
                },
            ],
            "realizations": [{"key": "id", "catalog_field_id": field_id}],
        },
    )
    assert response.status_code == 201, response.text
    change_set_id = response.json()["id"]
    validated = _validate(test_client, headers, workspace["id"], change_set_id).json()
    assert validated["validation_summary"]["ready_for_approval"] is True
    approved = _approve(test_client, headers, workspace["id"], change_set_id).json()
    assert approved["status"] == "approved"
    assert approved["approved_hash"] == approved["proposal_hash"]
    assert _counts(sessions) == before


# --- Solution ----------------------------------------------------------------


def _solution_structure_body(candidate_id, system_id):
    return {
        "state_id": candidate_id,
        "summary": "Customer onboarding solution",
        "nodes": [
            {"key": "sol", "kind": "solution_boundary", "name": "Customer Onboarding"},
            {"key": "crm", "kind": "catalog_system", "name": "CRM"},
            {
                "key": "portal",
                "kind": "component",
                "name": "Portal",
                "parent_key": "sol",
                "component_type": "ui",
            },
            {"key": "svc", "kind": "component", "name": "Onboarding Service", "parent_key": "sol"},
            {
                "key": "conn",
                "kind": "component",
                "name": "Integration Connector",
                "parent_key": "sol",
                "component_type": "integration",
            },
            {
                "key": "repo",
                "kind": "data_repository",
                "name": "Onboarding Store",
                "parent_key": "sol",
            },
            {"key": "deploy", "kind": "deployment_node", "name": "Cloud", "parent_key": "sol"},
            {"key": "trust", "kind": "trust_boundary", "name": "Internal", "parent_key": "sol"},
            {
                "key": "svc_prov",
                "kind": "interface",
                "name": "Signup API",
                "parent_key": "svc",
                "direction": "provided",
                "interface_kind": "sync",
            },
            {
                "key": "conn_req",
                "kind": "interface",
                "name": "Signup Client",
                "parent_key": "conn",
                "direction": "required",
                "interface_kind": "sync",
            },
            {
                "key": "op1",
                "kind": "interface_operation",
                "name": "CreateCustomer",
                "parent_key": "svc_prov",
                "operation_kind": "operation",
            },
            {
                "key": "ev1",
                "kind": "interface_operation",
                "name": "CustomerCreated",
                "parent_key": "svc_prov",
                "operation_kind": "event",
            },
        ],
        "links": [
            {
                "relationship_type": "connects_to",
                "source_key": "conn_req",
                "target_key": "svc_prov",
            },
            {"relationship_type": "uses_repository", "source_key": "svc", "target_key": "repo"},
            {"relationship_type": "deployed_on", "source_key": "svc", "target_key": "deploy"},
            {"relationship_type": "contained_in", "source_key": "svc", "target_key": "trust"},
            {"relationship_type": "crosses", "source_key": "svc_prov", "target_key": "trust"},
        ],
    }


def test_solution_structure_reuses_systems_and_resolves_temp_ids(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    system = _system(test_client, headers, "CRM")

    before = _counts(sessions)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_structure",
        _solution_structure_body(candidate["id"], system["id"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    ops = _ops_by_id(body)

    assert system["id"] in {item["target_id"] for item in body["reused_objects"]}
    temps = {item["temporary_id"] for item in body["proposed_objects"]}
    assert "tmp:component:portal" in temps
    assert "tmp:interface:signup-api" in temps

    # Dependent operations resolve temporary IDs and declare their dependency.
    portal_op = next(
        op
        for op in ops.values()
        if op["domain_action"] == "create_object"
        and op["proposed_value"].get("name") == "Portal"
    )
    assert portal_op["proposed_value"]["parent_ref"] == "tmp:solution_boundary:customer-onboarding"
    assert portal_op["depends_on"] == ["op-1"]
    assert portal_op["temporary_id"] == "tmp:component:portal"

    validated = _validate(test_client, headers, workspace["id"], body["id"]).json()
    assert validated["status"] == "validated", validated["validation_summary"]
    assert validated["validation_summary"]["ready_for_approval"] is True

    approved = _approve(test_client, headers, workspace["id"], body["id"]).json()
    assert approved["status"] == "approved"

    # No architecture-domain data created by proposal + validation + approval.
    assert _counts(sessions) == before


def test_interface_connection_direction_is_validated(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_structure",
        {
            "state_id": candidate["id"],
            "summary": "Bad connection",
            "nodes": [
                {"key": "sol", "kind": "solution_boundary", "name": "S"},
                {"key": "svc", "kind": "component", "name": "Svc", "parent_key": "sol"},
                {
                    "key": "p1",
                    "kind": "interface",
                    "name": "P1",
                    "parent_key": "svc",
                    "direction": "provided",
                },
                {
                    "key": "p2",
                    "kind": "interface",
                    "name": "P2",
                    "parent_key": "svc",
                    "direction": "provided",
                },
            ],
            "links": [
                {"relationship_type": "connects_to", "source_key": "p1", "target_key": "p2"}
            ],
        },
    )
    assert response.status_code == 201, response.text
    validated = _validate(test_client, headers, workspace["id"], response.json()["id"]).json()
    assert validated["status"] == "validation_failed"
    codes = {issue["code"] for issue in validated["validation_summary"]["issues"]}
    assert "relationship_direction" in codes


def test_interaction_requires_evidence(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_interaction",
        {
            "state_id": candidate["id"],
            "summary": "Interactions",
            "nodes": [
                {"key": "sol", "kind": "solution_boundary", "name": "S"},
                {"key": "svc", "kind": "component", "name": "Svc", "parent_key": "sol"},
                {
                    "key": "iface",
                    "kind": "interface",
                    "name": "Iface",
                    "parent_key": "svc",
                    "direction": "provided",
                },
            ],
            "interactions": [
                {
                    "key": "supported",
                    "source_key": "svc",
                    "target_key": "svc",
                    "interface_key": "iface",
                },
                {"key": "unsupported", "source_key": "svc", "target_key": "svc"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    ops = [op for op in body["operations"] if op["domain_action"] == "record_interaction"]
    supported = next(op for op in ops if op["proposed_value"]["evidence_refs"])
    assert supported["proposed_value"]["evidence_refs"] == ["tmp:interface:iface"]
    unsupported = next(op for op in ops if not op["proposed_value"]["evidence_refs"])
    assert unsupported["proposed_value"]["unresolved"] is True

    validated = _validate(test_client, headers, workspace["id"], body["id"]).json()
    assert validated["status"] == "validated"
    assert validated["validation_summary"]["ready_for_approval"] is False
    assert any(
        "no modeled or proposed" in decision
        for decision in validated["validation_summary"]["unresolved_decisions"]
    )


def test_operation_graph_cycles_are_rejected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_component",
        {
            "state_id": candidate["id"],
            "summary": "Cycle",
            "nodes": [
                {"key": "a", "kind": "component", "name": "A", "parent_key": "b"},
                {"key": "b", "kind": "component", "name": "B", "parent_key": "a"},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "node_reference_cycle"


def test_missing_dependency_is_detected(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_structure",
        _solution_structure_body(candidate["id"], _system(test_client, headers, "CRM")["id"]),
    ).json()

    with sessions() as db:
        link = db.scalar(
            select(HelperChangeOperation).where(
                HelperChangeOperation.change_set_id == UUID(body["id"]),
                HelperChangeOperation.domain_action == "create_link",
            )
        )
        link.depends_on = []
        change_set = db.get(HelperChangeSet, UUID(body["id"]))
        operations = list(
            db.scalars(
                select(HelperChangeOperation).where(
                    HelperChangeOperation.change_set_id == UUID(body["id"])
                )
            )
        )
        change_set.proposal_hash = service.compute_proposal_hash(change_set, operations)
        db.commit()

    validated = _validate(test_client, headers, workspace["id"], body["id"]).json()
    assert validated["status"] == "validation_failed"
    codes = {issue["code"] for issue in validated["validation_summary"]["issues"]}
    assert "missing_dependency" in codes


# --- Cross-cutting rules -----------------------------------------------------


def test_disabled_discipline_rejects_domain_helper(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers, disciplines=["information"])
    enterprise = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_strategy_chain",
        {"state_id": candidate["id"], "summary": "nope", "nodes": []},
    )
    assert enterprise.status_code == 404
    solution = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_structure",
        {"state_id": candidate["id"], "summary": "nope", "nodes": []},
    )
    assert solution.status_code == 404


def test_current_target_is_rejected_for_domain_helper(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_strategy_chain",
        {"state_id": current["id"], "summary": "current", "nodes": []},
    )
    assert response.status_code == 409


def test_cross_tenant_and_invalid_references_are_rejected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace_a, _ca, candidate_a = _workspace(test_client, headers)
    capability_a = _enterprise_object(
        test_client, headers, workspace_a["id"], candidate_a["id"], "capability", "Cap A"
    )
    workspace_b, _cb, candidate_b = _workspace(test_client, headers)

    cross = _propose(
        test_client,
        headers,
        workspace_b["id"],
        "propose_strategy_chain",
        {
            "state_id": candidate_b["id"],
            "summary": "cross tenant",
            "nodes": [
                {
                    "key": "cap",
                    "kind": "business_capability",
                    "name": "Cap A",
                    "existing_object_id": capability_a,
                }
            ],
        },
    )
    assert cross.status_code == 422
    assert cross.json()["detail"]["code"] == "unknown_reference"

    missing = _propose(
        test_client,
        headers,
        workspace_b["id"],
        "propose_strategy_chain",
        {
            "state_id": candidate_b["id"],
            "summary": "missing",
            "nodes": [
                {
                    "key": "cap",
                    "kind": "business_capability",
                    "name": "Ghost",
                    "existing_object_id": str(uuid4()),
                }
            ],
        },
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "unknown_reference"


def test_domain_proposal_audit_and_hash_binding(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    system = _system(test_client, headers, "CRM")
    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_structure",
        _solution_structure_body(candidate["id"], system["id"]),
    ).json()

    with sessions() as db:
        events = set(
            db.scalars(
                select(HelperAuditEvent.event_type).where(
                    HelperAuditEvent.change_set_id == UUID(body["id"])
                )
            )
        )
    assert {"proposal_invoked", "objects_reused", "objects_proposed"} <= events

    validated = _validate(test_client, headers, workspace["id"], body["id"]).json()
    assert validated["status"] == "validated"
    approved = _approve(test_client, headers, workspace["id"], body["id"]).json()
    assert approved["status"] == "approved"
    assert approved["approved_hash"] == approved["proposal_hash"]

    # Out-of-band mutation invalidates validation + approval (hash-bound).
    with sessions() as db:
        op = db.scalar(
            select(HelperChangeOperation).where(
                HelperChangeOperation.change_set_id == UUID(body["id"])
            )
        )
        op.proposed_value = {"changed": True}
        db.commit()
    status_body = test_client.get(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{body['id']}/status",
        headers=headers,
    ).json()
    assert status_body["status"] == "stale"
    assert status_body["approved_by"] is None


def test_proposal_and_validation_create_no_domain_records(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace(test_client, headers)
    _system(test_client, headers, "CRM")
    system = _system(test_client, headers, "CRM2")

    with sessions() as db:
        current_nodes_before = db.get(ArchitectureState, UUID(current["id"])).nodes
    before = _counts(sessions)

    body = _propose(
        test_client,
        headers,
        workspace["id"],
        "propose_solution_structure",
        _solution_structure_body(candidate["id"], system["id"]),
    ).json()
    _validate(test_client, headers, workspace["id"], body["id"])

    assert _counts(sessions) == before
    with sessions() as db:
        current_nodes_after = db.get(ArchitectureState, UUID(current["id"])).nodes
        assert db.scalar(select(func.count(HelperChangeSet.id))) == 1
    assert current_nodes_after == current_nodes_before
