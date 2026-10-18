from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    CatalogField,
    CatalogObject,
    InformationAttribute,
    Integration,
    IntegrationFieldRef,
    Tenant,
    User,
)
from tests.baseline_support import lock_baseline


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
        tenant = Tenant(name=f"ws-info-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="info@example.test",
                password_hash=hash_password("info-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "info@example.test", "password": "info-test-password"},
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
        json={"name": "Information Workspace", "disciplines": ["information"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _create_entity(test_client, headers, workspace_id, state_id, name, position):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities",
        json={"state_id": state_id, "name": name, "position": position},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_information_modeler_entity_attribute_relationship_flow(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    customer = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 80, "y": 80}
    )
    order = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Order", {"x": 420, "y": 80}
    )
    customer_id = customer["entity"]["object_id"]
    order_id = order["entity"]["object_id"]

    attribute = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities/{customer_id}/attributes",
        json={
            "state_id": candidate["id"],
            "name": "customer_id",
            "data_type": "uuid",
            "required": True,
            "nullable": False,
            "is_identifier": True,
        },
        headers=headers,
    )
    assert attribute.status_code == 201, attribute.text
    assert attribute.json()["is_identifier"] is True
    assert attribute.json()["required"] is True

    relationship = test_client.post(
        f"/api/workspaces/{workspace_id}/information/relationships",
        json={
            "state_id": candidate["id"],
            "source_object_id": customer_id,
            "target_object_id": order_id,
            "cardinality": "one_to_many",
        },
        headers=headers,
    )
    assert relationship.status_code == 201, relationship.text
    relationship_id = relationship.json()["id"]

    model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": candidate["id"]},
    ).json()
    assert model["editable"] is True
    assert {entity["name"] for entity in model["entities"]} == {"Customer", "Order"}
    customer_view = next(e for e in model["entities"] if e["name"] == "Customer")
    assert [a["name"] for a in customer_view["attributes"]] == ["customer_id"]
    assert customer_view["attributes"][0]["realization"] is None
    assert len(model["relationships"]) == 1
    assert model["relationships"][0]["cardinality"] == "one_to_many"
    assert model["relationships"][0]["source_object_id"] == customer_id

    updated = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        json={"cardinality": "many_to_many", "name": "places"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["cardinality"] == "many_to_many"

    # Current state is untouched by candidate work.
    lock_baseline(test_client, workspace_id, current["id"], headers)
    current_model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": current["id"]},
    ).json()
    assert current_model["editable"] is False
    assert current_model["entities"] == []
    assert current_model["relationships"] == []

    assert (
        test_client.delete(
            f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
            params={"state_id": candidate["id"]},
            headers=headers,
        ).status_code
        == 204
    )
    assert (
        test_client.delete(
            f"/api/workspaces/{workspace_id}/information/attributes/"
            f"{customer_view['attributes'][0]['object_id']}",
            params={"state_id": candidate["id"]},
            headers=headers,
        ).status_code
        == 204
    )
    model_after = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": candidate["id"]},
    ).json()
    assert model_after["relationships"] == []
    assert all(not entity["attributes"] for entity in model_after["entities"])


def test_information_realization_reuses_existing_catalog_field(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "CRM", "kind": "service"},
        headers=headers,
    ).json()
    catalog_object = test_client.post(
        f"/api/catalog/systems/{system['id']}/objects",
        json={"name": "customer", "label": "Customer"},
        headers=headers,
    ).json()
    field = test_client.post(
        f"/api/catalog/objects/{catalog_object['id']}/fields",
        json={"name": "email", "data_type": "string"},
        headers=headers,
    ).json()

    entity = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 60, "y": 60}
    )
    entity_id = entity["entity"]["object_id"]
    attribute = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities/{entity_id}/attributes",
        json={"state_id": candidate["id"], "name": "email", "data_type": "string"},
        headers=headers,
    ).json()

    realization = test_client.put(
        f"/api/workspaces/{workspace_id}/information/attributes/"
        f"{attribute['object_id']}/realization",
        json={
            "state_id": candidate["id"],
            "catalog_field_id": field["id"],
            "catalog_object_id": catalog_object["id"],
        },
        headers=headers,
    )
    assert realization.status_code == 200, realization.text
    assert realization.json()["catalog_field_id"] == field["id"]
    assert realization.json()["catalog_field_name"] == "email"
    assert realization.json()["catalog_object_name"] == "customer"

    # Idempotent re-realization does not create duplicates.
    test_client.put(
        f"/api/workspaces/{workspace_id}/information/attributes/"
        f"{attribute['object_id']}/realization",
        json={"state_id": candidate["id"], "catalog_field_id": field["id"]},
        headers=headers,
    )

    model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": candidate["id"]},
    ).json()
    entity_view = next(e for e in model["entities"] if e["name"] == "Customer")
    assert entity_view["attributes"][0]["realization"]["catalog_field_id"] == field["id"]

    with testing_sessions() as db:
        field_count = len(list(db.scalars(select(CatalogField))))
        object_count = len(list(db.scalars(select(CatalogObject))))
        field_refs = list(
            db.scalars(
                select(ArchitectureObject).where(
                    ArchitectureObject.kind == "catalog_field_ref"
                )
            )
        )
    assert field_count == 1
    assert object_count == 1
    assert len(field_refs) == 1

    # Clearing the mapping removes the edge but keeps the referenced field.
    cleared = test_client.put(
        f"/api/workspaces/{workspace_id}/information/attributes/"
        f"{attribute['object_id']}/realization",
        json={"state_id": candidate["id"], "catalog_field_id": None},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["catalog_field_id"] is None
    with testing_sessions() as db:
        assert len(list(db.scalars(select(CatalogField)))) == 1


def test_candidate_edits_of_current_attribute_use_overrides(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    entity = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Account", {"x": 40, "y": 40}
    )
    entity_id = entity["entity"]["object_id"]
    attribute = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities/{entity_id}/attributes",
        json={"state_id": candidate["id"], "name": "balance", "data_type": "decimal"},
        headers=headers,
    ).json()
    attribute_id = attribute["object_id"]

    # Promote the entity + attribute into Current (simulating a committed baseline).
    with testing_sessions.begin() as db:
        current_row = db.get(ArchitectureState, UUID(current["id"]))
        current_row.nodes = [
            *current_row.nodes,
            {
                "occurrence_id": f"occ-{uuid4()}",
                "object_id": entity_id,
                "position": {"x": 40, "y": 40},
                "discipline": "information",
            },
        ]
        record = db.get(InformationAttribute, UUID(attribute_id))
        record.created_in_state_id = None

    renamed = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/attributes/{attribute_id}",
        json={"state_id": candidate["id"], "name": "current_balance"},
        headers=headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "current_balance"

    candidate_model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": candidate["id"]},
    ).json()
    candidate_attr = next(
        e for e in candidate_model["entities"] if e["object_id"] == entity_id
    )["attributes"][0]
    assert candidate_attr["name"] == "current_balance"

    current_model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": current["id"]},
    ).json()
    current_attr = next(
        e for e in current_model["entities"] if e["object_id"] == entity_id
    )["attributes"][0]
    assert current_attr["name"] == "balance"


def test_information_endpoints_require_enabled_discipline(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": "Integration Only", "disciplines": ["integration"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    response = test_client.get(
        f"/api/workspaces/{workspace['id']}/information/model",
        params={"state_id": current["id"]},
    )
    assert response.status_code == 404


def test_candidate_relationships_cannot_mutate_current_baseline(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    source = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 0, "y": 0}
    )
    target = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Order", {"x": 300, "y": 0}
    )
    source_id = source["entity"]["object_id"]
    target_id = target["entity"]["object_id"]

    relationship = test_client.post(
        f"/api/workspaces/{workspace_id}/information/relationships",
        json={
            "state_id": candidate["id"],
            "source_object_id": source_id,
            "target_object_id": target_id,
            "cardinality": "one_to_many",
        },
        headers=headers,
    ).json()
    relationship_id = relationship["id"]

    # Promote the relationship to a committed canonical baseline edge (created_in_state_id=None).
    with testing_sessions.begin() as db:
        edge = db.get(ArchitectureRelationship, UUID(relationship_id))
        edge.created_in_state_id = None

    blocked_edit = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        json={"cardinality": "many_to_many"},
        headers=headers,
    )
    assert blocked_edit.status_code == 409, blocked_edit.text

    blocked_delete = test_client.delete(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        headers=headers,
    )
    assert blocked_delete.status_code == 409, blocked_delete.text

    # Current is read-only, so even the matching state id is rejected.
    current_edit = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": current["id"]},
        json={"cardinality": "many_to_many"},
        headers=headers,
    )
    assert current_edit.status_code == 409, current_edit.text

    # The canonical baseline edge is untouched.
    with testing_sessions() as db:
        edge = db.get(ArchitectureRelationship, UUID(relationship_id))
        assert edge is not None
        assert (edge.properties or {}).get("cardinality") == "one_to_many"


def test_relationship_handles_persist_reconnect_and_reset(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    customer = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 0, "y": 0}
    )
    order = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Order", {"x": 300, "y": 0}
    )
    invoice = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Invoice", {"x": 600, "y": 0}
    )
    source_id = customer["entity"]["object_id"]
    target_id = order["entity"]["object_id"]
    third_id = invoice["entity"]["object_id"]

    created = test_client.post(
        f"/api/workspaces/{workspace_id}/information/relationships",
        json={
            "state_id": candidate["id"],
            "source_object_id": source_id,
            "target_object_id": target_id,
            "cardinality": "one_to_many",
            "source_handle": "s-top",
            "target_handle": "t-top",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    relationship_id = created.json()["id"]
    assert created.json()["source_handle"] == "s-top"
    assert created.json()["target_handle"] == "t-top"

    # Reload preserves the manually selected handles.
    model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": candidate["id"]},
    ).json()
    relationship = next(r for r in model["relationships"] if r["id"] == relationship_id)
    assert relationship["source_handle"] == "s-top"
    assert relationship["target_handle"] == "t-top"

    # A different manual selection (bottom -> left) is preserved too.
    updated = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        json={"source_handle": "s-bottom", "target_handle": "t-left"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["source_handle"] == "s-bottom"
    assert updated.json()["target_handle"] == "t-left"

    # Reconnection may also move an endpoint onto another entity handle.
    reconnected = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        json={"target_object_id": third_id, "target_handle": "t-right"},
        headers=headers,
    )
    assert reconnected.status_code == 200, reconnected.text
    assert reconnected.json()["target_object_id"] == third_id
    assert reconnected.json()["target_handle"] == "t-right"

    # Reset to automatic routing clears the stored manual handles.
    reset = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        json={"source_handle": None, "target_handle": None},
        headers=headers,
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["source_handle"] is None
    assert reset.json()["target_handle"] is None

    model_after = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": candidate["id"]},
    ).json()
    relationship_after = next(
        r for r in model_after["relationships"] if r["id"] == relationship_id
    )
    assert relationship_after["source_handle"] is None
    assert relationship_after["target_handle"] is None


def test_candidate_relationship_handle_changes_do_not_affect_current(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    source = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 0, "y": 0}
    )
    target = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Order", {"x": 300, "y": 0}
    )
    source_id = source["entity"]["object_id"]
    target_id = target["entity"]["object_id"]

    created = test_client.post(
        f"/api/workspaces/{workspace_id}/information/relationships",
        json={
            "state_id": candidate["id"],
            "source_object_id": source_id,
            "target_object_id": target_id,
            "cardinality": "one_to_many",
            "source_handle": "s-top",
            "target_handle": "t-top",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    relationship_id = created.json()["id"]

    # The candidate relationship (and its handles) never leak into Current.
    current_model = test_client.get(
        f"/api/workspaces/{workspace_id}/information/model",
        params={"state_id": current["id"]},
    ).json()
    assert current_model["entities"] == []
    assert current_model["relationships"] == []

    # Manual handle changes in the candidate persist for that state.
    changed = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        json={"source_handle": "s-bottom", "target_handle": "t-left"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["source_handle"] == "s-bottom"

    # Promote the edge to a committed baseline; candidate edits are rejected.
    with testing_sessions.begin() as db:
        edge = db.get(ArchitectureRelationship, UUID(relationship_id))
        edge.created_in_state_id = None

    blocked = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/relationships/{relationship_id}",
        params={"state_id": candidate["id"]},
        json={"source_handle": "s-right", "target_handle": "t-right"},
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text

    with testing_sessions() as db:
        edge = db.get(ArchitectureRelationship, UUID(relationship_id))
        assert (edge.properties or {}).get("source_handle") == "s-bottom"
        assert (edge.properties or {}).get("target_handle") == "t-left"


# --- Information Architecture completion projections -------------------------


def _catalog_field(
    test_client,
    headers,
    system_name="CRM",
    object_name="customer",
    field_name="email",
    data_type="string",
):
    system = test_client.post(
        "/api/catalog/systems", json={"name": system_name, "kind": "service"}, headers=headers
    ).json()
    catalog_object = test_client.post(
        f"/api/catalog/systems/{system['id']}/objects",
        json={"name": object_name, "label": object_name.title()},
        headers=headers,
    ).json()
    field = test_client.post(
        f"/api/catalog/objects/{catalog_object['id']}/fields",
        json={"name": field_name, "data_type": data_type},
        headers=headers,
    ).json()
    return system, catalog_object, field


def _add_attribute(
    test_client, headers, workspace_id, state_id, entity_id, name, data_type="string", **extra
):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/information/entities/{entity_id}/attributes",
        json={"state_id": state_id, "name": name, "data_type": data_type, **extra},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _realize(test_client, headers, workspace_id, state_id, attribute_id, field_id):
    response = test_client.put(
        f"/api/workspaces/{workspace_id}/information/attributes/{attribute_id}/realization",
        json={"state_id": state_id, "catalog_field_id": field_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_conceptual_projection_hides_technical_detail(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    customer = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 40, "y": 40}
    )
    order = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Order", {"x": 380, "y": 40}
    )
    customer_id = customer["entity"]["object_id"]
    order_id = order["entity"]["object_id"]
    _add_attribute(test_client, headers, workspace_id, candidate["id"], customer_id, "customer_id")
    test_client.post(
        f"/api/workspaces/{workspace_id}/information/relationships",
        json={
            "state_id": candidate["id"],
            "source_object_id": customer_id,
            "target_object_id": order_id,
            "cardinality": "one_to_many",
            "name": "places",
        },
        headers=headers,
    )

    conceptual = test_client.get(
        f"/api/workspaces/{workspace_id}/information/conceptual",
        params={"state_id": candidate["id"]},
    ).json()
    assert {concept["name"] for concept in conceptual["concepts"]} == {"Customer", "Order"}
    for concept in conceptual["concepts"]:
        assert set(concept) == {"object_id", "name", "description", "owner"}
        assert "attributes" not in concept
        assert "data_type" not in concept
    assert len(conceptual["relationships"]) == 1
    relationship = conceptual["relationships"][0]
    assert set(relationship) == {
        "id",
        "source_object_id",
        "target_object_id",
        "name",
        "cardinality",
    }
    assert relationship["cardinality"] == "one_to_many"


def test_physical_projection_reuses_catalog_field_ids(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    system, catalog_object, email_field = _catalog_field(
        test_client, headers, system_name="CRM", object_name="customer", field_name="email"
    )
    integer_field = test_client.post(
        f"/api/catalog/objects/{catalog_object['id']}/fields",
        json={"name": "balance", "data_type": "integer"},
        headers=headers,
    ).json()

    entity = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 40, "y": 40}
    )
    entity_id = entity["entity"]["object_id"]
    email = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "email"
    )
    balance = _add_attribute(
        test_client,
        headers,
        workspace_id,
        candidate["id"],
        entity_id,
        "balance",
        data_type="decimal",
    )
    _add_attribute(test_client, headers, workspace_id, candidate["id"], entity_id, "phone")

    _realize(
        test_client, headers, workspace_id, candidate["id"], email["object_id"], email_field["id"]
    )
    _realize(
        test_client,
        headers,
        workspace_id,
        candidate["id"],
        balance["object_id"],
        integer_field["id"],
    )

    physical = test_client.get(
        f"/api/workspaces/{workspace_id}/information/physical",
        params={"state_id": candidate["id"]},
    ).json()
    by_name = {mapping["attribute_name"]: mapping for mapping in physical["mappings"]}

    # Existing catalog ids are reused verbatim; nothing is copied or duplicated.
    assert by_name["email"]["catalog_field_id"] == email_field["id"]
    assert by_name["email"]["catalog_object_id"] == email_field["object_id"]
    assert by_name["email"]["system_id"] == system["id"]
    assert by_name["email"]["system_name"] == "CRM"
    assert by_name["email"]["status"] == "realized"
    assert by_name["balance"]["status"] == "partial"
    assert by_name["phone"]["status"] == "unmapped"
    assert by_name["phone"]["catalog_field_id"] is None
    assert physical["summary"] == {"realized": 1, "partial": 1, "unmapped": 1, "invalid": 0}

    with testing_sessions() as db:
        assert len(list(db.scalars(select(CatalogField)))) == 2
        assert len(list(db.scalars(select(CatalogObject)))) == 1

    # A realization that points at a removed catalog field is reported invalid,
    # not silently dropped.
    with testing_sessions.begin() as db:
        field = db.get(CatalogField, UUID(email_field["id"]))
        field.deleted_at = datetime.now(UTC)
    invalidated = test_client.get(
        f"/api/workspaces/{workspace_id}/information/physical",
        params={"state_id": candidate["id"]},
    ).json()
    invalid_by_name = {mapping["attribute_name"]: mapping for mapping in invalidated["mappings"]}
    assert invalid_by_name["email"]["status"] == "invalid"
    assert invalidated["summary"]["invalid"] == 1


def test_ownership_projection_reports_missing_governance(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    system = test_client.post(
        "/api/catalog/systems", json={"name": "CRM", "kind": "service"}, headers=headers
    ).json()

    governed = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Governed", {"x": 40, "y": 40}
    )
    test_client.patch(
        f"/api/workspaces/{workspace_id}/information/entities/{governed['entity']['object_id']}",
        json={
            "owner": "Customer Ops",
            "steward": "Data Steward",
            "authoritative_system_id": system["id"],
            "classification": "internal",
            "sensitivity": "low",
        },
        headers=headers,
    )
    _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Ungoverned", {"x": 340, "y": 40}
    )
    sensitive = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Sensitive", {"x": 640, "y": 40}
    )
    test_client.patch(
        f"/api/workspaces/{workspace_id}/information/entities/{sensitive['entity']['object_id']}",
        json={"owner": "Risk", "sensitivity": "high"},
        headers=headers,
    )

    # Place CRM on the candidate canvas so the authority resolves as present.
    with testing_sessions.begin() as db:
        state = db.get(ArchitectureState, UUID(candidate["id"]))
        state.nodes = [
            *state.nodes,
            {
                "occurrence_id": f"occ-{system['id']}",
                "object_id": system["id"],
                "position": {"x": 0, "y": 0},
                "discipline": "information",
            },
        ]

    ownership = test_client.get(
        f"/api/workspaces/{workspace_id}/information/ownership",
        params={"state_id": candidate["id"]},
    ).json()
    by_name = {entry["name"]: entry for entry in ownership["entries"]}

    assert by_name["Governed"]["issues"] == []
    assert by_name["Governed"]["authoritative_in_state"] is True
    assert by_name["Governed"]["authoritative_system_name"] == "CRM"

    assert {"missing_owner", "missing_steward", "missing_authoritative_system"} <= set(
        by_name["Ungoverned"]["issues"]
    )
    assert "sensitive_without_ownership" in by_name["Sensitive"]["issues"]
    assert "missing_steward" in by_name["Sensitive"]["issues"]


def test_lineage_projection_uses_existing_references_only(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    crm_system, crm_object, crm_email = _catalog_field(
        test_client,
        headers,
        system_name="CRM",
        object_name="customer",
        field_name="email",
    )
    crm_phone = test_client.post(
        f"/api/catalog/objects/{crm_object['id']}/fields",
        json={"name": "phone", "data_type": "string"},
        headers=headers,
    ).json()
    billing_system, billing_object, billing_email = _catalog_field(
        test_client,
        headers,
        system_name="Billing",
        object_name="billing_account",
        field_name="email_address",
    )

    entity = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 40, "y": 40}
    )
    entity_id = entity["entity"]["object_id"]
    email = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "email"
    )
    phone = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "phone"
    )
    _realize(
        test_client, headers, workspace_id, candidate["id"], email["object_id"], crm_email["id"]
    )
    _realize(
        test_client, headers, workspace_id, candidate["id"], phone["object_id"], crm_phone["id"]
    )

    contract_id = uuid4()
    graph = {
        "version": 1,
        "nodes": [
            {"id": "src", "type": "source", "position": {"x": 0, "y": 0}},
            {"id": "tgt", "type": "target", "position": {"x": 400, "y": 0}},
        ],
        "edges": [
            {
                "id": "e1",
                "sourceNodeId": "src",
                "sourcePortId": f"field:{crm_email['id']}",
                "targetNodeId": "tgt",
                "targetPortId": f"field:{billing_email['id']}",
            }
        ],
    }
    with testing_sessions.begin() as db:
        db.add(
            Integration(
                id=contract_id,
                tenant_id=UUID(workspace_id),
                source_system_id=UUID(crm_system["id"]),
                source_object_id=UUID(crm_object["id"]),
                target_system_id=UUID(billing_system["id"]),
                target_object_id=UUID(billing_object["id"]),
                name="Customer onboarding (direct)",
                graph=graph,
                response_graph={"version": 1, "nodes": [], "edges": []},
                error_response_graph={"version": 1, "nodes": [], "edges": []},
            )
        )
        db.add(
            IntegrationFieldRef(
                id=uuid4(),
                tenant_id=UUID(workspace_id),
                integration_id=contract_id,
                object_id=UUID(crm_object["id"]),
                field_id=UUID(crm_email["id"]),
                direction="source",
            )
        )
        db.add(
            IntegrationFieldRef(
                id=uuid4(),
                tenant_id=UUID(workspace_id),
                integration_id=contract_id,
                object_id=UUID(billing_object["id"]),
                field_id=UUID(billing_email["id"]),
                direction="target",
            )
        )

    lineage = test_client.get(
        f"/api/workspaces/{workspace_id}/information/lineage",
        params={"state_id": candidate["id"]},
    ).json()
    node_ids = {node["id"] for node in lineage["nodes"]}
    edges = {(edge["source"], edge["target"]): edge["relation"] for edge in lineage["edges"]}

    attribute_key = f"attribute:{email['object_id']}"
    crm_field_key = f"field:{crm_email['id']}"
    billing_field_key = f"field:{billing_email['id']}"
    contract_key = f"contract:{contract_id}"
    assert attribute_key in node_ids and crm_field_key in node_ids
    assert billing_field_key in node_ids and contract_key in node_ids
    assert edges[(attribute_key, crm_field_key)] == "realized as"
    assert edges[(crm_field_key, contract_key)] == "mapped by"
    assert edges[(contract_key, billing_field_key)] == "delivered to"

    # The phone attribute is realized but unused by any contract: lineage ends
    # there and nothing downstream is fabricated.
    phone_field_key = f"field:{crm_phone['id']}"
    assert phone_field_key in node_ids
    assert not any(
        source == phone_field_key and relation == "mapped by"
        for (source, _target), relation in edges.items()
    )

    # An attribute with no realization is reported as a lineage gap.
    unmapped = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "nickname"
    )
    lineage_after = test_client.get(
        f"/api/workspaces/{workspace_id}/information/lineage",
        params={"state_id": candidate["id"]},
    ).json()
    assert f"attribute:{unmapped['object_id']}" in {node["id"] for node in lineage_after["nodes"]}
    assert any("Customer.nickname" in gap for gap in lineage_after["gaps"])
    assert not any(
        edge["source"] == f"attribute:{unmapped['object_id']}" for edge in lineage_after["edges"]
    )


def test_impact_projection_reports_added_changed_removed_reused(client):
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace_with_candidate(test_client, headers)
    workspace_id = workspace["id"]

    _system, _object, field = _catalog_field(
        test_client, headers, system_name="CRM", object_name="customer", field_name="email"
    )

    entity = _create_entity(
        test_client, headers, workspace_id, candidate["id"], "Customer", {"x": 40, "y": 40}
    )
    entity_id = entity["entity"]["object_id"]
    stable = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "email"
    )
    changed = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "status"
    )
    removed = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "legacy_code"
    )

    # Promote the entity and three attributes into the Current baseline.
    with testing_sessions.begin() as db:
        current_row = db.get(ArchitectureState, UUID(current["id"]))
        current_row.nodes = [
            *current_row.nodes,
            {
                "occurrence_id": f"occ-{entity_id}",
                "object_id": entity_id,
                "position": {"x": 40, "y": 40},
                "discipline": "information",
            },
        ]
        for attribute_id in (stable["object_id"], changed["object_id"], removed["object_id"]):
            db.get(InformationAttribute, UUID(attribute_id)).created_in_state_id = None

    # Add a brand new attribute and realize it; rename a baseline attribute;
    # delete another baseline attribute (excluded in the candidate only).
    added = _add_attribute(
        test_client, headers, workspace_id, candidate["id"], entity_id, "consent"
    )
    _realize(
        test_client, headers, workspace_id, candidate["id"], added["object_id"], field["id"]
    )
    renamed = test_client.patch(
        f"/api/workspaces/{workspace_id}/information/attributes/{changed['object_id']}",
        json={"state_id": candidate["id"], "name": "status_code"},
        headers=headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert (
        test_client.delete(
            f"/api/workspaces/{workspace_id}/information/attributes/{removed['object_id']}",
            params={"state_id": candidate["id"]},
            headers=headers,
        ).status_code
        == 204
    )

    impact = test_client.get(
        f"/api/workspaces/{workspace_id}/information/impact",
        params={"state_id": candidate["id"]},
    ).json()
    assert impact["supported"] is True
    assert impact["baseline_state_id"] == current["id"]

    changes = {(change["object_type"], change["object_id"]): change for change in impact["changes"]}
    assert changes[("entity", entity_id)]["change"] == "reused"
    assert changes[("attribute", stable["object_id"])]["change"] == "reused"
    assert changes[("attribute", changed["object_id"])]["change"] == "changed"
    assert "name" in changes[("attribute", changed["object_id"])]["changed_fields"]
    assert changes[("attribute", added["object_id"])]["change"] == "added"
    assert changes[("attribute", removed["object_id"])]["change"] == "removed"
    assert changes[("realization", added["object_id"])]["change"] == "added"
    assert impact["summary"]["reused"] >= 2
    assert impact["summary"]["added"] >= 1
    assert impact["summary"]["removed"] >= 1
    assert impact["summary"]["changed"] >= 1

    # Candidate work never alters the Current baseline.
    current_impact = test_client.get(
        f"/api/workspaces/{workspace_id}/information/impact",
        params={"state_id": current["id"]},
    ).json()
    assert current_impact["baseline_state_id"] == current["id"]
    assert {change["change"] for change in current_impact["changes"]} <= {"reused"}
