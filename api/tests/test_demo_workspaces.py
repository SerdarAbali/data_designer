"""Focused tests for the deterministic demo workspace generator."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.architecture.schemas import EnterpriseObjectCreate, EnterpriseObjectResponse
from app.auth.security import hash_password
from app.db import Base, get_session
from app.demo.context import demo_uuid
from app.demo.information import INTENTIONAL_GAP_ATTRIBUTE
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
    # The seeded decomposition flows left to right: Portal -> Onboarding -> Connector.
    by_name = {component["name"]: component["position"] for component in design["components"]}
    flow = ("Customer Portal", "Onboarding Service", "Integration Connector")
    xs = [by_name[name]["x"] for name in flow]
    assert xs == sorted(xs)
    ys = {by_name[name]["y"] for name in flow}
    assert len(ys) == 1
    # Platform completion: deployment targets, trust boundaries and the links that
    # compose the solution flow are seeded for the Full Architecture demo.
    assert design["deployment_nodes"] and design["trust_boundaries"]
    link_types = {link["relationship_type"] for link in design["links"]}
    assert {"deployed_on", "contained_in", "crosses", "connects_to"} <= link_types
    # Every required interface is composed onto a provided interface so the
    # interaction sequence has real providers rather than a generic External.
    connects = [link for link in design["links"] if link["relationship_type"] == "connects_to"]
    provided_ids = {
        interface["object_id"]
        for component in design["components"]
        for interface in component["interfaces"]
        if interface["direction"] == "provided"
    }
    assert connects and {link["target_object_id"] for link in connects} <= provided_ids

    landscape = test_client.get(
        f"/api/workspaces/{workspace_id_}/integration-design/landscape",
        params={"state_id": candidate},
    ).json()
    assert len(landscape["contracts"]) == 3
    assert landscape["interfaces"]
    # The idempotency key is surfaced as a field name, never a raw UUID.
    contract = next(item for item in landscape["contracts"] if item["name"].endswith("(direct)"))
    assert contract["idempotency_key_field_name"] == "customer_id"
    assert (
        contract["idempotency_key_field_name"]
        != contract["specification"]["idempotency_key_field_id"]
    )


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


def test_full_demo_enterprise_trace_is_connected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "EntTrace", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    base = f"/api/workspaces/{workspace_id_}/enterprise"

    model = test_client.get(f"{base}/model", params={"state_id": candidate}).json()
    links = {
        (link["relationship_type"], link["source_object_id"], link["target_object_id"])
        for link in model["links"]
    }

    def find(items, name):
        return next(item for item in items if item["name"] == name)

    goal = find(model["goals"], "Reduce customer onboarding time")
    requirement = find(model["requirements"], "Capture verified customer details")
    capability = find(model["capabilities"], "Customer onboarding")
    process = find(model["processes"], "Customer onboarding")
    role = find(model["roles"], "Head of Customer Operations")
    solution = find(model["applications"], "Customer Onboarding")
    principle = find(model["principles"], "Consent before marketing")

    assert ("drives", goal["object_id"], requirement["object_id"]) in links
    assert ("needs", requirement["object_id"], capability["object_id"]) in links
    assert ("has_process", capability["object_id"], process["object_id"]) in links
    # Support is directed application -> process, as the model expects.
    assert ("supports", solution["object_id"], process["object_id"]) in links
    assert ("owned_by", capability["object_id"], role["object_id"]) in links
    assert ("governed_by", process["object_id"], principle["object_id"]) in links

    # 1. Strategy trace contains the full chain.
    trace = test_client.get(f"{base}/strategy-trace", params={"state_id": candidate}).json()
    assert trace["gaps"] == []
    chain = next(
        item
        for item in trace["chains"]
        if item["goal"]["name"] == "Reduce customer onboarding time"
    )
    step = chain["steps"][0]
    assert step["requirement"]["name"] == "Capture verified customer details"
    assert [item["name"] for item in step["capabilities"]] == ["Customer onboarding"]
    assert [item["name"] for item in step["processes"]] == ["Customer onboarding"]
    assert "Customer Onboarding" in [item["name"] for item in step["applications"]]

    # 2. Capability map reports a complete capability.
    capability_map = test_client.get(
        f"{base}/capability-map", params={"state_id": candidate}
    ).json()
    entry = next(
        item
        for item in capability_map["capabilities"]
        if item["capability"]["name"] == "Customer onboarding"
    )
    assert entry["processes"]
    assert entry["applications"]
    assert entry["owner_role"] and entry["owner_role"]["name"] == "Head of Customer Operations"

    # 3. Process impact shows the linked capability and supporting application.
    process_impact = test_client.get(
        f"{base}/process-impact", params={"state_id": candidate}
    ).json()
    impacted = next(
        item
        for item in process_impact["processes"]
        if item["process"]["name"] == "Customer onboarding"
    )
    assert [item["name"] for item in impacted["capabilities"]] == ["Customer onboarding"]
    assert {item["name"] for item in impacted["applications"]} >= {"Customer Onboarding"}

    # 4. Application support uses the corrected direction.
    application_support = test_client.get(
        f"{base}/application-support", params={"state_id": candidate}
    ).json()
    solution_entry = next(
        item for item in application_support["applications"]
        if item["application"]["name"] == "Customer Onboarding"
    )
    assert "Customer onboarding" in [item["name"] for item in solution_entry["processes"]]
    crm_entry = next(
        item for item in application_support["applications"] if item["application"]["name"] == "CRM"
    )
    assert "Customer onboarding" in [item["name"] for item in crm_entry["capabilities"]]

    # 5. Exactly one intentional risk remains, and there are no gaps.
    impact = test_client.get(f"{base}/impact", params={"state_id": candidate}).json()
    assert [item["name"] for item in impact["risks"]] == ["Legacy billing dependency"]
    assert impact["gaps"] == []


def test_full_demo_enterprise_generation_is_idempotent(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "EntIdempotent", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    base = f"/api/workspaces/{workspace_id_}/enterprise"

    def snapshot():
        state_id = candidate_state(test_client, workspace_id_)
        model = test_client.get(f"{base}/model", params={"state_id": state_id}).json()
        return (
            len(model["goals"]),
            len(model["requirements"]),
            len(model["capabilities"]),
            len(model["processes"]),
            len(model["principles"]),
            len(model["roles"]),
            len(model["applications"]),
            sorted(
                (link["relationship_type"], link["source_object_id"], link["target_object_id"])
                for link in model["links"]
            ),
        )

    before = snapshot()
    assert before[7], "expected enterprise relationships"
    for _ in range(2):
        assert (
            test_client.post(
                f"/api/workspaces/{workspace_id_}/demo/reset", headers=headers
            ).status_code
            == 200
        )
    assert snapshot() == before


def test_generated_enterprise_objects_validate_against_schemas(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "EntSchemas", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    model = test_client.get(
        f"/api/workspaces/{workspace_id_}/enterprise/model", params={"state_id": candidate}
    ).json()

    objects = (
        model["goals"]
        + model["requirements"]
        + model["capabilities"]
        + model["processes"]
        + model["principles"]
        + model["roles"]
    )
    assert objects
    for obj in objects:
        EnterpriseObjectResponse.model_validate(obj)
        EnterpriseObjectCreate(
            state_id=UUID(candidate),
            kind=obj["kind"],
            name=obj["name"],
            description=obj["description"],
            owner=obj["owner"],
            outcome_metric=obj["outcome_metric"],
            horizon=obj["horizon"],
            process_type=obj["process_type"],
            principle_type=obj["principle_type"],
            rationale=obj["rationale"],
            role_type=obj["role_type"],
        )


def test_demo_correction_leaves_other_workspaces_unchanged(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    other = create_workspace(test_client, headers, "Plain", FULL)
    other_id = other["id"]

    demo = create_workspace(test_client, headers, "DemoOnly", FULL, demo_preset="full")
    demo_candidate = candidate_state(test_client, demo["id"])
    assert test_client.get(
        f"/api/workspaces/{demo['id']}/enterprise/model", params={"state_id": demo_candidate}
    ).json()["goals"]

    other_state = current_state(test_client, other_id)
    other_model = test_client.get(
        f"/api/workspaces/{other_id}/enterprise/model", params={"state_id": other_state}
    ).json()
    assert other_model["goals"] == []
    assert other_model["capabilities"] == []


# --- Information module of the full demo -------------------------------------


def _information_projection(test_client, workspace_id_, state_id, projection):
    response = test_client.get(
        f"/api/workspaces/{workspace_id_}/information/{projection}",
        params={"state_id": state_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_full_demo_information_lineage_is_valid_and_not_fabricated(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "InfoLineage", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    tenant = UUID(workspace_id_)

    lineage = _information_projection(test_client, workspace_id_, candidate, "lineage")
    nodes = {node["id"]: node for node in lineage["nodes"]}
    relations = {(edge["source"], edge["target"]): edge["relation"] for edge in lineage["edges"]}

    email_attr = f"attribute:{demo_uuid(tenant, 'info.customer.email')}"
    crm_email = f"field:{demo_uuid(tenant, 'field.crm.customer.email')}"
    billing_email = f"field:{demo_uuid(tenant, 'field.billing.billing_account.email_address')}"
    direct = f"contract:{demo_uuid(tenant, 'integration.direct')}"
    event = f"contract:{demo_uuid(tenant, 'integration.event')}"
    runtime_payload = (
        f"field:{demo_uuid(tenant, 'field.integration_runtime.customer_event.payload')}"
    )

    # A proven end-to-end path: logical attribute -> source field -> contract ->
    # target field, all reusing canonical generated ids.
    assert relations[(email_attr, crm_email)] == "realized as"
    assert relations[(crm_email, direct)] == "mapped by"
    assert relations[(direct, billing_email)] == "delivered to"
    assert nodes[billing_email]["system_name"] == "Billing"
    assert relations[(crm_email, event)] == "mapped by"
    assert relations[(event, runtime_payload)] == "delivered to"
    assert nodes[runtime_payload]["system_name"] == "Integration Runtime"

    # The intentional gap is surfaced and nothing downstream is invented.
    gap_attr = f"attribute:{demo_uuid(tenant, f'info.customer.{INTENTIONAL_GAP_ATTRIBUTE}')}"
    assert gap_attr in nodes
    assert not any(source == gap_attr for source, _target in relations)
    assert any(INTENTIONAL_GAP_ATTRIBUTE in gap for gap in lineage["gaps"])


def test_full_demo_information_realization_reuses_catalog(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "InfoPhysical", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    tenant = UUID(workspace_id_)

    physical = _information_projection(test_client, workspace_id_, candidate, "physical")
    customer = {
        mapping["attribute_name"]: mapping
        for mapping in physical["mappings"]
        if mapping["entity_name"] == "Customer"
    }
    assert customer["email"]["status"] == "realized"
    assert customer["email"]["catalog_field_id"] == str(
        demo_uuid(tenant, "field.crm.customer.email")
    )
    assert customer["email"]["system_name"] == "CRM"
    assert {contract["name"] for contract in customer["email"]["contracts"]} >= {
        "Customer onboarding (direct)"
    }
    assert customer[INTENTIONAL_GAP_ATTRIBUTE]["status"] == "unmapped"
    assert customer[INTENTIONAL_GAP_ATTRIBUTE]["catalog_field_id"] is None

    # Realization reuses catalog rows; the demo never duplicates them.
    with sessions() as db:
        assert db.scalar(select(func.count(CatalogField.id))) == 19
        assert db.scalar(select(func.count(CatalogObject.id))) == 4


def test_full_demo_information_impact_diffs_current_and_candidate(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "InfoImpact", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    current = current_state(test_client, workspace_id_)
    candidate = candidate_state(test_client, workspace_id_)
    tenant = UUID(workspace_id_)

    current_model = _information_projection(test_client, workspace_id_, current, "model")
    customer = next(item for item in current_model["entities"] if item["name"] == "Customer")
    assert {attribute["name"] for attribute in customer["attributes"]} == {
        "customer_id",
        "first_name",
        "last_name",
    }
    assert all(attribute["realization"] for attribute in customer["attributes"])
    assert all(item["name"] != "Customer Consent" for item in current_model["entities"])

    impact = _information_projection(test_client, workspace_id_, candidate, "impact")
    assert impact["supported"] is True
    changes = {(change["object_type"], change["object_id"]): change for change in impact["changes"]}
    assert changes[("entity", str(demo_uuid(tenant, "info.customer")))]["change"] == "reused"
    assert changes[("entity", str(demo_uuid(tenant, "info.consent")))]["change"] == "added"
    assert (
        changes[("attribute", str(demo_uuid(tenant, "info.customer.customer_id")))]["change"]
        == "reused"
    )
    assert (
        changes[("attribute", str(demo_uuid(tenant, "info.customer.email")))]["change"] == "added"
    )


def test_full_demo_information_generation_is_idempotent(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "InfoIdem", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]

    def snapshot():
        candidate = candidate_state(test_client, workspace_id_)
        return {
            "model": _information_projection(test_client, workspace_id_, candidate, "model"),
            "lineage": _information_projection(test_client, workspace_id_, candidate, "lineage"),
            "physical": _information_projection(
                test_client, workspace_id_, candidate, "physical"
            ),
            "ownership": _information_projection(
                test_client, workspace_id_, candidate, "ownership"
            ),
        }

    first = snapshot()
    for _ in range(2):
        response = test_client.post(
            f"/api/workspaces/{workspace_id_}/demo/reset", headers=headers
        )
        assert response.status_code == 200, response.text
    assert snapshot() == first


def test_full_demo_integration_topology_and_sequence(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = create_workspace(test_client, headers, "IntTopology", FULL, demo_preset="full")
    workspace_id_ = workspace["id"]
    candidate = candidate_state(test_client, workspace_id_)
    design = f"/api/workspaces/{workspace_id_}/integration-design"

    landscape = test_client.get(
        f"{design}/landscape", params={"state_id": candidate}
    ).json()
    by_name = {item["name"]: item for item in landscape["contracts"]}
    direct = by_name["Customer onboarding (direct)"]
    event = by_name["Customer onboarding (event)"]

    # Direct integrations never route through a runtime; the event contract does.
    assert direct["target"]["is_runtime"] is False
    assert direct["source"]["is_runtime"] is False
    assert event["target"]["is_runtime"] is True
    assert event["target"]["system_kind"] == "middleware"
    assert event["target"]["system_name"] == "Integration Runtime"

    direct_flow = test_client.get(
        f"{design}/contracts/{direct['id']}/flow", params={"state_id": candidate}
    ).json()
    assert direct_flow["channel_kind"] == "api"
    assert direct_flow["channel_label"] == "API endpoint"
    request = next(phase for phase in direct_flow["phases"] if phase["phase"] == "request")
    assert any(item["role"] == "transformation" for item in request["transformations"])
    assert all(set(item["position"]) == {"x", "y"} for item in request["transformations"])

    event_flow = test_client.get(
        f"{design}/contracts/{event['id']}/flow", params={"state_id": candidate}
    ).json()
    assert event_flow["channel_kind"] == "event"
    assert event_flow["contract"]["target"]["is_runtime"] is True

    sequence = test_client.get(
        f"{design}/contracts/{direct['id']}/sequence", params={"state_id": candidate}
    ).json()
    scenarios = {item["name"]: item for item in sequence["scenarios"]}
    happy = scenarios["Onboarding happy path"]
    assert happy["status"] == "passing"
    assert {item["id"] for item in happy["participants"]} == {"crm", "billing"}
    contract_step = next(item for item in happy["interactions"] if item["contract_step"])
    assert contract_step["phase"] == "request"
    assert contract_step["from_id"] == "crm"
    assert contract_step["to_id"] == "billing"
    # The intentional demo failure is reported by the existing engine, not fabricated.
    unresolved = scenarios["Demo: unresolved name review (demo content)"]
    assert unresolved["status"] == "failing"
    assert unresolved["outdated"] is False
