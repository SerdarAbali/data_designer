import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import ArchitectureState, Tenant, User

DEMO_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "solution-designer" / "demo.json"


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
        tenant = Tenant(name=f"ws-solution-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="solution@example.test",
                password_hash=hash_password("solution-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "solution@example.test", "password": "solution-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _workspace_with_candidate(test_client: TestClient, headers: dict[str, str]):
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": "Solution Workspace", "disciplines": ["solution"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _discipline(workspace_id) -> str:
    return f"/api/workspaces/{workspace_id}/solution"


def _solution(workspace_id, solution_id) -> str:
    return f"{_discipline(workspace_id)}/solutions/{solution_id}"


def _create_solution(test_client, headers, workspace_id, state_id, payload):
    response = test_client.post(
        f"{_discipline(workspace_id)}/solutions",
        json={"state_id": state_id, **payload},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_component(test_client, headers, workspace_id, solution_id, state_id, name, **kw):
    response = test_client.post(
        f"{_solution(workspace_id, solution_id)}/components",
        json={"state_id": state_id, "name": name, "position": {"x": 100, "y": 100}, **kw},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _component_by_name(design, name):
    return next(component for component in design["components"] if component["name"] == name)


def _interface_by_name(component, name):
    return next(interface for interface in component["interfaces"] if interface["name"] == name)


def test_solution_designer_hierarchy_flow(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    design = _create_solution(
        test_client,
        headers,
        workspace_id,
        state_id,
        {"name": "Payments Platform", "owner": "Payments Team"},
    )
    solution_id = design["solution"]["solution_object_id"]
    assert design["solution"]["name"] == "Payments Platform"
    assert design["solution"]["owner"] == "Payments Team"

    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "Core Banking", "kind": "service"},
        headers=headers,
    ).json()
    member = test_client.post(
        f"{_solution(workspace_id, solution_id)}/members",
        json={"state_id": state_id, "system_id": system["id"]},
        headers=headers,
    )
    assert member.status_code in (200, 201), member.text
    assert [m["name"] for m in member.json()["solution"]["members"]] == ["Core Banking"]

    created = _create_component(
        test_client,
        headers,
        workspace_id,
        solution_id,
        state_id,
        "Payment API",
        responsibility="Expose payment endpoints.",
        component_type="service",
        technology="FastAPI",
    )
    component = _component_by_name(created, "Payment API")
    component_id = component["object_id"]
    assert component["responsibility"] == "Expose payment endpoints."
    assert component["component_type"] == "service"

    provided = test_client.post(
        f"{_discipline(workspace_id)}/components/{component_id}/interfaces",
        json={
            "state_id": state_id,
            "name": "Payments API",
            "direction": "provided",
            "interface_kind": "sync",
            "protocol": "HTTPS",
        },
        headers=headers,
    )
    assert provided.status_code == 201, provided.text
    required = test_client.post(
        f"{_discipline(workspace_id)}/components/{component_id}/interfaces",
        json={"state_id": state_id, "name": "Ledger Client", "direction": "required"},
        headers=headers,
    )
    assert required.status_code == 201, required.text

    component = _component_by_name(required.json(), "Payment API")
    assert {i["name"]: i["direction"] for i in component["interfaces"]} == {
        "Payments API": "provided",
        "Ledger Client": "required",
    }
    payments_api_id = _interface_by_name(component, "Payments API")["object_id"]

    for name, kind in (("CreatePayment", "operation"), ("PaymentCreated", "event")):
        response = test_client.post(
            f"{_discipline(workspace_id)}/interfaces/{payments_api_id}/operations",
            json={"state_id": state_id, "name": name, "operation_kind": kind},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    final = response.json()
    component = _component_by_name(final, "Payment API")
    payments_api = _interface_by_name(component, "Payments API")
    assert {o["name"]: o["operation_kind"] for o in payments_api["operations"]} == {
        "CreatePayment": "operation",
        "PaymentCreated": "event",
    }

    drill = test_client.get(
        f"{_solution(workspace_id, solution_id)}/components/{component_id}",
        params={"state_id": state_id},
    )
    assert drill.status_code == 200, drill.text
    assert drill.json()["object_id"] == component_id
    assert len(drill.json()["interfaces"]) == 2

    reload_a = test_client.get(
        f"{_solution(workspace_id, solution_id)}/design",
        params={"state_id": state_id},
    ).json()
    reload_b = test_client.get(
        f"{_solution(workspace_id, solution_id)}/design",
        params={"state_id": state_id},
    ).json()
    assert [c["object_id"] for c in reload_a["components"]] == [
        c["object_id"] for c in reload_b["components"]
    ]
    assert len(reload_a["components"]) == 1


def test_solution_candidate_isolation(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    design = _create_solution(
        test_client, headers, workspace_id, candidate["id"], {"name": "Draft Solution"}
    )
    solution_id = design["solution"]["solution_object_id"]
    _create_component(test_client, headers, workspace_id, solution_id, candidate["id"], "Worker")

    current_design = test_client.get(
        f"{_solution(workspace_id, solution_id)}/design",
        params={"state_id": current["id"]},
    ).json()
    assert current_design["editable"] is False
    assert current_design["components"] == []

    current_list = test_client.get(
        f"{_discipline(workspace_id)}/solutions",
        params={"state_id": current["id"]},
    ).json()
    assert current_list == []

    candidate_list = test_client.get(
        f"{_discipline(workspace_id)}/solutions",
        params={"state_id": candidate["id"]},
    ).json()
    assert [s["name"] for s in candidate_list] == ["Draft Solution"]
    assert candidate_list[0]["component_count"] == 1


def test_candidate_edits_of_current_solution_use_overrides(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    created = _create_solution(
        test_client, headers, workspace_id, candidate["id"], {"name": "Payments Platform"}
    )
    solution_id = created["solution"]["solution_object_id"]

    # Promote the solution boundary onto Current (simulating a committed baseline).
    with testing_sessions.begin() as db:
        current_row = db.get(ArchitectureState, UUID(current["id"]))
        current_row.nodes = [
            *current_row.nodes,
            {
                "occurrence_id": f"occ-{uuid4()}",
                "object_id": solution_id,
                "position": {"x": 40, "y": 40},
                "discipline": "solution",
            },
        ]

    renamed = test_client.patch(
        f"{_solution(workspace_id, solution_id)}",
        params={"state_id": candidate["id"]},
        json={"name": "Payments Platform v2"},
        headers=headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["solution"]["name"] == "Payments Platform v2"

    # The candidate edit is isolated as an override; Current is unchanged.
    current_design = test_client.get(
        f"{_solution(workspace_id, solution_id)}/design",
        params={"state_id": current["id"]},
    ).json()
    assert current_design["solution"]["name"] == "Payments Platform"

    candidate_list = test_client.get(
        f"{_discipline(workspace_id)}/solutions",
        params={"state_id": candidate["id"]},
    ).json()
    assert [s["name"] for s in candidate_list] == ["Payments Platform v2"]


def test_solution_repository_deployment_trust_flow(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    design = _create_solution(test_client, headers, workspace_id, state_id, {"name": "Platform"})
    solution_id = design["solution"]["solution_object_id"]
    created = _create_component(test_client, headers, workspace_id, solution_id, state_id, "API")
    component_id = _component_by_name(created, "API")["object_id"]
    interface_response = test_client.post(
        f"{_discipline(workspace_id)}/components/{component_id}/interfaces",
        json={"state_id": state_id, "name": "Public API", "direction": "provided"},
        headers=headers,
    )
    component = _component_by_name(interface_response.json(), "API")
    interface_id = component["interfaces"][0]["object_id"]

    repository = test_client.post(
        f"{_solution(workspace_id, solution_id)}/repositories",
        json={
            "state_id": state_id,
            "name": "Payments DB",
            "repository_type": "relational",
            "technology": "PostgreSQL",
        },
        headers=headers,
    )
    assert repository.status_code == 201, repository.text
    repository_id = repository.json()["repositories"][0]["object_id"]

    deployment = test_client.post(
        f"{_solution(workspace_id, solution_id)}/deployment-nodes",
        json={
            "state_id": state_id,
            "name": "Production Cluster",
            "environment": "production",
            "hosting": "cloud",
        },
        headers=headers,
    )
    assert deployment.status_code == 201, deployment.text
    deployment_id = deployment.json()["deployment_nodes"][0]["object_id"]

    trust = test_client.post(
        f"{_solution(workspace_id, solution_id)}/trust-boundaries",
        json={"state_id": state_id, "name": "Public DMZ", "security_level": "public"},
        headers=headers,
    )
    assert trust.status_code == 201, trust.text
    trust_id = trust.json()["trust_boundaries"][0]["object_id"]

    linked = test_client.put(
        f"{_discipline(workspace_id)}/components/{component_id}/repository",
        json={"state_id": state_id, "target_object_id": repository_id},
        headers=headers,
    )
    assert linked.status_code == 200, linked.text
    linked = test_client.put(
        f"{_discipline(workspace_id)}/components/{component_id}/deployment",
        json={"state_id": state_id, "target_object_id": deployment_id},
        headers=headers,
    )
    assert linked.status_code == 200, linked.text
    linked = test_client.put(
        f"{_discipline(workspace_id)}/interfaces/{interface_id}/trust-boundary",
        json={"state_id": state_id, "target_object_id": trust_id},
        headers=headers,
    )
    assert linked.status_code == 200, linked.text

    links = {
        (link["source_object_id"], link["target_object_id"]) for link in linked.json()["links"]
    }
    assert (component_id, repository_id) in links
    assert (component_id, deployment_id) in links
    assert (interface_id, trust_id) in links

    unlinked = test_client.put(
        f"{_discipline(workspace_id)}/components/{component_id}/repository",
        json={"state_id": state_id, "target_object_id": None},
        headers=headers,
    )
    assert unlinked.status_code == 200
    assert (component_id, repository_id) not in {
        (link["source_object_id"], link["target_object_id"]) for link in unlinked.json()["links"]
    }


def test_solution_component_delete_cascades_children(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    design = _create_solution(test_client, headers, workspace_id, state_id, {"name": "Draft"})
    solution_id = design["solution"]["solution_object_id"]
    created = _create_component(test_client, headers, workspace_id, solution_id, state_id, "API")
    component_id = _component_by_name(created, "API")["object_id"]
    interface = test_client.post(
        f"{_discipline(workspace_id)}/components/{component_id}/interfaces",
        json={"state_id": state_id, "name": "Public API"},
        headers=headers,
    )
    interface_id = _component_by_name(interface.json(), "API")["interfaces"][0]["object_id"]
    test_client.post(
        f"{_discipline(workspace_id)}/interfaces/{interface_id}/operations",
        json={"state_id": state_id, "name": "CreatePayment"},
        headers=headers,
    )

    removed = test_client.delete(
        f"{_discipline(workspace_id)}/components/{component_id}",
        params={"state_id": state_id},
        headers=headers,
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["components"] == []

    missing = test_client.get(
        f"{_solution(workspace_id, solution_id)}/components/{component_id}",
        params={"state_id": state_id},
    )
    assert missing.status_code == 404


def test_solution_duplicate_component_name_conflicts(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]
    design = _create_solution(test_client, headers, workspace_id, state_id, {"name": "Draft"})
    solution_id = design["solution"]["solution_object_id"]
    _create_component(test_client, headers, workspace_id, solution_id, state_id, "API")

    conflict = test_client.post(
        f"{_solution(workspace_id, solution_id)}/components",
        json={"state_id": state_id, "name": "API", "position": {"x": 1, "y": 1}},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_solution_requires_enabled_discipline(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": "Info Only", "disciplines": ["information"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    response = test_client.get(
        f"/api/workspaces/{workspace['id']}/solution/solutions",
        params={"state_id": current["id"]},
    )
    assert response.status_code == 404
    assert "not enabled" in response.json()["detail"].lower()


def test_solution_demo_fixture_shape():
    demo = json.loads(DEMO_PATH.read_text())
    assert demo["solution"]["name"]
    assert [c["name"] for c in demo["components"]] == ["Payment API", "Payment Worker"]
    payment_api = demo["components"][0]
    directions = {i["direction"] for i in payment_api["interfaces"]}
    assert directions == {"provided", "required"}
    operations = payment_api["interfaces"][0]["operations"]
    assert {o["operation_kind"] for o in operations} == {"operation", "event"}
    assert demo["repositories"][0]["links"] == ["Payment API", "Payment Worker"]
