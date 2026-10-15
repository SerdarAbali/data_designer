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
