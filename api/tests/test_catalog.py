from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import CatalogObject, CatalogSystem, Tenant, User


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
        tenant = Tenant(name=f"catalog-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="catalog@example.test",
                password_hash=hash_password("catalog-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "catalog@example.test", "password": "catalog-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def test_catalog_crud_uses_generic_names_types_and_stable_ids(client) -> None:
    test_client, _ = client
    created_system = test_client.post(
        "/api/catalog/systems",
        json={
            "name": "My Legacy Application",
            "kind": "homegrown-custom-platform",
            "metadata": {"region": "north", "active": True},
        },
        headers=csrf_headers(test_client),
    )
    assert created_system.status_code == 201
    system = created_system.json()
    system_id = system["id"]
    assert system["metadata"] == {"region": "north", "active": True}

    updated_system = test_client.patch(
        f"/api/catalog/systems/{system_id}",
        json={"name": "Renamed Legacy Application"},
        headers=csrf_headers(test_client),
    )
    assert updated_system.status_code == 200
    assert updated_system.json()["id"] == system_id
    assert updated_system.json()["name"] == "Renamed Legacy Application"
    assert test_client.get(f"/api/catalog/systems/{system_id}").status_code == 200
    positioned_system = test_client.patch(
        f"/api/catalog/systems/{system_id}",
        json={"position": {"x": 320, "y": 140}},
        headers=csrf_headers(test_client),
    )
    assert positioned_system.status_code == 200
    assert positioned_system.json()["position"] == {"x": 320.0, "y": 140.0}
    assert test_client.get(f"/api/catalog/systems/{system_id}").json()["position"] == {
        "x": 320.0,
        "y": 140.0,
    }

    created_object = test_client.post(
        f"/api/catalog/systems/{system_id}/objects",
        json={"name": "CustomerRecord"},
        headers=csrf_headers(test_client),
    )
    assert created_object.status_code == 201
    obj = created_object.json()
    assert obj["label"] == "CustomerRecord"
    assert obj["position"] == 0
    updated_object = test_client.patch(
        f"/api/catalog/objects/{obj['id']}",
        json={"label": "Customer"},
        headers=csrf_headers(test_client),
    )
    assert updated_object.status_code == 200
    assert updated_object.json()["id"] == obj["id"]
    assert updated_object.json()["label"] == "Customer"
    second_object = test_client.post(
        f"/api/catalog/systems/{system_id}/objects",
        json={"name": "OrderRecord"},
        headers=csrf_headers(test_client),
    )
    assert second_object.status_code == 201
    listed_objects = test_client.get(f"/api/catalog/systems/{system_id}/objects").json()
    assert [item["position"] for item in listed_objects] == [0, 1]

    created_field = test_client.post(
        f"/api/catalog/objects/{obj['id']}/fields",
        json={
            "name": "CUST_ID",
            "data_type": "customer-code",
            "required": True,
            "nullable": False,
            "default_value": {"source": "legacy"},
        },
        headers=csrf_headers(test_client),
    )
    assert created_field.status_code == 201
    field = created_field.json()
    field_id = field["id"]
    assert field["data_type"] == "customer-code"
    assert field["default_value"] == {"source": "legacy"}
    assert field["position"] == 0

    renamed_field = test_client.patch(
        f"/api/catalog/fields/{field_id}",
        json={"name": "CUSTOMER_IDENTIFIER"},
        headers=csrf_headers(test_client),
    )
    assert renamed_field.status_code == 200
    assert renamed_field.json()["id"] == field_id
    assert renamed_field.json()["name"] == "CUSTOMER_IDENTIFIER"
    assert test_client.get(f"/api/catalog/fields/{field_id}").status_code == 200
    assert test_client.delete(
        f"/api/catalog/objects/{obj['id']}", headers=csrf_headers(test_client)
    ).status_code == 204
    assert test_client.get(f"/api/catalog/objects/{obj['id']}").status_code == 404
    assert test_client.post(
        f"/api/catalog/objects/{obj['id']}/restore",
        headers=csrf_headers(test_client),
    ).status_code == 200
    assert test_client.post(
        f"/api/catalog/fields/{field_id}/restore",
        headers=csrf_headers(test_client),
    ).status_code == 200

    second_field = test_client.post(
        f"/api/catalog/objects/{obj['id']}/fields",
        json={"name": "PHONE", "data_type": "text"},
        headers=csrf_headers(test_client),
    )
    assert second_field.status_code == 201
    listed = test_client.get(f"/api/catalog/objects/{obj['id']}/fields").json()
    assert [item["position"] for item in listed] == [0, 1]


def test_archive_restore_and_name_conflicts(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "Archive Test"},
        headers=headers,
    ).json()
    duplicate = test_client.post(
        "/api/catalog/systems",
        json={"name": "Archive Test"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    object_response = test_client.post(
        f"/api/catalog/systems/{system['id']}/objects",
        json={"name": "Record"},
        headers=headers,
    )
    obj = object_response.json()
    field = test_client.post(
        f"/api/catalog/objects/{obj['id']}/fields",
        json={"name": "Code", "data_type": "text"},
        headers=headers,
    ).json()

    assert test_client.delete(
        f"/api/catalog/systems/{system['id']}", headers=headers
    ).status_code == 204
    assert test_client.get(f"/api/catalog/systems/{system['id']}").status_code == 404
    assert test_client.get(f"/api/catalog/systems/{system['id']}/objects").status_code == 404

    replacement = test_client.post(
        "/api/catalog/systems",
        json={"name": "Archive Test"},
        headers=headers,
    )
    assert replacement.status_code == 201
    assert test_client.post(
        f"/api/catalog/systems/{system['id']}/restore",
        headers=headers,
    ).status_code == 409
    assert test_client.delete(
        f"/api/catalog/systems/{replacement.json()['id']}", headers=headers
    ).status_code == 204

    restored = test_client.post(
        f"/api/catalog/systems/{system['id']}/restore",
        headers=headers,
    )
    assert restored.status_code == 200
    assert test_client.get(f"/api/catalog/systems/{system['id']}/objects").json() == []

    restored_object = test_client.post(
        f"/api/catalog/objects/{obj['id']}/restore",
        headers=headers,
    )
    assert restored_object.status_code == 200
    restored_field = test_client.post(
        f"/api/catalog/fields/{field['id']}/restore",
        headers=headers,
    )
    assert restored_field.status_code == 200

    assert test_client.delete(
        f"/api/catalog/fields/{field['id']}", headers=headers
    ).status_code == 204
    assert test_client.get(f"/api/catalog/fields/{field['id']}").status_code == 404
    assert test_client.post(
        f"/api/catalog/fields/{field['id']}/restore",
        headers=headers,
    ).status_code == 200


def test_catalog_requires_csrf_and_hides_other_tenants(client) -> None:
    test_client, testing_sessions = client
    response = test_client.post("/api/catalog/systems", json={"name": "No CSRF"})
    assert response.status_code == 403

    with testing_sessions.begin() as db:
        other_tenant = Tenant(name=f"other-{uuid4()}")
        db.add(other_tenant)
        db.flush()
        from app.models import CatalogSystem

        hidden_system = CatalogSystem(
            tenant_id=other_tenant.id,
            name="Private",
            kind="custom",
            binding_state="unbound",
            extra_metadata={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(hidden_system)
        db.flush()
        hidden_id = hidden_system.id

    assert test_client.get(f"/api/catalog/systems/{hidden_id}").status_code == 404
    assert test_client.get("/api/catalog/systems").json() == []


def test_catalog_requires_authentication(client) -> None:
    test_client, _ = client
    test_client.post(
        "/api/auth/logout",
        headers=csrf_headers(test_client),
    )

    response = test_client.get("/api/catalog/systems")
    assert response.status_code == 401


def test_catalog_validates_names_and_metadata_size(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)

    assert test_client.post(
        "/api/catalog/systems",
        json={"name": "  ", "kind": "custom"},
        headers=headers,
    ).status_code == 422
    assert test_client.post(
        "/api/catalog/systems",
        json={"name": "Too much metadata", "metadata": {"large": "x" * 17_000}},
        headers=headers,
    ).status_code == 422


def test_composite_foreign_key_prevents_cross_tenant_parent(client) -> None:
    _, testing_sessions = client
    with testing_sessions() as db, db.begin():
        first_tenant = Tenant(name=f"first-{uuid4()}")
        second_tenant = Tenant(name=f"second-{uuid4()}")
        db.add_all([first_tenant, second_tenant])
        db.flush()
        system = CatalogSystem(
            tenant_id=first_tenant.id,
            name="First tenant system",
            kind="custom",
            binding_state="unbound",
            extra_metadata={},
        )
        db.add(system)
        db.flush()
        invalid_object = CatalogObject(
            tenant_id=second_tenant.id,
            system_id=system.id,
            name="Cross-tenant object",
            label="Cross-tenant object",
            origin="manual",
            extra_metadata={},
            position=0,
        )
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(invalid_object)
                db.flush()
