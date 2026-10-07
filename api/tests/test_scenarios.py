from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.auth.security import hash_password
from app.models import Tenant, User
from tests.test_integrations import client as client_fixture
from tests.test_integrations import (
    create_endpoint,
    create_integration,
    csrf_headers,
    field_mapping_graph,
)

client = client_fixture


def string_endpoint(test_client, name: str, field_name: str) -> dict:
    endpoint = create_endpoint(test_client, name, field_name)
    changed = test_client.patch(
        f"/api/catalog/fields/{endpoint['field']['id']}",
        json={"data_type": "string"},
        headers=csrf_headers(test_client),
    )
    assert changed.status_code == 200
    return endpoint


def mapped_contract(test_client, name: str, source: dict, target: dict, *, upper: bool = True):
    integration = create_integration(test_client, source, target, name=name).json()
    graph = field_mapping_graph(source, target)
    graph["nodes"][1]["config"]["function"] = "upper" if upper else "trim"
    response_graph = field_mapping_graph(target, source)
    saved = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={
            "expected_revision": 1,
            "graph": graph,
            "response_graph": response_graph,
            "interaction_type": "REQUEST_RESPONSE",
        },
        headers=csrf_headers(test_client),
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def scenario_document(contract: dict, source: dict, target: dict, **overrides) -> dict:
    source_field = source["field"]["id"]
    target_field = target["field"]["id"]
    document = {
        "version": 1,
        "preconditions": "Customer exists in CRM",
        "trigger": "User saves customer",
        "participants": [
            {"id": "user", "kind": "actor", "label": "Sales rep"},
            {"id": "src", "kind": "system", "systemId": source["system"]["id"]},
            {"id": "tgt", "kind": "system", "systemId": target["system"]["id"]},
        ],
        "contractIds": [contract["id"]],
        "beforeState": [
            {
                "id": "before-1",
                "participantId": "src",
                "objectId": source["object"]["id"],
                "values": {source_field: "acme"},
            }
        ],
        "afterState": [
            {
                "id": "after-1",
                "participantId": "tgt",
                "objectId": target["object"]["id"],
                "values": {target_field: "ACME"},
            }
        ],
        "items": [
            {
                "kind": "actor",
                "id": "s0",
                "fromParticipantId": "user",
                "toParticipantId": "src",
                "label": "Save customer",
            },
            {
                "kind": "contract",
                "id": "s1",
                "contractId": contract["id"],
                "phase": "request",
                "sampleValues": {source_field: "acme"},
                "expectedValues": {target_field: "ACME"},
            },
            {
                "kind": "alt",
                "id": "f1",
                "operands": [
                    {
                        "guard": "accepted",
                        "items": [
                            {
                                "kind": "contract",
                                "id": "s2",
                                "contractId": contract["id"],
                                "phase": "success-response",
                                "sampleValues": {target_field: " ok "},
                                "expectedValues": {source_field: "ok"},
                            }
                        ],
                    },
                    {
                        "guard": "rejected",
                        "items": [
                            {
                                "kind": "self",
                                "id": "s3",
                                "fromParticipantId": "src",
                                "label": "Log failure",
                            }
                        ],
                    },
                ],
            },
        ],
        "assertions": [
            {
                "id": "a1",
                "text": "Customer code is upper case",
                "stepId": "s1",
                "fieldId": target_field,
                "expected": "ACME",
            },
            {"id": "a2", "text": "Audit entry exists"},
        ],
        "notes": "",
    }
    document.update(overrides)
    return document


def setup_contract(test_client):
    source = string_endpoint(test_client, "CRM", "name")
    target = string_endpoint(test_client, "ERP", "code")
    contract = mapped_contract(test_client, "Customer push", source, target)
    return source, target, contract


def test_scenario_crud_revision_and_listing(client) -> None:
    test_client, _ = client
    source, target, contract = setup_contract(test_client)
    headers = csrf_headers(test_client)
    document = scenario_document(contract, source, target)

    created = test_client.post(
        "/api/scenarios",
        json={
            "scope_integration_id": contract["id"],
            "name": "Happy customer push",
            "category": "happy_path",
            "document": document,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    scenario = created.json()
    assert scenario["revision"] == 1
    assert scenario["document"]["items"][2]["operands"][1]["items"][0]["toParticipantId"] == "src"

    landscape = test_client.post(
        "/api/scenarios",
        json={"name": "End to end", "category": "alternative", "document": document},
        headers=headers,
    )
    assert landscape.status_code == 201, landscape.text

    duplicate = test_client.post(
        "/api/scenarios",
        json={"name": "End to end", "category": "error", "document": document},
        headers=headers,
    )
    assert duplicate.status_code == 409

    by_contract = test_client.get(f"/api/scenarios?integration_id={contract['id']}").json()
    assert {item["name"] for item in by_contract} == {"Happy customer push", "End to end"}
    contract_only = test_client.get("/api/scenarios?scope=contract").json()
    assert [item["name"] for item in contract_only] == ["Happy customer push"]
    landscape_only = test_client.get("/api/scenarios?scope=landscape").json()
    assert [item["name"] for item in landscape_only] == ["End to end"]

    updated = test_client.put(
        f"/api/scenarios/{scenario['id']}",
        json={
            "expected_revision": 1,
            "name": "Renamed",
            "category": "error",
            "document": document,
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    stale = test_client.put(
        f"/api/scenarios/{scenario['id']}",
        json={"expected_revision": 1, "name": "x", "category": "error", "document": document},
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    archived = test_client.delete(f"/api/scenarios/{scenario['id']}", headers=headers)
    assert archived.status_code == 204
    assert test_client.get(f"/api/scenarios/{scenario['id']}").status_code == 404

    unchanged = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert unchanged["revision"] == contract["revision"]
    assert unchanged["graph"] == contract["graph"]


def test_scenario_validation_rejects_invalid_references(client) -> None:
    test_client, _ = client
    source, target, contract = setup_contract(test_client)
    other_source = string_endpoint(test_client, "Other", "x")
    other = mapped_contract(test_client, "Other contract", other_source, target)
    headers = csrf_headers(test_client)

    def post(document, scope=None):
        return test_client.post(
            "/api/scenarios",
            json={
                "scope_integration_id": scope,
                "name": "Invalid",
                "category": "error",
                "document": document,
            },
            headers=headers,
        )

    scoped_other = scenario_document(other, other_source, target)
    response = post(scoped_other, scope=contract["id"])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_scenario_reference"

    document = scenario_document(contract, source, target)
    document["items"][1]["sampleValues"] = {target["field"]["id"]: "wrong side"}
    assert post(document).status_code == 422

    document = scenario_document(contract, source, target)
    document["items"][1]["phase"] = "async-response"
    assert post(document).status_code == 422

    document = scenario_document(contract, source, target)
    document["beforeState"][0]["participantId"] = "tgt"
    assert post(document).status_code == 422

    document = scenario_document(contract, source, target)
    document["items"][0]["toParticipantId"] = "ghost"
    assert post(document).status_code == 422

    document = scenario_document(contract, source, target)
    document["items"][0]["sampleValues"] = {source["field"]["id"]: "x"}
    assert post(document).status_code == 422

    document = scenario_document(contract, source, target)
    document["items"][2]["operands"] = document["items"][2]["operands"][:1]
    assert post(document).status_code == 422


def test_archived_contract_reference_is_kept_and_reported(client) -> None:
    test_client, _ = client
    source, target, contract = setup_contract(test_client)
    headers = csrf_headers(test_client)
    document = scenario_document(contract, source, target)
    created = test_client.post(
        "/api/scenarios",
        json={"name": "Landscape flow", "category": "happy_path", "document": document},
        headers=headers,
    ).json()

    assert test_client.delete(
        f"/api/integrations/{contract['id']}", headers=headers
    ).status_code == 204

    resaved = test_client.put(
        f"/api/scenarios/{created['id']}",
        json={
            "expected_revision": 1,
            "name": "Landscape flow",
            "category": "happy_path",
            "document": document,
        },
        headers=headers,
    )
    assert resaved.status_code == 200, resaved.text

    evaluated = test_client.post(
        "/api/scenarios/evaluate", json={"document": document}, headers=headers
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    outcomes = {item["stepId"]: item["outcome"] for item in body["steps"]}
    assert outcomes["s1"] == "missing_reference"
    assert body["missingReferences"]
    assert body["summary"]["missingReferences"] >= 1


def test_evaluate_runs_contract_phases_and_assertions(client) -> None:
    test_client, _ = client
    source, target, contract = setup_contract(test_client)
    headers = csrf_headers(test_client)
    document = scenario_document(contract, source, target)

    evaluated = test_client.post(
        "/api/scenarios/evaluate", json={"document": document}, headers=headers
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    steps = {item["stepId"]: item for item in body["steps"]}
    assert steps["s0"]["outcome"] == "not_evaluated"
    assert steps["s1"]["outcome"] == "ok"
    assert steps["s1"]["targetValues"] == {target["field"]["id"]: "ACME"}
    assert steps["s2"]["outcome"] == "ok"
    assert steps["s3"]["outcome"] == "not_evaluated"
    assertions = {item["assertionId"]: item["status"] for item in body["assertions"]}
    assert assertions == {"a1": "passed", "a2": "manual"}
    assert body["summary"]["ok"] == 2

    document["items"][1]["expectedValues"] = {target["field"]["id"]: "acme"}
    document["assertions"][0]["expected"] = "nope"
    mismatch = test_client.post(
        "/api/scenarios/evaluate", json={"document": document}, headers=headers
    ).json()
    step = next(item for item in mismatch["steps"] if item["stepId"] == "s1")
    assert step["outcome"] == "mismatch"
    assert step["mismatches"][0]["actual"] == "ACME"
    assert mismatch["assertions"][0]["status"] == "failed"


def test_scenario_routes_require_auth_and_csrf(client) -> None:
    test_client, _ = client
    source, target, contract = setup_contract(test_client)
    document = scenario_document(contract, source, target)
    no_csrf = test_client.post(
        "/api/scenarios", json={"name": "x", "category": "error", "document": document}
    )
    assert no_csrf.status_code == 403
    test_client.cookies.clear()
    assert test_client.get("/api/scenarios").status_code == 401


def test_error_response_phase_evaluates_against_error_object(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source = string_endpoint(test_client, "Order source", "reference")
    target = string_endpoint(test_client, "Order target", "order_id")
    error_object = test_client.post(
        f"/api/catalog/systems/{target['system']['id']}/objects",
        json={"name": "Order error"},
        headers=headers,
    ).json()
    error_field = test_client.post(
        f"/api/catalog/objects/{error_object['id']}/fields",
        json={"name": "error_code", "data_type": "string"},
        headers=headers,
    ).json()
    error_endpoint = {"system": target["system"], "object": error_object, "field": error_field}
    integration = create_integration(test_client, source, target, name="Order push").json()
    error_graph = field_mapping_graph(error_endpoint, source)
    error_graph["nodes"][1]["config"]["function"] = "upper"
    saved = test_client.put(
        f"/api/integrations/{integration['id']}/graph",
        json={
            "expected_revision": 1,
            "graph": field_mapping_graph(source, target),
            "response_graph": field_mapping_graph(target, source),
            "error_response_object_id": error_object["id"],
            "error_response_graph": error_graph,
            "interaction_type": "REQUEST_RESPONSE",
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    document = scenario_document(
        saved.json(),
        source,
        target,
        afterState=[],
        assertions=[],
        items=[
            {
                "kind": "contract",
                "id": "err",
                "contractId": integration["id"],
                "phase": "error-response",
                "sampleValues": {error_field["id"]: "timeout"},
                "expectedValues": {source["field"]["id"]: "TIMEOUT"},
            }
        ],
    )

    evaluated = test_client.post(
        "/api/scenarios/evaluate", json={"document": document}, headers=headers
    )
    assert evaluated.status_code == 200, evaluated.text
    step = evaluated.json()["steps"][0]
    assert step["phase"] == "error-response"
    assert step["outcome"] == "ok", step
    assert step["targetValues"] == {source["field"]["id"]: "TIMEOUT"}


def test_scenarios_are_tenant_isolated(client) -> None:
    test_client, testing_sessions = client
    source, target, contract = setup_contract(test_client)
    document = scenario_document(contract, source, target)
    created = test_client.post(
        "/api/scenarios",
        json={"name": "Private flow", "category": "happy_path", "document": document},
        headers=csrf_headers(test_client),
    )
    assert created.status_code == 201, created.text
    scenario_id = created.json()["id"]

    with testing_sessions.begin() as db:
        tenant = Tenant(name=f"scenario-outsider-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="scenario-outsider@example.test",
                password_hash=hash_password("outsider-test-password"),
            )
        )

    with TestClient(main.app) as outsider:
        csrf = outsider.get("/api/auth/csrf").json()["csrf_token"]
        login = outsider.post(
            "/api/auth/login",
            json={"email": "scenario-outsider@example.test", "password": "outsider-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert login.status_code == 200
        outsider_headers = csrf_headers(outsider)
        listed = outsider.get("/api/scenarios", params={"scope": "all"})
        by_contract = outsider.get("/api/scenarios", params={"integration_id": contract["id"]})
        fetched = outsider.get(f"/api/scenarios/{scenario_id}")
        updated = outsider.put(
            f"/api/scenarios/{scenario_id}",
            json={
                "expected_revision": 1,
                "name": "Hijacked",
                "category": "error",
                "document": document,
            },
            headers=outsider_headers,
        )
        deleted = outsider.delete(f"/api/scenarios/{scenario_id}", headers=outsider_headers)
        reused = outsider.post(
            "/api/scenarios",
            json={"name": "Borrowed", "category": "happy_path", "document": document},
            headers=outsider_headers,
        )
        evaluated = outsider.post(
            "/api/scenarios/evaluate", json={"document": document}, headers=outsider_headers
        )

    assert listed.status_code == 200 and listed.json() == []
    assert by_contract.status_code == 200 and by_contract.json() == []
    assert fetched.status_code == 404
    assert updated.status_code == 404
    assert deleted.status_code == 404
    assert reused.status_code == 422
    assert reused.json()["detail"]["code"] == "invalid_scenario_reference"
    assert evaluated.status_code == 200
    steps = evaluated.json()["steps"]
    contract_steps = [item for item in steps if item["contractId"]]
    assert contract_steps and all(item["outcome"] == "missing_reference" for item in contract_steps)
    assert all(not item.get("targetValues") for item in steps)

    owner_view = test_client.get(f"/api/scenarios/{scenario_id}")
    assert owner_view.status_code == 200
    assert owner_view.json()["name"] == "Private flow"
