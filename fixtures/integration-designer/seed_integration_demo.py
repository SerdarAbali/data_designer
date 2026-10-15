"""Deterministic Integration Designer demo fixture.

Seeds an integration contract (systems, objects, fields, a solution component
with provided/required interfaces and operations, the request/response graphs,
operating properties, and reference scenarios) into a live API so the
Integration Designer workbench can be exercised by hand.

Usage:
    api/.venv/bin/python fixtures/integration-designer/seed_integration_demo.py

The workspace is stamped per run, so repeated runs create fresh demo
workspaces that converge on the same shape described by demo.json.
"""

import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

BASE_URL = os.environ.get("INTEGRATION_DEMO_BASE_URL", "http://127.0.0.1:8000")
EMAIL = os.environ.get("INTEGRATION_DEMO_EMAIL", "solution-demo@example.test")
PASSWORD = os.environ.get("INTEGRATION_DEMO_PASSWORD", "solution-demo-password")
HERE = Path(__file__).parent

step_results: list[str] = []


def step(number: int, message: str) -> None:
    line = f"[{number:>2}] {message}"
    print(line, flush=True)
    step_results.append(line)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"Fixture failed: {message}")


def mapping_graph(mappings: list[dict], resolve: dict[str, str]) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    source_node = str(uuid4())
    nodes.append({"id": source_node, "type": "source", "position": {"x": 0, "y": 0}})
    target_node = str(uuid4())
    nodes.append({"id": target_node, "type": "target", "position": {"x": 420, "y": 0}})
    for index, mapping in enumerate(mappings):
        transform = str(uuid4())
        nodes.append(
            {
                "id": transform,
                "type": "fx",
                "position": {"x": 210, "y": 90 * index},
                "config": {"function": mapping.get("transform", "trim")},
            }
        )
        edges.append(
            {
                "id": str(uuid4()),
                "sourceNodeId": source_node,
                "sourcePortId": f"field:{resolve[mapping['source']]}",
                "targetNodeId": transform,
                "targetPortId": "input",
            }
        )
        edges.append(
            {
                "id": str(uuid4()),
                "sourceNodeId": transform,
                "sourcePortId": "output",
                "targetNodeId": target_node,
                "targetPortId": f"field:{resolve[mapping['target']]}",
            }
        )
    return {"version": 1, "nodes": nodes, "edges": edges}


def main() -> int:
    demo = json.loads((HERE / "demo.json").read_text())

    client = httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=True)
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    login = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    check(login.status_code == 200, f"login failed: {login.status_code} {login.text}")
    token = client.cookies["dd_csrf"]

    def api(method: str, path: str, **kwargs):
        headers = {"X-CSRF-Token": token} if method != "GET" else {}
        response = client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise AssertionError(f"{method} {path} -> {response.status_code}: {response.text}")
        return response.json() if response.content else None

    stamp = time.strftime("%H%M%S")
    workspace = api(
        "POST",
        "/api/workspaces",
        json={
            "name": f"Integration Demo {stamp}",
            "disciplines": demo["disciplines"],
        },
    )
    workspace_id = workspace["id"]
    step(0, f"Created workspace {workspace['name']}")

    states = api("GET", f"/api/workspaces/{workspace_id}/states")
    current = next(item for item in states if item["state_type"] == "current")
    candidate = api(
        "POST",
        f"/api/workspaces/{workspace_id}/states/{current['id']}/duplicate",
        json={"target_name": demo["candidate_name"]},
    )
    state_id = candidate["id"]
    step(1, f"Created candidate state {candidate['name']}")

    systems: dict[str, str] = {}
    objects: dict[str, str] = {}
    fields: dict[str, str] = {}
    for system in demo["systems"]:
        created = api(
            "POST",
            "/api/catalog/systems",
            json={"name": system["name"], "kind": system.get("kind", "custom platform")},
        )
        systems[system["key"]] = created["id"]
        for obj in system["objects"]:
            created_object = api(
                "POST",
                f"/api/catalog/systems/{created['id']}/objects",
                json={"name": obj["name"]},
            )
            objects[obj["key"]] = created_object["id"]
            for field in obj["fields"]:
                created_field = api(
                    "POST",
                    f"/api/catalog/objects/{created_object['id']}/fields",
                    json={"name": field["name"], "data_type": field["data_type"]},
                )
                fields[field["key"]] = created_field["id"]
    step(2, f"Created {len(systems)} systems, {len(objects)} objects, {len(fields)} fields")

    base = f"/api/workspaces/{workspace_id}/solution"
    design = api("POST", f"{base}/solutions", json={"state_id": state_id, **demo["solution"]})
    solution_id = design["solution"]["solution_object_id"]
    component_ids: dict[str, str] = {}
    for component in demo["solution"]["components"]:
        response = api(
            "POST",
            f"{base}/solutions/{solution_id}/components",
            json={
                "state_id": state_id,
                "name": component["name"],
                "component_type": component.get("component_type"),
                "technology": component.get("technology"),
                "responsibility": component.get("responsibility"),
                "position": {"x": 160.0, "y": 160.0},
            },
        )
        component_ids[component["key"]] = next(
            item["object_id"]
            for item in response["components"]
            if item["name"] == component["name"]
        )

    interface_ids: dict[str, str] = {}
    operations = 0
    for interface in demo["interfaces"]:
        component_id = component_ids[interface["component"]]
        response = api(
            "POST",
            f"{base}/components/{component_id}/interfaces",
            json={
                "state_id": state_id,
                "name": interface["name"],
                "direction": interface.get("direction", "provided"),
                "interface_kind": interface.get("interface_kind"),
                "protocol": interface.get("protocol"),
            },
        )
        target_component = next(
            item for item in response["components"] if item["object_id"] == component_id
        )
        interface_id = next(
            item["object_id"]
            for item in target_component["interfaces"]
            if item["name"] == interface["name"]
        )
        interface_ids[interface["key"]] = interface_id
        for operation in interface.get("operations", []):
            api(
                "POST",
                f"{base}/interfaces/{interface_id}/operations",
                json={
                    "state_id": state_id,
                    "name": operation["name"],
                    "operation_kind": operation.get("operation_kind", "operation"),
                },
            )
            operations += 1
    step(3, f"Created {len(interface_ids)} interfaces and {operations} operations/events")

    contract_demo = demo["contract"]
    request_graph = mapping_graph(contract_demo["mappings"], fields)
    response_graph = mapping_graph(contract_demo["response_mappings"], fields)
    source_field = fields[contract_demo["source"]["field"]]
    created = api(
        "POST",
        "/api/integrations",
        json={
            "source_system_id": systems[contract_demo["source"]["system"]],
            "source_object_id": objects[contract_demo["source"]["object"]],
            "target_system_id": systems[contract_demo["target"]["system"]],
            "target_object_id": objects[contract_demo["target"]["object"]],
            "name": contract_demo["name"],
            "description": contract_demo.get("description"),
            "interaction_type": contract_demo["interaction_type"],
            "graph": request_graph,
            "response_graph": response_graph,
            "sample_rows": [{"rowId": "sample-1", "values": {source_field: "acme"}}],
        },
    )
    contract_id = created["id"]

    specification = dict(contract_demo["specification"])
    key = specification.get("idempotency_key_field_id")
    if key:
        specification["idempotency_key_field_id"] = fields[key]
    api(
        "PATCH",
        f"/api/integrations/{contract_id}",
        json={
            "expected_revision": created["revision"],
            "pattern": contract_demo["pattern"],
            "implementation_status": contract_demo["implementation_status"],
            "producer_interface_id": interface_ids[contract_demo["producer_interface"]],
            "consumer_interface_id": interface_ids[contract_demo["consumer_interface"]],
            "specification": specification,
        },
    )
    step(4, f"Created contract '{contract_demo['name']}' with operating properties")

    source_system = systems[contract_demo["source"]["system"]]
    target_system = systems[contract_demo["target"]["system"]]
    target_field = fields[contract_demo["target"]["field"]]
    for scenario in demo["scenarios"]:
        document = {
            "version": 1,
            "participants": [
                {"id": "user", "kind": "actor", "label": "Operator"},
                {"id": "src", "kind": "system", "systemId": source_system},
                {"id": "tgt", "kind": "system", "systemId": target_system},
            ],
            "beforeState": [],
            "afterState": [],
            "items": [
                {
                    "kind": "contract",
                    "id": "s1",
                    "contractId": contract_id,
                    "phase": scenario["phase"],
                    "sampleValues": {
                        source_field: scenario["sample_values"]["customer_name"]
                    },
                    "expectedValues": {
                        target_field: scenario["expected_values"]["account_code"]
                    },
                }
            ],
            "assertions": [],
            "notes": "",
        }
        api(
            "POST",
            "/api/scenarios",
            json={
                "scope_integration_id": contract_id,
                "name": scenario["name"],
                "category": scenario["category"],
                "document": document,
            },
        )
    step(5, f"Created {len(demo['scenarios'])} reference scenarios")

    landscape = api(
        "GET",
        f"/api/workspaces/{workspace_id}/integration-design/landscape?state_id={state_id}",
    )
    check(len(landscape["contracts"]) == 1, "expected exactly one contract in the landscape")
    conformance = api(
        "GET",
        f"/api/workspaces/{workspace_id}/integration-design/contracts/{contract_id}"
        f"/conformance?state_id={state_id}",
    )
    check(len(conformance["scenarios"]) == len(demo["scenarios"]), "scenario count mismatch")
    step(
        6,
        "Reloaded the landscape and conformance view "
        f"(statuses: {conformance['summary']})",
    )

    print()
    print("Integration Designer demo is ready.")
    print(f"  Workspace : {workspace['name']} ({workspace_id})")
    print(f"  State     : {candidate['name']} ({state_id})")
    print(f"  Contract  : {contract_demo['name']} ({contract_id})")
    print()
    print("Open the web app, switch to the Integration workbench, and select the")
    print("'Integration Demo' workspace to walk the manual checklist in README.md.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        sys.exit(1)
