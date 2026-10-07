from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import IntegrationFieldRef, Tenant, User


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
        tenant = Tenant(name=f"integrations-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="integrations@example.test",
                password_hash=hash_password("integration-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={
                "email": "integrations@example.test",
                "password": "integration-test-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def create_endpoint(test_client: TestClient, name: str, field_name: str) -> dict:
    system = test_client.post(
        "/api/catalog/systems",
        json={"name": f"{name} system", "kind": "custom platform"},
        headers=csrf_headers(test_client),
    )
    assert system.status_code == 201
    obj = test_client.post(
        f"/api/catalog/systems/{system.json()['id']}/objects",
        json={"name": f"{name} object"},
        headers=csrf_headers(test_client),
    )
    assert obj.status_code == 201
    field = test_client.post(
        f"/api/catalog/objects/{obj.json()['id']}/fields",
        json={"name": field_name, "data_type": "arbitrary-type"},
        headers=csrf_headers(test_client),
    )
    assert field.status_code == 201
    return {"system": system.json(), "object": obj.json(), "field": field.json()}


def create_integration(
    test_client: TestClient,
    source: dict,
    target: dict,
    *,
    graph: dict | None = None,
    name: str = "Customer sync",
) -> dict:
    response = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": source["system"]["id"],
            "source_object_id": source["object"]["id"],
            "target_system_id": target["system"]["id"],
            "target_object_id": target["object"]["id"],
            "name": name,
            "graph": graph
            or {"version": 1, "nodes": [], "edges": []},
            "sample_rows": [
                {
                    "rowId": "sample-1",
                    "values": {source["field"]["id"]: "a value"},
                }
            ],
        },
        headers=csrf_headers(test_client),
    )
    return response


def field_mapping_graph(source: dict, target: dict) -> dict:
    source_node = str(uuid4())
    transform_node = str(uuid4())
    target_node = str(uuid4())
    return {
        "version": 1,
        "nodes": [
            {"id": source_node, "type": "source", "position": {"x": 0, "y": 0}},
            {
                "id": transform_node,
                "type": "fx",
                "position": {"x": 200, "y": 0},
                "config": {"function": "trim"},
            },
            {"id": target_node, "type": "target", "position": {"x": 400, "y": 0}},
        ],
        "edges": [
            {
                "id": str(uuid4()),
                "sourceNodeId": source_node,
                "sourcePortId": f"field:{source['field']['id']}",
                "targetNodeId": transform_node,
                "targetPortId": "input",
            },
            {
                "id": str(uuid4()),
                "sourceNodeId": transform_node,
                "sourcePortId": "output",
                "targetNodeId": target_node,
                "targetPortId": f"field:{target['field']['id']}",
            },
        ],
    }


def test_create_update_and_list_integration_with_stable_graph_field_refs(client) -> None:
    test_client, testing_sessions = client
    source = create_endpoint(test_client, "Legacy", "CUST_ID")
    target = create_endpoint(test_client, "Warehouse", "customer_code")
    created = create_integration(test_client, source, target)
    assert created.status_code == 201, created.text
    integration = created.json()
    assert integration["revision"] == 1
    assert integration["graph"]["version"] == 1
    assert integration["sample_rows"] == [
        {"rowId": "sample-1", "values": {source["field"]["id"]: "a value"}}
    ]

    graph = field_mapping_graph(source, target)
    saved = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": graph},
        headers=csrf_headers(test_client),
    )
    assert saved.status_code == 200, saved.text
    saved_integration = saved.json()
    assert saved_integration["revision"] == 2
    assert saved_integration["graph"]["edges"][0]["sourcePortId"] == (
        f"field:{source['field']['id']}"
    )
    with testing_sessions() as db:
        refs = list(
            db.scalars(
                select(IntegrationFieldRef).where(
                    IntegrationFieldRef.integration_id == UUID(integration["id"])
                )
            )
        )
    assert {(str(ref.field_id), ref.direction) for ref in refs} == {
        (source["field"]["id"], "source"),
        (target["field"]["id"], "target"),
    }
    renamed = test_client.patch(
        f"/api/catalog/fields/{source['field']['id']}",
        json={"name": "RENAMED_ID"},
        headers=csrf_headers(test_client),
    )
    assert renamed.status_code == 200
    assert renamed.json()["id"] == source["field"]["id"]
    assert test_client.get(f"/api/integrations/{integration['id']}").json()["graph"] == (
        saved_integration["graph"]
    )

    stale = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": graph},
        headers=csrf_headers(test_client),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    updated = test_client.patch(
        f"/api/integrations/{integration['id']}",
        json={"expected_revision": 2, "description": "Updated", "sample_rows": []},
        headers=csrf_headers(test_client),
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 3
    assert updated.json()["description"] == "Updated"
    assert test_client.get("/api/integrations").json()[0]["id"] == integration["id"]


def test_request_response_mapping_simulates_both_directions_and_tracks_refs(client) -> None:
    test_client, testing_sessions = client
    source = create_endpoint(test_client, "Client", "client_value")
    target = create_endpoint(test_client, "Service", "service_value")
    for endpoint in (source, target):
        changed = test_client.patch(
            f"/api/catalog/fields/{endpoint['field']['id']}",
            json={"data_type": "string"},
            headers=csrf_headers(test_client),
        )
        assert changed.status_code == 200
    integration = create_integration(test_client, source, target).json()
    assert integration["interaction_type"] == "ONE_WAY"
    assert integration["response_graph"]["version"] == 1

    request_graph = field_mapping_graph(source, target)
    response_graph = field_mapping_graph(target, source)
    saved = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={
            "expected_revision": 1,
            "graph": request_graph,
            "response_graph": response_graph,
            "interaction_type": "REQUEST_RESPONSE",
        },
        headers=csrf_headers(test_client),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["interaction_type"] == "REQUEST_RESPONSE"

    simulated = test_client.post(
        f"/api/integrations/{integration['id']}/dry-run",
        json={
            "responsePayload": [
                {"rowId": "response-1", "values": {target["field"]["id"]: "  returned  "}}
            ],
        },
        headers=csrf_headers(test_client),
    )
    assert simulated.status_code == 200, simulated.text
    result = simulated.json()
    assert result["requestOutcomes"] == result["rows"]
    assert result["requestOutcomes"][0]["targetValues"] == {
        target["field"]["id"]: "a value"
    }
    assert result["responseOutcomes"][0]["targetValues"] == {
        source["field"]["id"]: "returned"
    }
    with testing_sessions() as db:
        refs = list(
            db.scalars(
                select(IntegrationFieldRef).where(
                    IntegrationFieldRef.integration_id == UUID(integration["id"])
                )
            )
        )
    assert {(str(ref.field_id), ref.direction) for ref in refs} == {
        (source["field"]["id"], "source"),
        (source["field"]["id"], "response_target"),
        (target["field"]["id"], "target"),
        (target["field"]["id"], "response_source"),
    }

    response_only = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={
            "expected_revision": 2,
            "graph": {"version": 1, "nodes": [], "edges": []},
            "response_graph": response_graph,
            "interaction_type": "REQUEST_RESPONSE",
            "sample_rows": [],
        },
        headers=csrf_headers(test_client),
    )
    assert response_only.status_code == 200, response_only.text
    archived = test_client.delete(
        f"/api/catalog/fields/{source['field']['id']}",
        headers=csrf_headers(test_client),
    )
    assert archived.status_code == 409
    assert archived.json()["detail"]["code"] == "catalog_item_in_use"


def test_error_response_mapping_is_saved_separately_and_tracks_phase_refs(client) -> None:
    test_client, testing_sessions = client
    source = create_endpoint(test_client, "Error source", "source_value")
    target = create_endpoint(test_client, "Error target", "target_value")
    error_object = test_client.post(
        f"/api/catalog/systems/{target['system']['id']}/objects",
        json={"name": "Error payload"},
        headers=csrf_headers(test_client),
    )
    assert error_object.status_code == 201, error_object.text
    error_field = test_client.post(
        f"/api/catalog/objects/{error_object.json()['id']}/fields",
        json={"name": "error_code", "data_type": "string"},
        headers=csrf_headers(test_client),
    )
    assert error_field.status_code == 201, error_field.text
    error_endpoint = {
        "system": target["system"],
        "object": error_object.json(),
        "field": error_field.json(),
    }
    integration = create_integration(test_client, source, target).json()
    request_graph = field_mapping_graph(source, target)
    success_graph = field_mapping_graph(target, source)
    error_graph = field_mapping_graph(error_endpoint, source)

    saved = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={
            "expected_revision": 1,
            "graph": request_graph,
            "response_graph": success_graph,
            "error_response_object_id": error_object.json()["id"],
            "error_response_graph": error_graph,
            "interaction_type": "REQUEST_RESPONSE",
        },
        headers=csrf_headers(test_client),
    )
    assert saved.status_code == 200, saved.text
    response_body = saved.json()
    assert response_body["graph"]["edges"] == request_graph["edges"]
    assert response_body["response_graph"]["edges"] == success_graph["edges"]
    assert saved.json()["error_response_object_id"] == error_object.json()["id"]
    assert response_body["error_response_graph"]["edges"] == error_graph["edges"]
    for saved_graph, expected_graph in (
        (response_body["graph"], request_graph),
        (response_body["response_graph"], success_graph),
        (response_body["error_response_graph"], error_graph),
    ):
        assert [(node["id"], node["type"]) for node in saved_graph["nodes"]] == [
            (node["id"], node["type"]) for node in expected_graph["nodes"]
        ]

    reloaded = test_client.get(f"/api/integrations/{integration['id']}")
    assert reloaded.status_code == 200
    assert reloaded.json()["error_response_graph"]["edges"] == error_graph["edges"]

    with testing_sessions() as db:
        refs = list(
            db.scalars(
                select(IntegrationFieldRef).where(
                    IntegrationFieldRef.integration_id == UUID(integration["id"])
                )
            )
        )
    assert (source["field"]["id"], "error_response_target") in {
        (str(ref.field_id), ref.direction) for ref in refs
    }
    assert (error_field.json()["id"], "error_response_source") in {
        (str(ref.field_id), ref.direction) for ref in refs
    }

    no_schema_graph = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={
            "expected_revision": 2,
            "graph": request_graph,
            "error_response_object_id": None,
            "error_response_graph": error_graph,
        },
        headers=csrf_headers(test_client),
    )
    assert no_schema_graph.status_code == 422


def test_graph_save_can_atomically_update_name_and_sample_rows(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Atomic source", "input")
    target = create_endpoint(test_client, "Atomic target", "output")
    integration = create_integration(test_client, source, target).json()
    graph = field_mapping_graph(source, target)

    response = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={
            "expected_revision": 1,
            "graph": graph,
            "name": "Renamed mapping",
            "sample_rows": [
                {"rowId": "sample-new", "values": {source["field"]["id"]: "value"}},
            ],
        },
        headers=csrf_headers(test_client),
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Renamed mapping"
    assert response.json()["revision"] == 2
    assert response.json()["sample_rows"] == [
        {"rowId": "sample-new", "values": {source["field"]["id"]: "value"}},
    ]


def test_graph_validation_rejects_versions_fields_duplicates_and_cycles(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Source", "id")
    target = create_endpoint(test_client, "Target", "id")
    integration = create_integration(test_client, source, target).json()
    headers = csrf_headers(test_client)

    for invalid_version in (2, True):
        unsupported_version = test_client.put(
            f"/api/integrations/{integration['id']}/graph",
            json={
                "expected_revision": 1,
                "graph": {"version": invalid_version, "nodes": [], "edges": []},
            },
            headers=headers,
        )
        assert unsupported_version.status_code == 422

    graph = field_mapping_graph(source, target)
    graph["edges"][1]["targetPortId"] = "field:" + str(uuid4())
    unknown_field = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": graph},
        headers=headers,
    )
    assert unknown_field.status_code == 422
    assert "unknown_target_field" in str(unknown_field.json())

    graph = field_mapping_graph(source, target)
    graph["edges"].append(
        {
            **graph["edges"][1],
            "id": str(uuid4()),
            "sourceNodeId": graph["nodes"][0]["id"],
            "sourcePortId": f"field:{source['field']['id']}",
        }
    )
    duplicate_target = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": graph},
        headers=headers,
    )
    assert duplicate_target.status_code == 422
    assert "duplicate_target_mapping" in str(duplicate_target.json())

    cycle = field_mapping_graph(source, target)
    cycle["edges"].append(
        {
            "id": str(uuid4()),
            "sourceNodeId": cycle["nodes"][1]["id"],
            "sourcePortId": "output",
            "targetNodeId": cycle["nodes"][0]["id"],
            "targetPortId": "input",
        }
    )
    cyclic = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": cycle},
        headers=headers,
    )
    assert cyclic.status_code == 422
    assert "graph_cycle" in str(cyclic.json())


def test_graph_save_rejects_invalid_operation_configuration(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Config source", "value")
    target = create_endpoint(test_client, "Config target", "value")
    integration = create_integration(test_client, source, target).json()
    graph = field_mapping_graph(source, target)
    graph["nodes"][1]["config"] = {"function": "execute-expression"}

    response = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": graph},
        headers=csrf_headers(test_client),
    )

    assert response.status_code == 422
    assert "unsupported_function" in str(response.json())


def test_direct_field_mapping_requires_matching_generic_types(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Typed source", "source_value")
    target = create_endpoint(test_client, "Typed target", "target_value")
    changed = test_client.patch(
        f"/api/catalog/fields/{target['field']['id']}",
        json={"data_type": "different-generic-type"},
        headers=csrf_headers(test_client),
    )
    assert changed.status_code == 200
    integration = create_integration(test_client, source, target).json()
    source_node, target_node = str(uuid4()), str(uuid4())
    direct_graph = {
        "version": 1,
        "nodes": [
            {"id": source_node, "type": "source", "position": {"x": 0, "y": 0}},
            {"id": target_node, "type": "target", "position": {"x": 300, "y": 0}},
        ],
        "edges": [
            {
                "id": str(uuid4()),
                "sourceNodeId": source_node,
                "sourcePortId": f"field:{source['field']['id']}",
                "targetNodeId": target_node,
                "targetPortId": f"field:{target['field']['id']}",
            }
        ],
    }
    response = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": direct_graph},
        headers=csrf_headers(test_client),
    )
    assert response.status_code == 422
    assert "incompatible_field_types" in str(response.json())


def test_integration_endpoints_and_samples_are_validated(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Source", "id")
    target = create_endpoint(test_client, "Target", "id")
    payload = {
        "source_system_id": source["system"]["id"],
        "source_object_id": target["object"]["id"],
        "target_system_id": target["system"]["id"],
        "target_object_id": target["object"]["id"],
        "name": "Bad source selection",
    }
    mismatched_endpoint = test_client.post(
        "/api/integrations", json=payload, headers=csrf_headers(test_client)
    )
    assert mismatched_endpoint.status_code == 422

    response = create_integration(test_client, source, target)
    assert response.status_code == 201
    integration_id = response.json()["id"]

    invalid_sample = test_client.patch(
        f"/api/integrations/{integration_id}",
        json={
            "expected_revision": 1,
            "sample_rows": [{"rowId": "bad", "values": {str(uuid4()): "unknown"}}],
        },
        headers=csrf_headers(test_client),
    )
    assert invalid_sample.status_code == 422

    assert test_client.post(
        "/api/integrations",
        json={
            **payload,
            "source_object_id": source["object"]["id"],
        },
        headers=csrf_headers(test_client),
    ).status_code == 201


def test_archives_conflict_with_active_endpoint_and_graph_field_refs(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Source", "id")
    target = create_endpoint(test_client, "Target", "id")
    integration = create_integration(test_client, source, target).json()
    graph = field_mapping_graph(source, target)
    saved = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": graph},
        headers=csrf_headers(test_client),
    )
    assert saved.status_code == 200

    headers = csrf_headers(test_client)
    for path in (
        f"/api/catalog/fields/{source['field']['id']}",
        f"/api/catalog/objects/{source['object']['id']}",
        f"/api/catalog/systems/{source['system']['id']}",
    ):
        conflict = test_client.delete(path, headers=headers)
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "catalog_item_in_use"

    assert test_client.delete(
        f"/api/integrations/{integration['id']}", headers=headers
    ).status_code == 204
    assert test_client.delete(
        f"/api/catalog/fields/{source['field']['id']}", headers=headers
    ).status_code == 204
    assert test_client.get(f"/api/integrations/{integration['id']}").status_code == 404


def test_sample_rows_keep_source_fields_in_use_until_removed(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Sample source", "sampled")
    target = create_endpoint(test_client, "Sample target", "output")
    integration = create_integration(test_client, source, target).json()
    headers = csrf_headers(test_client)

    conflict = test_client.delete(
        f"/api/catalog/fields/{source['field']['id']}", headers=headers
    )
    assert conflict.status_code == 409

    updated = test_client.patch(
        f"/api/integrations/{integration['id']}",
        json={"expected_revision": 1, "sample_rows": []},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert test_client.delete(
        f"/api/catalog/fields/{source['field']['id']}", headers=headers
    ).status_code == 204


def test_dry_run_uses_saved_graph_and_sample_rows_without_writing(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Simulation source", "input")
    target = create_endpoint(test_client, "Simulation target", "output")
    for endpoint in (source, target):
        changed = test_client.patch(
            f"/api/catalog/fields/{endpoint['field']['id']}",
            json={"data_type": "string"},
            headers=csrf_headers(test_client),
        )
        assert changed.status_code == 200

    integration = create_integration(test_client, source, target).json()
    graph = field_mapping_graph(source, target)
    graph["nodes"][1]["config"]["function"] = "upper"
    saved = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={"expected_revision": 1, "graph": graph},
        headers=csrf_headers(test_client),
    )
    assert saved.status_code == 200

    simulated = test_client.post(
        f"/api/integrations/{integration['id']}/dry-run",
        json={"expectedRevision": 2},
        headers=csrf_headers(test_client),
    )
    assert simulated.status_code == 200, simulated.text
    result = simulated.json()
    assert result["integrationId"] == integration["id"]
    assert result["revision"] == 2
    assert result["summary"] == {"total": 1, "ok": 1, "skipped": 0, "failed": 0}
    assert result["rows"][0]["targetValues"] == {target["field"]["id"]: "A VALUE"}
    assert result["rows"][0]["trace"][0]["outputs"][f"field:{source['field']['id']}"] == (
        "[redacted]"
    )
    assert result["traceTruncated"] is False

    unchanged = test_client.get(f"/api/integrations/{integration['id']}").json()
    assert unchanged["revision"] == 2
    assert unchanged["graph"] == saved.json()["graph"]


def test_dry_run_accepts_draft_graph_and_rows_without_persisting_them(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Draft source", "input")
    target = create_endpoint(test_client, "Draft target", "output")
    for endpoint in (source, target):
        changed = test_client.patch(
            f"/api/catalog/fields/{endpoint['field']['id']}",
            json={"data_type": "string"},
            headers=csrf_headers(test_client),
        )
        assert changed.status_code == 200
    integration = create_integration(test_client, source, target).json()
    graph = field_mapping_graph(source, target)
    graph["nodes"][1]["config"]["function"] = "trim"

    response = test_client.post(
        f"/api/integrations/{integration['id']}/dry-run",
        json={
            "expectedRevision": 1,
            "graph": graph,
            "rows": [
                {
                    "rowId": "draft-row",
                    "values": {source["field"]["id"]: "  Ada  "},
                },
                {"rowId": "bad-row", "values": {source["field"]["id"]: 42}},
            ],
            "options": {"includeTraceValues": True},
        },
        headers=csrf_headers(test_client),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["summary"] == {"total": 2, "ok": 1, "skipped": 0, "failed": 1}
    assert result["rows"][0]["rowId"] == "draft-row"
    assert result["rows"][0]["targetValues"] == {target["field"]["id"]: "Ada"}
    assert result["rows"][0]["trace"][0]["outputs"][f"field:{source['field']['id']}"] == (
        "  Ada  "
    )
    assert result["rows"][1]["outcome"] == "failed"
    assert result["rows"][1]["errors"][0]["code"] == "type_mismatch"
    assert result["rows"][1]["errors"][0]["nodeId"] == graph["nodes"][1]["id"]
    unchanged = test_client.get(f"/api/integrations/{integration['id']}").json()
    assert unchanged["revision"] == 1
    assert unchanged["graph"]["nodes"] == []
    assert unchanged["sample_rows"][0]["rowId"] == "sample-1"


def test_dry_run_checks_auth_revision_catalog_and_graph_limits(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Validation source", "input")
    target = create_endpoint(test_client, "Validation target", "output")
    for endpoint in (source, target):
        changed = test_client.patch(
            f"/api/catalog/fields/{endpoint['field']['id']}",
            json={"data_type": "string"},
            headers=csrf_headers(test_client),
        )
        assert changed.status_code == 200
    integration = create_integration(test_client, source, target).json()
    path = f"/api/integrations/{integration['id']}/dry-run"

    assert test_client.post(path, json={}).status_code == 403
    stale = test_client.post(
        path,
        json={"expectedRevision": 2},
        headers=csrf_headers(test_client),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    unknown_field = test_client.post(
        path,
        json={
            "rows": [{"rowId": "unknown", "values": {str(uuid4()): "value"}}],
        },
        headers=csrf_headers(test_client),
    )
    assert unknown_field.status_code == 422
    assert unknown_field.json()["detail"]["code"] == "unknown_sample_field"

    invalid_graph = field_mapping_graph(source, target)
    invalid_graph["nodes"][1]["config"]["function"] = "not-supported"
    graph_error = test_client.post(
        path,
        json={"graph": invalid_graph},
        headers=csrf_headers(test_client),
    )
    assert graph_error.status_code == 422
    assert graph_error.json()["detail"]["code"] == "invalid_graph"
    assert "unsupported_function" in str(graph_error.json()["detail"]["issues"])

    oversized_rows = [
        {"rowId": str(index), "values": {source["field"]["id"]: "x"}}
        for index in range(101)
    ]
    row_limit = test_client.post(
        path,
        json={"rows": oversized_rows},
        headers=csrf_headers(test_client),
    )
    assert row_limit.status_code == 422


def test_dry_run_is_tenant_scoped(client) -> None:
    test_client, testing_sessions = client
    source = create_endpoint(test_client, "Tenant source", "input")
    target = create_endpoint(test_client, "Tenant target", "output")
    integration = create_integration(test_client, source, target).json()

    with testing_sessions.begin() as db:
        tenant = Tenant(name=f"simulation-outsider-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="simulation-outsider@example.test",
                password_hash=hash_password("outsider-test-password"),
            )
        )

    with TestClient(main.app) as outsider:
        csrf = outsider.get("/api/auth/csrf").json()["csrf_token"]
        login = outsider.post(
            "/api/auth/login",
            json={
                "email": "simulation-outsider@example.test",
                "password": "outsider-test-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert login.status_code == 200
        denied = outsider.post(
            f"/api/integrations/{integration['id']}/dry-run",
            json={},
            headers=csrf_headers(outsider),
        )
        analysis = outsider.get("/api/integrations/architecture")
    assert denied.status_code == 404
    assert analysis.status_code == 200
    assert analysis.json() == {"integrations": [], "conflicts": []}


def test_integration_dependencies_are_tenant_scoped_unique_and_acyclic(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Source", "id")
    target = create_endpoint(test_client, "Target", "id")
    first = create_integration(test_client, source, target, name="First").json()
    second = create_integration(test_client, source, target, name="Second").json()
    third = create_integration(test_client, source, target, name="Third").json()
    headers = csrf_headers(test_client)

    assert test_client.post(
        f"/api/integrations/{first['id']}/dependencies",
        json={"downstream_integration_id": first["id"]},
        headers=headers,
    ).status_code == 422
    first_to_second = test_client.post(
        f"/api/integrations/{first['id']}/dependencies",
        json={"downstream_integration_id": second["id"]},
        headers=headers,
    )
    assert first_to_second.status_code == 201
    duplicate = test_client.post(
        f"/api/integrations/{first['id']}/dependencies",
        json={"downstream_integration_id": second["id"]},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert test_client.post(
        f"/api/integrations/{second['id']}/dependencies",
        json={"downstream_integration_id": first["id"]},
        headers=headers,
    ).status_code == 409

    assert test_client.post(
        f"/api/integrations/{second['id']}/dependencies",
        json={"downstream_integration_id": third["id"]},
        headers=headers,
    ).status_code == 201
    assert test_client.get(f"/api/integrations/{first['id']}/dependencies").json() == [
        first_to_second.json()
    ]
    assert test_client.delete(
        f"/api/integrations/{first['id']}/dependencies/{second['id']}",
        headers=headers,
    ).status_code == 204
    assert test_client.delete(
        f"/api/integrations/{second['id']}", headers=headers
    ).status_code == 204
    assert test_client.get(f"/api/integrations/{first['id']}/dependencies").json() == []


def test_architecture_analysis_reports_conflicts_health_and_upstream_warnings(client) -> None:
    test_client, _ = client
    source = create_endpoint(test_client, "Architecture source", "id")
    target = create_endpoint(test_client, "Architecture target", "id")
    independent_target = create_endpoint(test_client, "Independent target", "id")
    first = create_integration(
        test_client,
        source,
        target,
        graph=field_mapping_graph(source, target),
        name="First writer",
    ).json()
    second = create_integration(
        test_client,
        source,
        target,
        graph=field_mapping_graph(source, target),
        name="Second writer",
    ).json()
    dependent_draft = create_integration(
        test_client, source, independent_target, name="Dependent draft"
    ).json()
    healthy = create_integration(
        test_client,
        source,
        independent_target,
        graph=field_mapping_graph(source, independent_target),
        name="Healthy integration",
    ).json()
    headers = csrf_headers(test_client)
    assert test_client.post(
        f"/api/integrations/{first['id']}/dependencies",
        json={"downstream_integration_id": dependent_draft["id"]},
        headers=headers,
    ).status_code == 201

    renamed_target = test_client.patch(
        f"/api/catalog/fields/{target['field']['id']}",
        json={"label": "Renamed account identifier"},
        headers=headers,
    )
    assert renamed_target.status_code == 200

    response = test_client.get("/api/integrations/architecture")
    assert response.status_code == 200
    analysis = {item["id"]: item for item in response.json()["integrations"]}
    assert analysis[first["id"]]["status"] == "attention"
    assert analysis[second["id"]]["status"] == "attention"
    assert analysis[dependent_draft["id"]]["status"] == "attention"
    assert analysis[dependent_draft["id"]]["upstream"] == [
        {"id": first["id"], "name": "First writer", "status": "attention"}
    ]
    assert "No target fields are mapped." in analysis[dependent_draft["id"]]["reasons"]
    assert any(
        reason.startswith("Depends on unhealthy upstream")
        for reason in analysis[dependent_draft["id"]]["reasons"]
    )
    assert analysis[healthy["id"]]["status"] == "healthy"
    conflict, = response.json()["conflicts"]
    assert conflict["field_id"] == target["field"]["id"]
    assert conflict["field_label"] == "Renamed account identifier"
    assert {item["id"] for item in conflict["integrations"]} == {
        first["id"],
        second["id"],
    }

    assert test_client.delete(
        f"/api/integrations/{second['id']}", headers=headers
    ).status_code == 204
    updated = test_client.get("/api/integrations/architecture").json()
    assert updated["conflicts"] == []
    updated_by_id = {item["id"]: item for item in updated["integrations"]}
    assert updated_by_id[first["id"]]["status"] == "healthy"
    assert updated_by_id[dependent_draft["id"]]["status"] == "draft"


def test_integration_routes_require_authentication_and_csrf(client) -> None:
    test_client, _ = client
    assert test_client.get("/api/integrations").status_code == 200
    response = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": str(uuid4()),
            "source_object_id": str(uuid4()),
            "target_system_id": str(uuid4()),
            "target_object_id": str(uuid4()),
            "name": "No CSRF",
        },
    )
    assert response.status_code == 403
    test_client.post("/api/auth/logout", headers=csrf_headers(test_client))
    assert test_client.get("/api/integrations").status_code == 401
