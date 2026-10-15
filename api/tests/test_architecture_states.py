from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import ArchitectureState, CatalogSystem, Tenant, User, Workspace


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
        tenant = Tenant(name=f"ws-arch-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="arch@example.test",
                password_hash=hash_password("arch-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "arch@example.test", "password": "arch-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def test_workspace_disciplines_and_patch(client):
    test_client, _ = client
    headers = csrf_headers(test_client)

    # 1. Create workspace with specific disciplines
    res = test_client.post(
        "/api/workspaces",
        json={
            "name": "Integration Only WS",
            "description": "Integration architecture focus",
            "disciplines": ["integration"],
        },
        headers=headers,
    )
    assert res.status_code == 201
    created = res.json()
    assert created["name"] == "Integration Only WS"
    assert created["disciplines"] == ["integration"]

    ws_id = created["id"]

    # 2. Update disciplines via PATCH without duplicating workspace
    patch_res = test_client.patch(
        f"/api/workspaces/{ws_id}",
        json={
            "disciplines": ["solution", "integration"],
        },
        headers=headers,
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["disciplines"] == ["solution", "integration"]


def test_architecture_state_lifecycle_and_candidate_isolation(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)

    # 1. Create a workspace
    ws_res = test_client.post(
        "/api/workspaces",
        json={
            "name": "Core Banking Architecture",
            "disciplines": ["enterprise", "solution", "integration"],
        },
        headers=headers,
    )
    assert ws_res.status_code == 201
    workspace_id = ws_res.json()["id"]

    # 2. Add two canonical systems in the catalog
    sys_a = test_client.post(
        "/api/catalog/systems",
        json={"name": "Payment Gateway", "kind": "service", "position": {"x": 100, "y": 150}},
        headers=headers,
    ).json()

    sys_b = test_client.post(
        "/api/catalog/systems",
        json={"name": "Core Ledger", "kind": "database", "position": {"x": 500, "y": 150}},
        headers=headers,
    ).json()

    # 3. List states for workspace -> triggers auto-initialization of Current State
    states_res = test_client.get(f"/api/workspaces/{workspace_id}/states")
    assert states_res.status_code == 200
    states = states_res.json()
    assert len(states) == 1
    current_state = states[0]
    assert current_state["name"] == "Current State"
    assert current_state["state_type"] == "current"

    # Verify nodes reference canonical systems through object_id
    current_nodes = current_state["nodes"]
    assert len(current_nodes) == 2
    obj_ids = {n["object_id"] for n in current_nodes}
    assert sys_a["id"] in obj_ids
    assert sys_b["id"] in obj_ids

    current_state_id = current_state["id"]

    # 4. Duplicate Current State into Candidate Design
    dup_res = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current_state_id}/duplicate",
        json={
            "target_name": "Candidate Design",
            "target_state_type": "candidate",
            "description": "Proposed payment queue decoupling",
        },
        headers=headers,
    )
    assert dup_res.status_code == 201
    candidate_state = dup_res.json()
    assert candidate_state["name"] == "Candidate Design"
    assert candidate_state["state_type"] == "candidate"
    assert candidate_state["id"] != current_state_id

    candidate_state_id = candidate_state["id"]
    candidate_nodes = candidate_state["nodes"]
    assert len(candidate_nodes) == 2

    # Verify occurrence_ids are fresh while object_ids are preserved
    assert candidate_nodes[0]["occurrence_id"] != current_nodes[0]["occurrence_id"]
    assert candidate_nodes[0]["object_id"] == current_nodes[0]["object_id"]

    # 5. Modify Candidate State: move a node, set candidate overrides, and add a relationship
    candidate_nodes[0]["position"] = {"x": 300, "y": 400}
    candidate_nodes[0]["candidate_overrides"] = {"name": "Payment Gateway v2"}

    new_rel = {
        "id": "rel-custom-1",
        "source_id": candidate_nodes[0]["occurrence_id"],
        "target_id": candidate_nodes[1]["occurrence_id"],
        "type": "Consumes",
        "name": "Async Events",
    }

    update_res = test_client.put(
        f"/api/workspaces/{workspace_id}/states/{candidate_state_id}",
        json={
            "nodes": candidate_nodes,
            "relationships": [new_rel],
        },
        headers=headers,
    )
    assert update_res.status_code == 200
    updated_candidate = update_res.json()
    assert updated_candidate["nodes"][0]["position"]["x"] == 300
    assert updated_candidate["nodes"][0]["candidate_overrides"]["name"] == "Payment Gateway v2"
    assert len(updated_candidate["relationships"]) == 1

    # 6. Verify Complete State Isolation: Current State must remain untouched!
    current_check = test_client.get(
        f"/api/workspaces/{workspace_id}/states/{current_state_id}"
    ).json()
    assert current_check["nodes"][0]["position"]["x"] == 100
    assert current_check["nodes"][0]["candidate_overrides"] == {}
    assert len(current_check["relationships"]) == 0

    # Verify canonical system in database is untouched
    with testing_sessions() as db:
        canonical_sys = db.get(CatalogSystem, UUID(sys_a["id"]))
        assert canonical_sys.name == "Payment Gateway"


def _create_system_with_object(test_client: TestClient, name: str) -> tuple[dict, dict]:
    headers = csrf_headers(test_client)
    system = test_client.post(
        "/api/catalog/systems", json={"name": name, "kind": "service"}, headers=headers
    )
    assert system.status_code == 201
    obj = test_client.post(
        f"/api/catalog/systems/{system.json()['id']}/objects",
        json={"name": f"{name} object"},
        headers=headers,
    )
    assert obj.status_code == 201
    return system.json(), obj.json()


def test_auto_initialized_relationships_reference_occurrences_and_survive_duplication(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    ws = test_client.post(
        "/api/workspaces", json={"name": "Integration Canvas"}, headers=headers
    ).json()
    workspace_id = ws["id"]

    source_system, source_object = _create_system_with_object(test_client, "Orders")
    target_system, target_object = _create_system_with_object(test_client, "Billing")
    integration = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": source_system["id"],
            "source_object_id": source_object["id"],
            "target_system_id": target_system["id"],
            "target_object_id": target_object["id"],
            "name": "Order billing",
        },
        headers=headers,
    )
    assert integration.status_code == 201
    integration_id = integration.json()["id"]

    current = test_client.get(f"/api/workspaces/{workspace_id}/states").json()[0]
    occurrence_by_object = {n["object_id"]: n["occurrence_id"] for n in current["nodes"]}
    [rel] = current["relationships"]
    assert rel["integration_id"] == integration_id
    assert rel["source_id"] == occurrence_by_object[source_system["id"]]
    assert rel["target_id"] == occurrence_by_object[target_system["id"]]

    candidate = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    candidate_occurrences = {n["occurrence_id"] for n in candidate["nodes"]}
    [candidate_rel] = candidate["relationships"]
    assert candidate_rel["integration_id"] == integration_id
    assert candidate_rel["source_id"] in candidate_occurrences
    assert candidate_rel["target_id"] in candidate_occurrences
    assert candidate_rel["source_id"] not in occurrence_by_object.values()


def test_workspace_disciplines_are_validated(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    invalid = test_client.post(
        "/api/workspaces",
        json={"name": "Bad disciplines", "disciplines": ["astrology"]},
        headers=headers,
    )
    assert invalid.status_code == 422
    empty = test_client.post(
        "/api/workspaces", json={"name": "No disciplines", "disciplines": []}, headers=headers
    )
    assert empty.status_code == 422

    ws = test_client.post(
        "/api/workspaces",
        json={"name": "Deduped", "disciplines": ["solution", "solution", "integration"]},
        headers=headers,
    )
    assert ws.status_code == 201
    assert ws.json()["disciplines"] == ["solution", "integration"]


def test_architecture_states_require_workspace_access(client):
    test_client, testing_sessions = client
    with testing_sessions.begin() as db:
        other = Tenant(name=f"other-tenant-{uuid4()}")
        db.add(other)
        db.flush()
        other_id = other.id
    response = test_client.get(f"/api/workspaces/{other_id}/states")
    assert response.status_code == 404
    with testing_sessions() as db:
        assert db.get(Workspace, other_id) is None
        assert (
            db.scalars(
                select(ArchitectureState).where(ArchitectureState.workspace_id == other_id)
            ).first()
            is None
        )


def test_thin_architecture_objects_reuse_systems_and_are_candidate_isolated(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={
            "name": "Shared Architecture Views",
            "disciplines": ["enterprise", "information", "solution", "integration"],
        },
        headers=headers,
    ).json()
    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "Shared System", "kind": "service"},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()

    object_drafts = [
        ("business_requirement", "Requirement", "related_system_id", None),
        ("business_capability", "Capability", "related_system_id", None),
        ("solution_boundary", "Boundary", "related_system_id", None),
        ("component", "Component", "related_system_id", None),
        ("interface", "Interface", "related_system_id", None),
        ("information_object", "Information", "authoritative_system_id", "Data Team"),
    ]
    created_objects = []
    latest_candidate = candidate
    for index, (kind, name, system_key, owner) in enumerate(object_drafts):
        body = {
            "kind": kind,
            "state_id": candidate["id"],
            "name": name,
            "description": f"{name} details",
            system_key: system["id"],
            "position": {"x": 100.0 + index * 60, "y": 220.0 + index * 60},
        }
        if owner:
            body["owner"] = owner
        response = test_client.post(
            f"/api/workspaces/{workspace['id']}/architecture-objects",
            json=body,
            headers=headers,
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["object"]["kind"] == kind
        assert payload["state"]["id"] == candidate["id"]
        created_objects.append(payload["object"])
        latest_candidate = payload["state"]

    candidate_ids = {node["object_id"] for node in latest_candidate["nodes"]}
    assert system["id"] in candidate_ids
    assert {item["id"] for item in created_objects}.issubset(candidate_ids)
    assert len(latest_candidate["relationships"]) == len(object_drafts)
    info = next(item for item in created_objects if item["kind"] == "information_object")
    assert info["owner"] == "Data Team"
    assert info["authoritative_system_id"] == system["id"]

    current_after = test_client.get(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}"
    ).json()
    assert {node["object_id"] for node in current_after["nodes"]} == {system["id"]}
    assert current_after["relationships"] == []

    current_write = test_client.put(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}",
        json={"nodes": current_after["nodes"], "relationships": []},
        headers=headers,
    )
    assert current_write.status_code == 409
    current_delete = test_client.delete(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}",
        headers=headers,
    )
    assert current_delete.status_code == 409

    listed = test_client.get(
        f"/api/workspaces/{workspace['id']}/architecture-objects"
    )
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {item["id"] for item in created_objects}


def test_disabled_architecture_object_kinds_are_not_exposed(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": "Integration Only", "disciplines": ["integration"]},
        headers=headers,
    ).json()
    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "Integration System", "kind": "service"},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()

    response = test_client.post(
        f"/api/workspaces/{workspace['id']}/architecture-objects",
        json={
            "kind": "business_requirement",
            "state_id": candidate["id"],
            "name": "Not enabled",
            "related_system_id": system["id"],
            "position": {"x": 100, "y": 200},
        },
        headers=headers,
    )
    assert response.status_code == 404
    assert test_client.get(
        f"/api/workspaces/{workspace['id']}/architecture-objects"
    ).json() == []
