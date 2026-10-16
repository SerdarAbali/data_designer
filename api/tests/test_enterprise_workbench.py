import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.architecture.schemas import EnterpriseObjectCreate, EnterpriseObjectResponse
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import ArchitectureRelationship, ArchitectureState, Tenant, User, Workspace

DEMO_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "enterprise-architecture" / "demo.json"
)


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
        tenant = Tenant(name=f"ws-enterprise-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="enterprise@example.test",
                password_hash=hash_password("enterprise-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "enterprise@example.test", "password": "enterprise-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _workspace_with_candidate(test_client, headers, disciplines=("enterprise",)):
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": "Enterprise Workspace", "disciplines": list(disciplines)},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Strategy"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _discipline(workspace_id) -> str:
    return f"/api/workspaces/{workspace_id}/enterprise"


def _create_object(test_client, headers, workspace_id, state_id, kind, name, **kw):
    response = test_client.post(
        f"{_discipline(workspace_id)}/objects",
        json={"state_id": state_id, "kind": kind, "name": name, "position": {"x": 0, "y": 0}, **kw},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _link(test_client, headers, workspace_id, state_id, relationship_type, source, target):
    response = test_client.post(
        f"{_discipline(workspace_id)}/links",
        json={
            "state_id": state_id,
            "relationship_type": relationship_type,
            "source_object_id": source,
            "target_object_id": target,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _group(model, group, name):
    return next(item for item in model[group] if item["name"] == name)


def _append_node(sessions, state_id, object_ids):
    with sessions.begin() as db:
        state = db.get(ArchitectureState, UUID(str(state_id)))
        state.nodes = [
            *state.nodes,
            *[
                {
                    "occurrence_id": f"occ-{object_id}",
                    "object_id": str(object_id),
                    "position": {"x": 0.0, "y": 0.0},
                    "discipline": "enterprise",
                    "parent_occurrence_id": None,
                    "width": None,
                    "height": None,
                    "display_metadata": {},
                    "candidate_overrides": {},
                }
                for object_id in object_ids
            ],
        ]


def _insert_relationship(sessions, tenant_id, source, target, relationship_type, state_id):
    with sessions.begin() as db:
        db.add(
            ArchitectureRelationship(
                id=uuid4(),
                tenant_id=tenant_id,
                source_object_id=UUID(str(source)),
                target_object_id=UUID(str(target)),
                relationship_type=relationship_type,
                properties={},
                created_in_state_id=UUID(str(state_id)) if state_id else None,
            )
        )


def test_enterprise_object_crud_and_isolation(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    model = _create_object(
        test_client,
        headers,
        workspace_id,
        state_id,
        "goal",
        "Grow revenue",
        owner="CFO",
        outcome_metric="+10% ARR",
        horizon="FY27",
    )
    assert _group(model, "goals", "Grow revenue")["outcome_metric"] == "+10% ARR"
    assert _group(model, "goals", "Grow revenue")["owner"] == "CFO"

    _create_object(test_client, headers, workspace_id, state_id, "requirement", "Faster payments")
    _create_object(test_client, headers, workspace_id, state_id, "capability", "Payment processing")
    process_model = _create_object(
        test_client,
        headers,
        workspace_id,
        state_id,
        "process",
        "Card settlement",
        process_type="value_stream",
    )
    assert _group(process_model, "processes", "Card settlement")["process_type"] == "value_stream"
    principle_model = _create_object(
        test_client,
        headers,
        workspace_id,
        state_id,
        "principle",
        "Data residency",
        principle_type="constraint",
        rationale="Regulated workloads stay in-region.",
    )
    assert _group(principle_model, "principles", "Data residency")["principle_type"] == "constraint"
    role_model = _create_object(
        test_client, headers, workspace_id, state_id, "role", "Payments Team", role_type="role"
    )
    assert _group(role_model, "roles", "Payments Team")["role_type"] == "role"

    assert len(role_model["goals"]) == 1
    assert len(role_model["requirements"]) == 1
    assert len(role_model["capabilities"]) == 1
    assert len(role_model["processes"]) == 1
    assert len(role_model["principles"]) == 1
    assert len(role_model["roles"]) == 1

    current_model = test_client.get(
        f"{_discipline(workspace_id)}/model",
        params={"state_id": current["id"]},
    ).json()
    assert current_model["editable"] is False
    assert current_model["goals"] == []
    assert current_model["capabilities"] == []
    assert role_model["editable"] is True

    response = test_client.post(
        f"{_discipline(workspace_id)}/objects",
        json={"state_id": current["id"], "kind": "goal", "name": "Blocked"},
        headers=headers,
    )
    assert response.status_code == 409, response.text

    duplicate = test_client.post(
        f"{_discipline(workspace_id)}/objects",
        json={"state_id": state_id, "kind": "goal", "name": "Grow revenue"},
        headers=headers,
    )
    assert duplicate.status_code == 409, duplicate.text

    goal_id = _group(role_model, "goals", "Grow revenue")["object_id"]
    updated = test_client.patch(
        f"{_discipline(workspace_id)}/objects/{goal_id}",
        json={"state_id": state_id, "owner": "COO"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert _group(updated.json(), "goals", "Grow revenue")["owner"] == "COO"

    process_id = _group(role_model, "processes", "Card settlement")["object_id"]
    deleted = test_client.delete(
        f"{_discipline(workspace_id)}/objects/{process_id}",
        params={"state_id": state_id},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["processes"] == []


def test_enterprise_discipline_gating(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(
        test_client, headers, disciplines=("solution",)
    )
    response = test_client.get(
        f"{_discipline(workspace['id'])}/model",
        params={"state_id": candidate["id"]},
        headers=headers,
    )
    assert response.status_code == 404, response.text
    assert "not enabled" in response.json()["detail"]


def test_enterprise_links_and_views(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    model = _create_object(test_client, headers, workspace_id, state_id, "goal", "Grow revenue")
    goal_id = _group(model, "goals", "Grow revenue")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, state_id, "requirement", "Faster payments"
    )
    requirement_id = _group(model, "requirements", "Faster payments")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, state_id, "capability", "Payment processing"
    )
    capability_id = _group(model, "capabilities", "Payment processing")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, state_id, "process", "Card settlement"
    )
    process_id = _group(model, "processes", "Card settlement")["object_id"]
    model = _create_object(
        test_client,
        headers,
        workspace_id,
        state_id,
        "principle",
        "Data residency",
        principle_type="constraint",
    )
    principle_id = _group(model, "principles", "Data residency")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, state_id, "role", "Payments Team", role_type="role"
    )
    role_id = _group(model, "roles", "Payments Team")["object_id"]

    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "Core Banking", "kind": "service"},
        headers=headers,
    ).json()

    _link(test_client, headers, workspace_id, state_id, "drives", goal_id, requirement_id)
    _link(test_client, headers, workspace_id, state_id, "needs", requirement_id, capability_id)
    _link(test_client, headers, workspace_id, state_id, "has_process", capability_id, process_id)
    _link(test_client, headers, workspace_id, state_id, "supports", system["id"], capability_id)
    _link(test_client, headers, workspace_id, state_id, "supports", system["id"], process_id)
    _link(test_client, headers, workspace_id, state_id, "satisfies", system["id"], requirement_id)
    _link(test_client, headers, workspace_id, state_id, "governed_by", capability_id, principle_id)
    _link(test_client, headers, workspace_id, state_id, "owned_by", capability_id, role_id)

    invalid = test_client.post(
        f"{_discipline(workspace_id)}/links",
        json={
            "state_id": state_id,
            "relationship_type": "drives",
            "source_object_id": capability_id,
            "target_object_id": requirement_id,
        },
        headers=headers,
    )
    assert invalid.status_code == 422, invalid.text

    duplicate = test_client.post(
        f"{_discipline(workspace_id)}/links",
        json={
            "state_id": state_id,
            "relationship_type": "drives",
            "source_object_id": goal_id,
            "target_object_id": requirement_id,
        },
        headers=headers,
    )
    assert duplicate.status_code == 409, duplicate.text

    capability_map = test_client.get(
        f"{_discipline(workspace_id)}/capability-map", params={"state_id": state_id}
    ).json()
    entry = next(
        item
        for item in capability_map["capabilities"]
        if item["capability"]["name"] == "Payment processing"
    )
    assert [p["name"] for p in entry["processes"]] == ["Card settlement"]
    assert [a["name"] for a in entry["applications"]] == ["Core Banking"]
    assert [p["name"] for p in entry["principles"]] == ["Data residency"]
    assert entry["owner_role"]["name"] == "Payments Team"

    process_impact = test_client.get(
        f"{_discipline(workspace_id)}/process-impact", params={"state_id": state_id}
    ).json()
    process_entry = next(
        item for item in process_impact["processes"] if item["process"]["name"] == "Card settlement"
    )
    assert [c["name"] for c in process_entry["capabilities"]] == ["Payment processing"]
    assert [a["name"] for a in process_entry["applications"]] == ["Core Banking"]
    assert [r["name"] for r in process_entry["requirements"]] == ["Faster payments"]

    application_support = test_client.get(
        f"{_discipline(workspace_id)}/application-support", params={"state_id": state_id}
    ).json()
    support_entry = next(
        item
        for item in application_support["applications"]
        if item["application"]["name"] == "Core Banking"
    )
    assert [c["name"] for c in support_entry["capabilities"]] == ["Payment processing"]
    assert [p["name"] for p in support_entry["processes"]] == ["Card settlement"]
    assert [r["name"] for r in support_entry["requirements"]] == ["Faster payments"]

    trace = test_client.get(
        f"{_discipline(workspace_id)}/strategy-trace", params={"state_id": state_id}
    ).json()
    chain = next(item for item in trace["chains"] if item["goal"]["name"] == "Grow revenue")
    assert chain["gaps"] == []
    step = chain["steps"][0]
    assert step["requirement"]["name"] == "Faster payments"
    assert [c["name"] for c in step["capabilities"]] == ["Payment processing"]
    assert [p["name"] for p in step["processes"]] == ["Card settlement"]
    assert [a["name"] for a in step["applications"]] == ["Core Banking"]
    assert trace["gaps"] == []
    assert trace["unlinked_requirements"] == []


def test_enterprise_strategy_gaps(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    _create_object(test_client, headers, workspace_id, state_id, "goal", "Unmet goal")
    trace = test_client.get(
        f"{_discipline(workspace_id)}/strategy-trace", params={"state_id": state_id}
    ).json()
    chain = next(item for item in trace["chains"] if item["goal"]["name"] == "Unmet goal")
    assert chain["steps"] == []
    assert any("no linked requirement" in gap for gap in chain["gaps"])
    assert any("no linked requirement" in gap for gap in trace["gaps"])


def test_enterprise_candidate_overrides_current(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    model = _create_object(
        test_client, headers, workspace_id, state_id, "capability", "Payment processing"
    )
    capability_id = _group(model, "capabilities", "Payment processing")["object_id"]

    include = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current['id']}/include-objects",
        json={"architecture_object_ids": [capability_id]},
        headers=headers,
    )
    assert include.status_code == 200, include.text

    updated = test_client.patch(
        f"{_discipline(workspace_id)}/objects/{capability_id}",
        json={"state_id": state_id, "name": "Payments processing"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert [c["name"] for c in updated.json()["capabilities"]] == ["Payments processing"]

    current_model = test_client.get(
        f"{_discipline(workspace_id)}/model", params={"state_id": current["id"]}
    ).json()
    assert [c["name"] for c in current_model["capabilities"]] == ["Payment processing"]


def test_enterprise_impact_diff(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    model = _create_object(
        test_client, headers, workspace_id, state_id, "capability", "Reused capability"
    )
    reused_id = _group(model, "capabilities", "Reused capability")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, state_id, "capability", "Changed capability"
    )
    changed_id = _group(model, "capabilities", "Changed capability")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, state_id, "capability", "Removed capability"
    )
    removed_id = _group(model, "capabilities", "Removed capability")["object_id"]
    _create_object(test_client, headers, workspace_id, state_id, "goal", "Added goal")

    include = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current['id']}/include-objects",
        json={"architecture_object_ids": [reused_id, changed_id, removed_id]},
        headers=headers,
    )
    assert include.status_code == 200, include.text

    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "Core Banking", "kind": "service"},
        headers=headers,
    ).json()
    _link(test_client, headers, workspace_id, state_id, "supports", system["id"], changed_id)

    patched = test_client.patch(
        f"{_discipline(workspace_id)}/objects/{changed_id}",
        json={"state_id": state_id, "name": "Renamed capability"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    removed = test_client.delete(
        f"{_discipline(workspace_id)}/objects/{removed_id}",
        params={"state_id": state_id},
        headers=headers,
    )
    assert removed.status_code == 200, removed.text

    impact = test_client.get(
        f"{_discipline(workspace_id)}/impact", params={"state_id": state_id}
    ).json()
    by_id = {change["object_id"]: change["change"] for change in impact["changes"]}
    assert by_id[reused_id] == "reused"
    assert by_id[changed_id] == "changed"
    assert by_id[removed_id] == "removed"
    added = next(change for change in impact["changes"] if change["name"] == "Added goal")
    assert added["change"] == "added"
    changed = next(change for change in impact["changes"] if change["object_id"] == changed_id)
    assert changed["changed_fields"] == ["name"]

    affected_capability_ids = {c["object_id"] for c in impact["affected_capabilities"]}
    assert changed_id in affected_capability_ids
    assert removed_id in affected_capability_ids
    assert [a["name"] for a in impact["affected_applications"]] == ["Core Banking"]
    assert impact["unresolved_dependencies"] == []
    assert impact["baseline_state_id"] == current["id"]


def test_enterprise_impact_constraints_and_risks(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    model = _create_object(
        test_client,
        headers,
        workspace_id,
        state_id,
        "principle",
        "Data residency",
        principle_type="constraint",
    )
    constraint_id = _group(model, "principles", "Data residency")["object_id"]
    _create_object(
        test_client,
        headers,
        workspace_id,
        state_id,
        "principle",
        "Vendor lock-in",
        principle_type="risk",
    )
    model = _create_object(
        test_client, headers, workspace_id, state_id, "capability", "Payment processing"
    )
    capability_id = _group(model, "capabilities", "Payment processing")["object_id"]

    impact = test_client.get(
        f"{_discipline(workspace_id)}/impact", params={"state_id": state_id}
    ).json()
    assert any("Data residency" in item for item in impact["unresolved_constraints"])
    assert [r["name"] for r in impact["risks"]] == ["Vendor lock-in"]

    governed = test_client.post(
        f"{_discipline(workspace_id)}/links",
        json={
            "state_id": state_id,
            "relationship_type": "governed_by",
            "source_object_id": capability_id,
            "target_object_id": constraint_id,
        },
        headers=headers,
    )
    assert governed.status_code == 201, governed.text
    impact = test_client.get(
        f"{_discipline(workspace_id)}/impact", params={"state_id": state_id}
    ).json()
    assert all("Data residency" not in item for item in impact["unresolved_constraints"])


def test_enterprise_delete_link(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    model = _create_object(test_client, headers, workspace_id, state_id, "goal", "Grow revenue")
    goal_id = _group(model, "goals", "Grow revenue")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, state_id, "requirement", "Faster payments"
    )
    requirement_id = _group(model, "requirements", "Faster payments")["object_id"]

    model = _link(test_client, headers, workspace_id, state_id, "drives", goal_id, requirement_id)
    link_id = model["links"][0]["id"]
    removed = test_client.delete(
        f"{_discipline(workspace_id)}/links/{link_id}",
        params={"state_id": state_id},
        headers=headers,
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["links"] == []


def test_enterprise_relationship_state_filtering(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    with sessions() as db:
        tenant_id = db.get(Workspace, UUID(workspace_id)).tenant_id

    def create(kind, name, **kw):
        model = _create_object(
            test_client, headers, workspace_id, candidate["id"], kind, name, **kw
        )
        group = {
            "goal": "goals",
            "requirement": "requirements",
            "capability": "capabilities",
            "process": "processes",
            "principle": "principles",
            "role": "roles",
        }[kind]
        return _group(model, group, name)["object_id"]

    goal = create("goal", "Connected goal")
    requirement = create("requirement", "Connected requirement")
    capability = create("capability", "Connected capability")
    process = create("process", "Connected process")
    principle = create("principle", "Connected principle", principle_type="constraint")
    role = create("role", "Connected role", role_type="role")

    # Expose the authored objects in Current too so canonical (NULL-scoped)
    # relationships are resolvable there.
    _append_node(
        sessions, current["id"], [goal, requirement, capability, process, principle, role]
    )

    # Canonical baseline relationships: visible in every state.
    _insert_relationship(sessions, tenant_id, goal, requirement, "drives", None)
    _insert_relationship(sessions, tenant_id, requirement, capability, "needs", None)
    _insert_relationship(sessions, tenant_id, capability, process, "has_process", None)
    _insert_relationship(sessions, tenant_id, capability, principle, "governed_by", None)
    _insert_relationship(sessions, tenant_id, process, principle, "governed_by", None)
    _insert_relationship(sessions, tenant_id, capability, role, "owned_by", None)

    for state in (current, candidate):
        state_id = state["id"]
        model = test_client.get(
            f"{_discipline(workspace_id)}/model", params={"state_id": state_id}
        ).json()
        types = {link["relationship_type"] for link in model["links"]}
        assert {"drives", "needs", "has_process", "governed_by", "owned_by"} <= types

        trace = test_client.get(
            f"{_discipline(workspace_id)}/strategy-trace", params={"state_id": state_id}
        ).json()
        chain = next(item for item in trace["chains"] if item["goal"]["name"] == "Connected goal")
        assert [step["requirement"]["name"] for step in chain["steps"]] == [
            "Connected requirement"
        ]

        capability_map = test_client.get(
            f"{_discipline(workspace_id)}/capability-map", params={"state_id": state_id}
        ).json()
        entry = next(
            item
            for item in capability_map["capabilities"]
            if item["capability"]["name"] == "Connected capability"
        )
        assert [item["name"] for item in entry["processes"]] == ["Connected process"]
        assert entry["owner_role"]["name"] == "Connected role"

        process_impact = test_client.get(
            f"{_discipline(workspace_id)}/process-impact", params={"state_id": state_id}
        ).json()
        impacted = next(
            item
            for item in process_impact["processes"]
            if item["process"]["name"] == "Connected process"
        )
        assert [item["name"] for item in impacted["capabilities"]] == ["Connected capability"]
        assert [item["name"] for item in impacted["governed_by"]] == ["Connected principle"]

        application_support = test_client.get(
            f"{_discipline(workspace_id)}/application-support", params={"state_id": state_id}
        ).json()
        assert application_support["applications"] == []


def test_enterprise_relationship_candidate_scoping(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    with sessions() as db:
        tenant_id = db.get(Workspace, UUID(workspace_id)).tenant_id

    model = _create_object(
        test_client, headers, workspace_id, candidate["id"], "goal", "Shared goal"
    )
    shared_goal = _group(model, "goals", "Shared goal")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, candidate["id"], "requirement", "Shared requirement"
    )
    shared_requirement = _group(model, "requirements", "Shared requirement")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, candidate["id"], "goal", "Candidate-only goal"
    )
    scoped_goal = _group(model, "goals", "Candidate-only goal")["object_id"]
    model = _create_object(
        test_client,
        headers,
        workspace_id,
        candidate["id"],
        "requirement",
        "Candidate-only requirement",
    )
    scoped_requirement = _group(model, "requirements", "Candidate-only requirement")["object_id"]

    _append_node(
        sessions,
        current["id"],
        [shared_goal, shared_requirement, scoped_goal, scoped_requirement],
    )
    _insert_relationship(sessions, tenant_id, shared_goal, shared_requirement, "drives", None)
    _insert_relationship(
        sessions, tenant_id, scoped_goal, scoped_requirement, "drives", candidate["id"]
    )

    def drives_pairs(state_id):
        model = test_client.get(
            f"{_discipline(workspace_id)}/model", params={"state_id": state_id}
        ).json()
        return {
            (link["source_object_id"], link["target_object_id"])
            for link in model["links"]
            if link["relationship_type"] == "drives"
        }

    current_pairs = drives_pairs(current["id"])
    candidate_pairs = drives_pairs(candidate["id"])
    assert (shared_goal, shared_requirement) in current_pairs
    assert (shared_goal, shared_requirement) in candidate_pairs
    assert (scoped_goal, scoped_requirement) not in current_pairs
    assert (scoped_goal, scoped_requirement) in candidate_pairs


def test_enterprise_relationships_do_not_leak_between_candidates(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]
    with sessions() as db:
        tenant_id = db.get(Workspace, UUID(workspace_id)).tenant_id

    other_candidate = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{current['id']}/duplicate",
        json={"target_name": "Second Candidate"},
        headers=headers,
    ).json()

    model = _create_object(
        test_client, headers, workspace_id, candidate["id"], "capability", "Leak capability"
    )
    capability = _group(model, "capabilities", "Leak capability")["object_id"]
    model = _create_object(
        test_client, headers, workspace_id, candidate["id"], "process", "Leak process"
    )
    process = _group(model, "processes", "Leak process")["object_id"]

    _append_node(sessions, candidate["id"], [capability, process])
    _append_node(sessions, other_candidate["id"], [capability, process])

    _insert_relationship(
        sessions, tenant_id, capability, process, "has_process", other_candidate["id"]
    )

    def has_process_pairs(state_id):
        model = test_client.get(
            f"{_discipline(workspace_id)}/model", params={"state_id": state_id}
        ).json()
        return {
            (link["source_object_id"], link["target_object_id"])
            for link in model["links"]
            if link["relationship_type"] == "has_process"
        }

    assert (capability, process) in has_process_pairs(other_candidate["id"])
    assert (capability, process) not in has_process_pairs(candidate["id"])
    assert (capability, process) not in has_process_pairs(current["id"])


def test_enterprise_demo_fixture_shape():
    assert DEMO_PATH.exists(), f"missing enterprise demo fixture at {DEMO_PATH}"
    demo = json.loads(DEMO_PATH.read_text())
    kinds = {obj["kind"] for obj in demo["objects"]}
    assert {"goal", "requirement", "capability", "process", "principle", "role"} <= kinds
    relationship_types = {link["relationship_type"] for link in demo["links"]}
    assert {"drives", "needs", "has_process", "supports", "satisfies"} <= relationship_types

    # Every demo object validates against both the request and response schemas
    # (this is what rejects out-of-enum values such as role_type="team").
    state_id = uuid4()
    for obj in demo["objects"]:
        EnterpriseObjectCreate(
            state_id=state_id,
            kind=obj["kind"],
            name=obj["name"],
            description=obj.get("description"),
            owner=obj.get("owner"),
            outcome_metric=obj.get("outcome_metric"),
            horizon=obj.get("horizon"),
            process_type=obj.get("process_type"),
            principle_type=obj.get("principle_type"),
            rationale=obj.get("rationale"),
            role_type=obj.get("role_type"),
        )
        EnterpriseObjectResponse.model_validate({**obj, "object_id": uuid4()})
