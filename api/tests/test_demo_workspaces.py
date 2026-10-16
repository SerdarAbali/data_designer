"""Focused tests for the deterministic demo workspace generator."""

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
    ArchitectureState,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
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
        tenant = Tenant(name=f"demo-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="demo@example.test",
                password_hash=hash_password("demo-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "demo@example.test", "password": "demo-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def create_workspace(test_client, headers, name, disciplines, demo_preset=None):
    body = {"name": name, "disciplines": disciplines}
    if demo_preset is not None:
        body["demo_preset"] = demo_preset
    response = test_client.post("/api/workspaces", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def workspace_id(test_client, name) -> str:
    for workspace in test_client.get("/api/workspaces").json():
        if workspace["name"] == name:
            return workspace["id"]
    raise AssertionError(f"workspace {name} not found")


def candidate_state(test_client, workspace) -> str:
    states = test_client.get(f"/api/workspaces/{workspace}/states").json()
    return next(state for state in states if state["state_type"] == "candidate")["id"]


def current_state(test_client, workspace) -> str:
    states = test_client.get(f"/api/workspaces/{workspace}/states").json()
    return next(state for state in states if state["state_type"] == "current")["id"]


FULL = ["enterprise", "information", "solution", "integration"]
SOLUTION_INTEGRATION = ["solution", "integration"]
INTEGRATION_ONLY = ["integration"]


def test_blank_workspace_creates_no_demo_content(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "Blank", FULL)
    assert workspace["demo_preset"] is None
    assert workspace["systems_count"] == 0
    assert workspace["contracts_count"] == 0
    assert workspace["scenarios_count"] == 0
    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    # A blank workspace only gets the lazily-initialised, empty Current state.
    assert [state["state_type"] for state in states] == ["current"]
    assert states[0]["nodes"] == []
    assert states[0]["relationships"] == []


def test_full_architecture_creates_all_four_modules(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "Full", FULL, demo_preset="full")
    assert workspace["demo_preset"] == "full"
    assert workspace["demo_version"]
    assert workspace["demo_generated_at"]
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)

    enterprise = test_client.get(
        f"/api/workspaces/{workspace_id_}/enterprise/model", params={"state_id": candidate}
    ).json()
    assert enterprise["goals"] and enterprise["requirements"] and enterprise["capabilities"]
    assert enterprise["processes"] and enterprise["principles"]

    information = test_client.get(
        f"/api/workspaces/{workspace_id_}/information/model", params={"state_id": candidate}
    ).json()
    entity = next(item for item in information["entities"] if item["name"] == "Customer")
    assert {attribute["name"] for attribute in entity["attributes"]} >= {
        "customer_id",
        "email",
        "consent",
    }
    assert any(attribute["realization"] for attribute in entity["attributes"])
    assert len(information["relationships"]) >= 1

    solutions = test_client.get(
        f"/api/workspaces/{workspace_id_}/solution/solutions", params={"state_id": candidate}
    ).json()
    assert len(solutions) == 1
    design = test_client.get(
        f"/api/workspaces/{workspace_id_}/solution/solutions/{solutions[0]['object_id']}/design",
        params={"state_id": candidate},
    ).json()
    assert design["components"]
    assert any(
        interface["direction"] == "provided"
        for component in design["components"]
        for interface in component["interfaces"]
    )

    landscape = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/landscape",
        params={"state_id": candidate},
    ).json()
    assert len(landscape["contracts"]) == 3
    assert landscape["interfaces"]


def test_solution_integration_omits_enterprise_and_information(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(
        test_client,
        headers,
        "Solution Integration",
        SOLUTION_INTEGRATION,
        demo_preset="solution_integration",
    )
    workspace_id_ = workspace["id"]
    assert workspace["disciplines"] == SOLUTION_INTEGRATION
    candidate = candidate_state(test_client, workspace_id_)

    assert (
        test_client.get(
            f"/api/workspaces/{workspace_id_}/enterprise/model", params={"state_id": candidate}
        ).status_code
        == 404
    )
    assert (
        test_client.get(
            f"/api/workspaces/{workspace_id_}/information/model", params={"state_id": candidate}
        ).status_code
        == 404
    )

    design = test_client.get(
        f"/api/workspaces/{workspace_id_}/solution/solutions", params={"state_id": candidate}
    ).json()
    assert len(design) == 1
    landscape = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/landscape",
        params={"state_id": candidate},
    ).json()
    assert landscape["contracts"]
    with sessions() as db:
        assert db.scalar(select(func.count(CatalogSystem.id))) == 3


def test_integration_only_omits_enterprise_information_solution(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(
        test_client,
        headers,
        "Integration Only",
        INTEGRATION_ONLY,
        demo_preset="integration_only",
    )
    workspace_id_ = workspace["id"]
    assert workspace["disciplines"] == INTEGRATION_ONLY
    candidate = candidate_state(test_client, workspace_id_)

    assert (
        test_client.get(
            f"/api/workspaces/{workspace_id_}/enterprise/model", params={"state_id": candidate}
        ).status_code
        == 404
    )
    assert (
        test_client.get(
            f"/api/workspaces/{workspace_id_}/information/model", params={"state_id": candidate}
        ).status_code
        == 404
    )
    assert (
        test_client.get(
            f"/api/workspaces/{workspace_id_}/solution/solutions", params={"state_id": candidate}
        ).status_code
        == 404
    )

    landscape = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/landscape",
        params={"state_id": candidate},
    ).json()
    assert len(landscape["contracts"]) == 3
    with sessions() as db:
        assert db.scalar(select(func.count(CatalogSystem.id))) == 3
        assert db.scalar(select(func.count(Integration.id))) == 3


def test_shared_catalog_systems_are_not_duplicated(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    create_workspace(test_client, headers, "Dedup", FULL, demo_preset="full")
    with sessions() as db:
        names = list(db.scalars(select(CatalogSystem.name)))
        assert sorted(names) == ["Billing", "CRM", "Integration Runtime"]
        assert db.scalar(select(func.count(CatalogObject.id))) == 4
        assert db.scalar(select(func.count(CatalogField.id))) == 19


def test_current_and_candidate_contain_different_states(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "States", FULL, demo_preset="full")
    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    current = next(state for state in states if state["state_type"] == "current")
    candidate = next(state for state in states if state["state_type"] == "candidate")
    assert 0 < len(current["nodes"]) < len(candidate["nodes"])
    assert current["relationships"] and candidate["relationships"]


def test_contracts_and_mappings_reference_generated_catalog(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "Refs", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    landscape = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/landscape",
        params={"state_id": candidate},
    ).json()
    direct = next(
        item for item in landscape["contracts"] if item["name"] == "Customer onboarding (direct)"
    )
    assert direct["target_fields_mapped"] > 0
    with sessions() as db:
        field_ids = set(db.scalars(select(CatalogField.id)))
        object_ids = set(db.scalars(select(CatalogObject.id)))
        contract = db.get(Integration, UUID(direct["id"]))
        assert contract.source_object_id in object_ids
        assert contract.target_object_id in object_ids
        refs = list(
            db.scalars(
                select(IntegrationFieldRef).where(IntegrationFieldRef.integration_id == contract.id)
            )
        )
        assert refs
        for ref in refs:
            assert ref.field_id in field_ids
        for graph in (contract.graph, contract.response_graph, contract.error_response_graph):
            for edge in graph["edges"]:
                for port in (edge["sourcePortId"], edge["targetPortId"]):
                    if port.startswith("field:"):
                        assert UUID(port.removeprefix("field:")) in field_ids


def test_success_test_passes_through_existing_engine(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "Engine", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    landscape = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/landscape",
        params={"state_id": candidate},
    ).json()
    direct = next(
        item for item in landscape["contracts"] if item["name"] == "Customer onboarding (direct)"
    )
    with sessions() as db:
        revision = db.get(Integration, UUID(direct["id"])).revision
    result = test_client.post(
        f"/api/integrations/{direct['id']}/dry-run",
        json={"expected_revision": revision},
        headers=headers,
    )
    assert result.status_code == 200, result.text
    summary = result.json()["summary"]
    assert summary["failed"] == 0
    assert summary["ok"] == summary["total"] >= 1


def test_error_scenario_and_intentional_failure(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "Scenarios", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    landscape = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/landscape",
        params={"state_id": candidate},
    ).json()
    direct = next(
        item for item in landscape["contracts"] if item["name"] == "Customer onboarding (direct)"
    )
    conformance = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/contracts/{direct['id']}/conformance",
        params={"state_id": candidate},
    ).json()
    by_name = {scenario["name"]: scenario for scenario in conformance["scenarios"]}
    assert by_name["Onboarding happy path"]["status"] == "passing"
    assert by_name["Onboarding error response"]["status"] == "passing"
    assert by_name["Demo: unresolved name review (demo content)"]["status"] == "failing"
    assert conformance["summary"]["failing"] >= 1


def test_rerunning_generation_creates_no_duplicates(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "Idempotent", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]

    def counts():
        with sessions() as db:
            return (
                db.scalar(select(func.count(CatalogSystem.id))),
                db.scalar(select(func.count(CatalogObject.id))),
                db.scalar(select(func.count(CatalogField.id))),
                db.scalar(select(func.count(Integration.id))),
                db.scalar(select(func.count(Scenario.id))),
                db.scalar(select(func.count(ArchitectureState.id))),
            )

    before = counts()
    assert (
        test_client.post(f"/api/workspaces/{workspace_id_}/demo/reset", headers=headers).status_code
        == 200
    )
    assert (
        test_client.post(f"/api/workspaces/{workspace_id_}/demo/reset", headers=headers).status_code
        == 200
    )
    assert counts() == before


def test_reset_only_removes_generated_content(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "Reset", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]

    # A user-created system inside the demo workspace must survive a reset.
    user_system = test_client.post(
        "/api/catalog/systems",
        json={"name": "User System", "kind": "application"},
        headers=headers,
    )
    assert user_system.status_code == 201, user_system.text
    user_system_id = user_system.json()["id"]

    response = test_client.post(f"/api/workspaces/{workspace_id_}/demo/reset", headers=headers)
    assert response.status_code == 200, response.text
    with sessions() as db:
        assert db.get(CatalogSystem, UUID(user_system_id)) is not None
        assert db.scalar(select(func.count(CatalogSystem.id))) == 4


def test_reset_preserves_discipline_settings(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(
        test_client,
        headers,
        "Disciplines",
        SOLUTION_INTEGRATION,
        demo_preset="solution_integration",
    )
    workspace_id_ = workspace["id"]
    response = test_client.post(f"/api/workspaces/{workspace_id_}/demo/reset", headers=headers)
    assert response.status_code == 200
    assert response.json()["disciplines"] == SOLUTION_INTEGRATION
