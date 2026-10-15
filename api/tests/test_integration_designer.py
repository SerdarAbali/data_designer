import json
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ArchitectureInterface, Integration
from tests.test_integrations import (
    client as client_fixture,
)
from tests.test_integrations import (
    create_endpoint,
    csrf_headers,
)
from tests.test_scenarios import mapped_contract, scenario_document, string_endpoint

client = client_fixture

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "integration-designer" / "demo.json"
)


def _workspace(test_client, headers, disciplines=("solution", "integration")):
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": "Integration Workspace", "disciplines": list(disciplines)},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _design(workspace_id) -> str:
    return f"/api/workspaces/{workspace_id}/integration-design"


def _create_interface(test_client, headers, workspace_id, state_id, name="Payments API") -> str:
    base = f"/api/workspaces/{workspace_id}/solution"
    design = test_client.post(
        f"{base}/solutions",
        json={"state_id": state_id, "name": f"Platform {uuid4().hex[:6]}"},
        headers=headers,
    )
    assert design.status_code == 201, design.text
    solution_id = design.json()["solution"]["solution_object_id"]
    component = test_client.post(
        f"{base}/solutions/{solution_id}/components",
        json={"state_id": state_id, "name": "Payment API", "position": {"x": 0, "y": 0}},
        headers=headers,
    )
    assert component.status_code == 201, component.text
    component_id = next(
        item for item in component.json()["components"] if item["name"] == "Payment API"
    )["object_id"]
    interface = test_client.post(
        f"{base}/components/{component_id}/interfaces",
        json={
            "state_id": state_id,
            "name": name,
            "direction": "provided",
            "interface_kind": "sync",
            "protocol": "HTTPS",
        },
        headers=headers,
    )
    assert interface.status_code == 201, interface.text
    component = next(
        item for item in interface.json()["components"] if item["object_id"] == component_id
    )
    interface_id = next(
        item for item in component["interfaces"] if item["name"] == name
    )["object_id"]
    operation = test_client.post(
        f"{base}/interfaces/{interface_id}/operations",
        json={"state_id": state_id, "name": "CreatePayment", "operation_kind": "operation"},
        headers=headers,
    )
    assert operation.status_code == 201, operation.text
    return interface_id


def test_integration_designer_requires_enabled_discipline(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": "Info Only", "disciplines": ["information"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    response = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    )
    assert response.status_code == 404
    assert "not enabled" in response.json()["detail"].lower()


def test_integration_landscape_contract_and_flow(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    interface_id = _create_interface(test_client, headers, workspace_id, state_id)
    contract = mapped_contract(test_client, "Customer push", source, target)
    source_field = source["field"]["id"]

    updated = test_client.patch(
        f"/api/integrations/{contract['id']}",
        json={
            "expected_revision": contract["revision"],
            "pattern": "request_reply",
            "implementation_status": "built",
            "producer_interface_id": interface_id,
            "specification": {
                "retry": {"max_attempts": 3, "backoff": "exponential"},
                "timeout_ms": 5000,
                "idempotent": True,
                "idempotency_key_field_id": source_field,
                "security": {"auth_type": "oauth2", "notes": "mTLS between regions"},
                "routing": "Route by customer region",
                "orchestration_role": "orchestration",
                "error_handling": "Retry then dead-letter",
            },
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["pattern"] == "request_reply"
    assert body["implementation_status"] == "built"
    assert body["producer_interface_id"] == interface_id
    assert body["specification"]["retry"]["max_attempts"] == 3
    assert body["specification"]["idempotency_key_field_id"] == source_field

    landscape = test_client.get(
        f"{_design(workspace_id)}/landscape", params={"state_id": state_id}
    ).json()
    assert landscape["editable"] is True
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["pattern"] == "request_reply"
    assert summary["status"] == "built"
    assert summary["producer_interface"]["name"] == "Payments API"
    assert summary["consumer_interface"] is None
    assert summary["target_fields_mapped"] == 1
    assert summary["target_fields_total"] == 1
    assert summary["has_request_graph"] is True
    assert summary["has_response_graph"] is True
    assert summary["scenario_count"] == 0
    assert summary["specification"]["routing"] == "Route by customer region"
    assert summary["specification"]["security"]["auth_type"] == "oauth2"

    interface_entry = next(
        item for item in landscape["interfaces"] if item["object_id"] == interface_id
    )
    assert [op["name"] for op in interface_entry["operations"]] == ["CreatePayment"]
    assert interface_entry["contract_ids"] == [contract["id"]]

    detail = test_client.get(
        f"{_design(workspace_id)}/contracts/{contract['id']}", params={"state_id": state_id}
    ).json()
    assert detail["contract"]["pattern"] == "request_reply"
    assert detail["source_interface"]["object_id"] == interface_id
    assert detail["target_interface"] is None
    phases = {phase["phase"]: phase for phase in detail["phases"]}
    assert phases["request"]["transformation_count"] == 1
    assert phases["request"]["mapped_target_count"] == 1
    assert phases["success-response"]["configured"] is True

    flow = test_client.get(
        f"{_design(workspace_id)}/contracts/{contract['id']}/flow",
        params={"state_id": state_id},
    ).json()
    assert flow["routing"] == "Route by customer region"
    assert flow["trigger_config"] == {}
    phases = {phase["phase"]: phase for phase in flow["phases"]}
    assert phases["request"]["transformations"][0]["type"] == "fx"
    assert phases["request"]["transformations"][0]["label"] == "fx: upper"


def test_integration_conformance_scenario_statuses(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    workspace_id = workspace["id"]
    state_id = candidate["id"]

    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    contract = mapped_contract(test_client, "Customer push", source, target)
    target_field = target["field"]["id"]

    passing = scenario_document(contract, source, target)
    created = test_client.post(
        "/api/scenarios",
        json={
            "scope_integration_id": contract["id"],
            "name": "Happy path",
            "category": "happy_path",
            "document": passing,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    failing = scenario_document(contract, source, target)
    failing["items"][1]["expectedValues"] = {target_field: "WRONG"}
    failing["assertions"][0]["expected"] = "nope"
    failed = test_client.post(
        "/api/scenarios",
        json={
            "scope_integration_id": contract["id"],
            "name": "Broken assertion",
            "category": "error",
            "document": failing,
        },
        headers=headers,
    )
    assert failed.status_code == 201, failed.text

    not_run = scenario_document(contract, source, target)
    not_run["items"] = [
        {
            "kind": "actor",
            "id": "a1",
            "fromParticipantId": "user",
            "toParticipantId": "src",
            "label": "Submit",
        }
    ]
    not_run["assertions"] = []
    untouched = test_client.post(
        "/api/scenarios",
        json={
            "scope_integration_id": contract["id"],
            "name": "Not run yet",
            "category": "alternative",
            "document": not_run,
        },
        headers=headers,
    )
    assert untouched.status_code == 201, untouched.text

    conformance = test_client.get(
        f"{_design(workspace_id)}/contracts/{contract['id']}/conformance",
        params={"state_id": state_id},
    ).json()
    by_name = {item["name"]: item["status"] for item in conformance["scenarios"]}
    assert by_name["Happy path"] == "passing"
    assert by_name["Broken assertion"] == "failing"
    assert by_name["Not run yet"] == "not_run"
    assert conformance["summary"]["passing"] == 1
    assert conformance["summary"]["failing"] == 1
    assert conformance["summary"]["not_run"] == 1
    assert conformance["request_coverage"]["mapped"] == 1
    assert conformance["request_coverage"]["ratio"] == 1.0
    assert conformance["response_coverage"]["mapped"] == 1

    time.sleep(0.05)
    bumped = test_client.patch(
        f"/api/integrations/{contract['id']}",
        json={"expected_revision": contract["revision"], "name": "Customer push v2"},
        headers=headers,
    )
    assert bumped.status_code == 200, bumped.text

    refreshed = test_client.get(
        f"{_design(workspace_id)}/contracts/{contract['id']}/conformance",
        params={"state_id": state_id},
    ).json()
    by_name = {item["name"]: item["status"] for item in refreshed["scenarios"]}
    assert by_name["Happy path"] == "outdated"
    assert by_name["Broken assertion"] == "outdated"
    assert refreshed["summary"]["outdated"] == 2


def test_integration_specification_bounds_and_interface_links(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source = create_endpoint(test_client, "CRM", "name")
    target = create_endpoint(test_client, "ERP", "code")

    base = {
        "source_system_id": source["system"]["id"],
        "source_object_id": source["object"]["id"],
        "target_system_id": target["system"]["id"],
        "target_object_id": target["object"]["id"],
        "name": "Contract",
        "sample_rows": [],
    }
    over_timeout = test_client.post(
        "/api/integrations",
        json={**base, "specification": {"timeout_ms": 700_000}},
        headers=headers,
    )
    assert over_timeout.status_code == 422, over_timeout.text
    key_without_idempotent = test_client.post(
        "/api/integrations",
        json={
            **base,
            "specification": {"idempotency_key_field_id": source["field"]["id"]},
        },
        headers=headers,
    )
    assert key_without_idempotent.status_code == 422, key_without_idempotent.text
    bad_interface = test_client.post(
        "/api/integrations",
        json={**base, "producer_interface_id": str(uuid4())},
        headers=headers,
    )
    assert bad_interface.status_code == 422, bad_interface.text
    assert "interface" in bad_interface.json()["detail"].lower()

    bad_consumer = test_client.post(
        "/api/integrations",
        json={**base, "consumer_interface_id": str(uuid4())},
        headers=headers,
    )
    assert bad_consumer.status_code == 422, bad_consumer.text

    # Referential integrity also holds on the update path, for both endpoints.
    contract = test_client.post("/api/integrations", json=base, headers=headers)
    assert contract.status_code == 201, contract.text
    contract_id = contract.json()["id"]
    bad_update = test_client.patch(
        f"/api/integrations/{contract_id}",
        json={
            "expected_revision": contract.json()["revision"],
            "producer_interface_id": str(uuid4()),
        },
        headers=headers,
    )
    assert bad_update.status_code == 422, bad_update.text
    bad_update_consumer = test_client.patch(
        f"/api/integrations/{contract_id}",
        json={
            "expected_revision": contract.json()["revision"],
            "consumer_interface_id": str(uuid4()),
        },
        headers=headers,
    )
    assert bad_update_consumer.status_code == 422, bad_update_consumer.text


def test_interface_links_are_enforced_by_database_constraints(client) -> None:
    test_client, testing_sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    workspace_id = workspace["id"]
    source = create_endpoint(test_client, "CRM", "name")
    target = create_endpoint(test_client, "ERP", "code")
    interface_id = _create_interface(test_client, headers, workspace_id, candidate["id"])

    contract = test_client.post(
        "/api/integrations",
        json={
            "source_system_id": source["system"]["id"],
            "source_object_id": source["object"]["id"],
            "target_system_id": target["system"]["id"],
            "target_object_id": target["object"]["id"],
            "name": "DB integrity contract",
            "sample_rows": [],
        },
        headers=headers,
    ).json()
    contract_id = UUID(contract["id"])

    # The database itself rejects dangling interface references (not just validation).
    with testing_sessions() as db:
        row = db.get(Integration, contract_id)
        row.producer_interface_id = uuid4()
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    with testing_sessions() as db:
        row = db.get(Integration, contract_id)
        row.consumer_interface_id = uuid4()
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    # A valid reference is accepted ...
    with testing_sessions() as db:
        row = db.get(Integration, contract_id)
        row.producer_interface_id = UUID(interface_id)
        db.commit()

    # ... and the referenced canonical interface cannot be deleted while in use.
    with testing_sessions() as db:
        interface = db.get(ArchitectureInterface, UUID(interface_id))
        db.delete(interface)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_integration_designer_demo_fixture_shape() -> None:
    assert FIXTURE_PATH.exists(), f"missing integration fixture at {FIXTURE_PATH}"
    demo = json.loads(FIXTURE_PATH.read_text())
    assert demo["contract"]["pattern"] == "request_reply"
    statuses = {"draft", "in_progress", "built", "verified"}
    assert demo["contract"]["implementation_status"] in statuses
    assert {iface["direction"] for iface in demo["interfaces"]} <= {"provided", "required"}
    assert demo["scenarios"], "the fixture must include at least one scenario"
