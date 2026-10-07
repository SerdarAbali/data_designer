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
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
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
        tenant = Tenant(name=f"ws-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="ws@example.test",
                password_hash=hash_password("ws-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "ws@example.test", "password": "ws-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def test_list_and_create_workspaces(client) -> None:
    test_client, _ = client
    # Initial listing should show the default workspace
    workspaces = test_client.get("/api/workspaces").json()
    assert len(workspaces) >= 1
    assert workspaces[0]["is_active"] is True

    # Create a new workspace
    new_ws = test_client.post(
        "/api/workspaces",
        json={"name": "Production Architecture", "description": "Client live design"},
        headers=csrf_headers(test_client),
    )
    assert new_ws.status_code == 201
    created = new_ws.json()
    assert created["name"] == "Production Architecture"
    assert created["is_active"] is True

    # Check listing again
    workspaces = test_client.get("/api/workspaces").json()
    assert len(workspaces) >= 2
    active = [w for w in workspaces if w["is_active"]]
    assert len(active) == 1
    assert active[0]["name"] == "Production Architecture"


def test_switch_workspace_isolates_catalog(client) -> None:
    test_client, _ = client
    # Create system in current workspace
    headers = csrf_headers(test_client)
    res = test_client.post(
        "/api/catalog/systems",
        json={"name": "System In WS 1", "kind": "application"},
        headers=headers,
    )
    assert res.status_code == 201

    # Create and switch to WS 2
    ws2 = test_client.post(
        "/api/workspaces",
        json={"name": "Workspace 2"},
        headers=headers,
    ).json()

    # Catalog in WS 2 should be empty
    systems_ws2 = test_client.get("/api/catalog/systems").json()
    assert len(systems_ws2) == 0

    # Switch back to WS 1
    initial_ws_id = test_client.get("/api/workspaces").json()[0]["id"]
    test_client.post(
        f"/api/workspaces/{initial_ws_id}/switch",
        headers=headers,
    )

    # Catalog in WS 1 should contain System In WS 1
    systems_ws1 = test_client.get("/api/catalog/systems").json()
    assert len(systems_ws1) == 1
    assert systems_ws1[0]["name"] == "System In WS 1"


def test_fork_workspace_creates_independent_deep_copy(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)

    # Setup source system, object, field
    sys_res = test_client.post(
        "/api/catalog/systems",
        json={"name": "Core ERP", "kind": "erp"},
        headers=headers,
    ).json()
    obj_res = test_client.post(
        f"/api/catalog/systems/{sys_res['id']}/objects",
        json={"name": "Customer", "label": "Customer"},
        headers=headers,
    ).json()
    test_client.post(
        f"/api/catalog/objects/{obj_res['id']}/fields",
        json={"name": "email", "data_type": "string"},
        headers=headers,
    )

    current_ws_id = test_client.get("/api/workspaces").json()[0]["id"]

    # Fork workspace
    fork_res = test_client.post(
        f"/api/workspaces/{current_ws_id}/fork",
        json={"name": "ERP Sandbox"},
        headers=headers,
    )
    assert fork_res.status_code == 201
    forked = fork_res.json()
    assert forked["name"] == "ERP Sandbox"
    assert forked["is_active"] is True

    # Forked workspace has copied system with different ID
    forked_systems = test_client.get("/api/catalog/systems").json()
    assert len(forked_systems) == 1
    assert forked_systems[0]["name"] == "Core ERP"
    assert forked_systems[0]["id"] != sys_res["id"]


def test_export_and_import_workspace(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)

    # Setup a system
    test_client.post(
        "/api/catalog/systems",
        json={"name": "Exported System", "kind": "custom"},
        headers=headers,
    )

    current_ws_id = test_client.get("/api/workspaces").json()[0]["id"]

    # Export
    bundle = test_client.get(f"/api/workspaces/{current_ws_id}/export").json()
    assert bundle["format"] == "data-designer-workspace"
    assert len(bundle["systems"]) == 1

    # Import bundle
    bundle["workspace"]["name"] = "Imported Space"
    import_res = test_client.post(
        "/api/workspaces/import",
        json=bundle,
        headers=headers,
    )
    assert import_res.status_code == 201
    imported = import_res.json()
    assert imported["name"] == "Imported Space"

    systems = test_client.get("/api/catalog/systems").json()
    assert len(systems) == 1
    assert systems[0]["name"] == "Exported System"


def test_cascade_archive_system_and_object(client) -> None:
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)

    # 1. Create two systems with objects
    sys_a = test_client.post(
        "/api/catalog/systems", json={"name": "Sys A", "kind": "app"}, headers=headers
    ).json()
    obj_a = test_client.post(
        f"/api/catalog/systems/{sys_a['id']}/objects",
        json={"name": "ObjA", "label": "Obj A"},
        headers=headers,
    ).json()

    sys_b = test_client.post(
        "/api/catalog/systems", json={"name": "Sys B", "kind": "app"}, headers=headers
    ).json()
    obj_b = test_client.post(
        f"/api/catalog/systems/{sys_b['id']}/objects",
        json={"name": "ObjB", "label": "Obj B"},
        headers=headers,
    ).json()

    # 2. Create an integration referencing them
    integration_res = test_client.post(
        "/api/integrations",
        json={
            "name": "A to B Sync",
            "interaction_type": "ONE_WAY",
            "source_system_id": sys_a["id"],
            "source_object_id": obj_a["id"],
            "target_system_id": sys_b["id"],
            "target_object_id": obj_b["id"],
        },
        headers=headers,
    )
    assert integration_res.status_code == 201

    # 3. Archive Sys A WITHOUT cascade -> blocked with 409
    res_blocked = test_client.delete(f"/api/catalog/systems/{sys_a['id']}", headers=headers)
    assert res_blocked.status_code == 409
    assert res_blocked.json()["detail"]["code"] == "catalog_item_in_use"
    assert "A to B Sync" in res_blocked.json()["detail"]["message"] or any(
        i["name"] == "A to B Sync" for i in res_blocked.json()["detail"]["integrations"]
    )

    # 4. Archive Sys A WITH cascade=true -> succeeds 204
    res_cascade = test_client.delete(
        f"/api/catalog/systems/{sys_a['id']}?cascade=true", headers=headers
    )
    assert res_cascade.status_code == 204

    # 5. Verify Sys A and Integration are archived
    with testing_sessions() as db:
        archived_sys = db.scalar(select(CatalogSystem).where(CatalogSystem.id == UUID(sys_a["id"])))
        assert archived_sys.deleted_at is not None

        archived_int = db.scalar(
            select(Integration).where(Integration.name == "A to B Sync")
        )
        assert archived_int.deleted_at is not None
