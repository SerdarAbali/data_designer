from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import (
    IntegrationFieldRef,
    Scenario,
    Tenant,
    User,
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
        tenant = Tenant(name=f"traceability-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="trace@example.test",
                password_hash=hash_password("trace-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "trace@example.test", "password": "trace-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _workspace(test_client: TestClient, headers: dict[str, str], disciplines: list[str]):
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": f"Trace {uuid4().hex[:8]}", "disciplines": disciplines},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _trace_url(workspace_id: str) -> str:
    return f"/api/workspaces/{workspace_id}"


def test_architecture_graph_information_to_contract_chain(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(
        test_client, headers, ["enterprise", "information", "solution", "integration"]
    )
    workspace_id = workspace["id"]
    base = _trace_url(workspace_id)

    # Catalog endpoint used for physical realization.
    system = test_client.post(
        "/api/catalog/systems", json={"name": "CRM", "kind": "service"}, headers=headers
    ).json()
    catalog_object = test_client.post(
        f"/api/catalog/systems/{system['id']}/objects",
        json={"name": "customer"},
        headers=headers,
    ).json()
    field = test_client.post(
        f"/api/catalog/objects/{catalog_object['id']}/fields",
        json={"name": "email", "data_type": "string"},
        headers=headers,
    ).json()

    entity = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities",
        json={
            "state_id": candidate["id"],
            "name": "Customer",
            "owner": "Data Office",
            "steward": "CRM Team",
            "classification": "confidential",
            "sensitivity": "high",
            "authoritative_system_id": system["id"],
            "position": {"x": 40, "y": 40},
        },
        headers=headers,
    ).json()["entity"]
    entity_id = entity["object_id"]
    attr = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities/{entity_id}/attributes",
        json={"state_id": candidate["id"], "name": "email", "data_type": "string"},
        headers=headers,
    ).json()
    attr_id = attr["object_id"]
    test_client.put(
        f"/api/workspaces/{workspace_id}/information/attributes/{attr_id}/realization",
        json={"state_id": candidate["id"], "catalog_field_id": field["id"]},
        headers=headers,
    )

    target_system = test_client.post(
        "/api/catalog/systems", json={"name": "ERP", "kind": "service"}, headers=headers
    ).json()
    target_object = test_client.post(
        f"/api/catalog/systems/{target_system['id']}/objects",
        json={"name": "account"},
        headers=headers,
    ).json()
    integration = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": system["id"],
            "source_object_id": catalog_object["id"],
            "target_system_id": target_system["id"],
            "target_object_id": target_object["id"],
            "name": "Customer sync",
            "graph": {"version": 1, "nodes": [], "edges": []},
            "sample_rows": [],
        },
        headers=headers,
    ).json()
    integration_id = integration["id"]

    # Authoritative mapping + scenario reference inserted directly (engine write path).
    with testing_sessions.begin() as db:
        db.add(
            IntegrationFieldRef(
                id=uuid4(),
                tenant_id=UUID(workspace_id),
                integration_id=UUID(integration_id),
                object_id=UUID(catalog_object["id"]),
                field_id=UUID(field["id"]),
                direction="source",
            )
        )
        db.add(
            Scenario(
                id=uuid4(),
                tenant_id=UUID(workspace_id),
                scope_integration_id=UUID(integration_id),
                name="Customer sync happy path",
                category="happy_path",
                document={"version": 1, "contractIds": [integration_id]},
            )
        )

    graph = test_client.get(
        f"{base}/architecture-graph", params={"state_id": candidate["id"]}
    ).json()
    kinds = {node["id"]: node["kind"] for node in graph["nodes"]}
    assert kinds[entity_id] == "information_object"
    assert kinds[attr_id] == "information_attribute"
    assert integration_id in kinds and kinds[integration_id] == "contract_ref"

    derived = {
        (edge["source_object_id"], edge["target_object_id"], edge["relationship_type"])
        for edge in graph["edges"]
    }
    assert (entity_id, attr_id, "has_attribute") in derived

    edge_types = {edge["relationship_type"] for edge in graph["edges"]}
    assert {"has_attribute", "realizes", "mapped_by", "verified_by"} <= edge_types

    usages = test_client.get(
        f"{base}/objects/{attr_id}/usages", params={"state_id": candidate["id"]}
    ).json()
    labels = {group["label"] for group in usages["groups"]}
    assert "Physical realization" in labels
    assert usages["physical_refs"], "attribute carries a physical catalog reference"

    field_ref_id = next(
        node["id"] for node in graph["nodes"] if node["kind"] == "catalog_field_ref"
    )
    field_usages = test_client.get(
        f"{base}/objects/{field_ref_id}/usages", params={"state_id": candidate["id"]}
    ).json()
    field_labels = {group["label"] for group in field_usages["groups"]}
    assert "Mapped into contracts" in field_labels

    chain = test_client.get(
        f"{base}/trace",
        params={
            "state_id": candidate["id"],
            "object_id": entity_id,
            "direction": "both",
            "depth": 5,
        },
    ).json()
    names = {node["name"] for node in chain["nodes"]}
    assert {"Customer", "email", "Customer sync"}.issubset(names)

    # Ownership + lineage metadata is surfaced by the information model.
    model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model", params={"state_id": candidate["id"]}
    ).json()
    customer = next(e for e in model["entities"] if e["name"] == "Customer")
    assert customer["steward"] == "CRM Team"
    assert customer["classification"] == "confidential"
    assert customer["sensitivity"] == "high"
    assert customer["authoritative_system_name"] == "CRM"


def test_trace_enterprise_goal_chain(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers, ["enterprise"])
    workspace_id = workspace["id"]
    base = _trace_url(workspace_id)

    def create(kind: str, name: str) -> str:
        response = test_client.post(
            f"/api/workspaces/{workspace_id}/enterprise/objects",
            json={"state_id": candidate["id"], "kind": kind, "name": name},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        model = response.json()
        group = {
            "goal": "goals",
            "requirement": "requirements",
            "capability": "capabilities",
            "process": "processes",
        }[kind]
        return next(o for o in model[group] if o["name"] == name)["object_id"]

    goal = create("goal", "Grow revenue")
    requirement = create("requirement", "Offer self-service")
    capability = create("capability", "Customer onboarding")
    process = create("process", "Onboard customer")

    for rel, source, target in (
        ("drives", goal, requirement),
        ("needs", requirement, capability),
        ("has_process", capability, process),
    ):
        response = test_client.post(
            f"/api/workspaces/{workspace_id}/enterprise/links",
            json={
                "state_id": candidate["id"],
                "relationship_type": rel,
                "source_object_id": source,
                "target_object_id": target,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

    chain = test_client.get(
        f"{base}/trace",
        params={
            "state_id": candidate["id"],
            "object_id": goal,
            "direction": "outgoing",
            "depth": 3,
        },
    ).json()
    names = {node["name"] for node in chain["nodes"]}
    expected = {"Grow revenue", "Offer self-service", "Customer onboarding", "Onboard customer"}
    assert expected <= names
    assert chain["depths"][goal] == 0
    assert chain["depths"][process] == 3

    usages = test_client.get(
        f"{base}/objects/{goal}/usages", params={"state_id": candidate["id"]}
    ).json()
    assert any(n["relationship_type"] == "drives" for n in usages["outgoing"])


def test_solution_derived_edges_in_graph(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers, ["solution"])
    workspace_id = workspace["id"]
    base = _trace_url(workspace_id)

    design = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions",
        json={"state_id": candidate["id"], "name": "Payments"},
        headers=headers,
    ).json()
    solution_id = design["solution"]["solution_object_id"]

    design = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions/{solution_id}/components",
        json={
            "state_id": candidate["id"],
            "name": "Payment service",
            "position": {"x": 40, "y": 40},
        },
        headers=headers,
    ).json()
    component_id = design["components"][0]["object_id"]

    design = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/components/{component_id}/interfaces",
        json={"state_id": candidate["id"], "name": "Payments API", "direction": "provided"},
        headers=headers,
    ).json()
    interface_id = next(
        i for c in design["components"] for i in c["interfaces"] if i["name"] == "Payments API"
    )["object_id"]

    design = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/interfaces/{interface_id}/operations",
        json={"state_id": candidate["id"], "name": "ChargeCard", "operation_kind": "command"},
        headers=headers,
    ).json()
    operation_id = next(
        o
        for c in design["components"]
        for i in c["interfaces"]
        for o in i["operations"]
        if o["name"] == "ChargeCard"
    )["object_id"]

    graph = test_client.get(
        f"{base}/architecture-graph", params={"state_id": candidate["id"]}
    ).json()
    edges = {
        (edge["source_object_id"], edge["target_object_id"], edge["relationship_type"])
        for edge in graph["edges"]
    }
    assert (solution_id, component_id, "contains_component") in edges
    assert (component_id, interface_id, "provides") in edges
    assert (interface_id, operation_id, "has_operation") in edges


def test_usages_unknown_object_returns_404(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers, ["information"])
    response = test_client.get(
        f"{_trace_url(workspace['id'])}/objects/{uuid4()}/usages",
        params={"state_id": current["id"]},
    )
    assert response.status_code == 404
