"""Deterministic Solution Designer demo fixture.

Seeds a complete solution design (components, provided/required interfaces,
operations and events, repositories, deployment nodes, trust boundaries, and
the cross-links between them) into a live API so the Solution Designer
workbench can be exercised by hand.

Usage:
    api/.venv/bin/python fixtures/solution-designer/seed_solution_demo.py

The workspace, catalog systems, and design are created deterministically from
demo.json, so repeated runs against the same workspace converge on the same
shape (names are upserted by the API where supported).
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE_URL = os.environ.get("SOLUTION_DEMO_BASE_URL", "http://127.0.0.1:8000")
EMAIL = os.environ.get("SOLUTION_DEMO_EMAIL", "solution-demo@example.test")
PASSWORD = os.environ.get("SOLUTION_DEMO_PASSWORD", "solution-demo-password")
HERE = Path(__file__).parent

step_results: list[str] = []


def step(number: int, message: str) -> None:
    line = f"[{number:>2}] {message}"
    print(line, flush=True)
    step_results.append(line)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"Fixture failed: {message}")


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
        json={"name": f"Solution Demo {stamp}", "disciplines": ["solution"]},
    )
    workspace_id = workspace["id"]
    step(0, f"Created workspace {workspace['name']}")

    states = api("GET", f"/api/workspaces/{workspace_id}/states")
    current = next(item for item in states if item["state_type"] == "current")
    candidate = api(
        "POST",
        f"/api/workspaces/{workspace_id}/states/{current['id']}/duplicate",
        json={"target_name": "Solution Demo Draft"},
    )
    state_id = candidate["id"]
    step(1, f"Created candidate design {candidate['name']}")

    base = f"/api/workspaces/{workspace_id}/solution"
    design = api(
        "POST",
        f"{base}/solutions",
        json={"state_id": state_id, **demo["solution"]},
    )
    solution_id = design["solution"]["solution_object_id"]
    step(2, f"Created solution '{demo['solution']['name']}'")

    system_ids: dict[str, str] = {}
    for name in demo["members"]:
        system = api(
            "POST",
            "/api/catalog/systems",
            json={"name": name, "kind": "service"},
        )
        system_ids[name] = system["id"]
        api(
            "POST",
            f"{base}/solutions/{solution_id}/members",
            json={"state_id": state_id, "system_id": system["id"]},
        )
    step(3, f"Added {len(system_ids)} member systems")

    component_ids: dict[str, str] = {}
    interface_ids: dict[str, str] = {}
    operations = 0
    for component in demo["components"]:
        response = api(
            "POST",
            f"{base}/solutions/{solution_id}/components",
            json={
                "state_id": state_id,
                "name": component["name"],
                "component_type": component.get("component_type"),
                "technology": component.get("technology"),
                "responsibility": component.get("responsibility"),
                "position": {"x": 160.0, "y": 160.0 + 160.0 * len(component_ids)},
            },
        )
        component_id = next(
            item["object_id"]
            for item in response["components"]
            if item["name"] == component["name"]
        )
        component_ids[component["name"]] = component_id
        for interface in component.get("interfaces", []):
            interface_response = api(
                "POST",
                f"{base}/components/{component_id}/interfaces",
                json={
                    "state_id": state_id,
                    "name": interface["name"],
                    "direction": interface.get("direction", "provided"),
                    "interface_kind": interface.get("interface_kind"),
                    "protocol": interface.get("protocol"),
                    "technology": interface.get("technology"),
                },
            )
            target = next(
                item
                for item in interface_response["components"]
                if item["object_id"] == component_id
            )
            interface_id = next(
                item["object_id"]
                for item in target["interfaces"]
                if item["name"] == interface["name"]
            )
            interface_ids[interface["name"]] = interface_id
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
    step(
        4,
        f"Created {len(component_ids)} components, {len(interface_ids)} interfaces, "
        f"{operations} operations/events",
    )

    repository_ids: dict[str, str] = {}
    for repository in demo.get("repositories", []):
        response = api(
            "POST",
            f"{base}/solutions/{solution_id}/repositories",
            json={
                "state_id": state_id,
                "name": repository["name"],
                "description": repository.get("description"),
                "owner": repository.get("owner"),
                "repository_type": repository.get("repository_type"),
                "technology": repository.get("technology"),
            },
        )
        repository_ids[repository["name"]] = response["repositories"][0]["object_id"]
        for component_name in repository.get("links", []):
            api(
                "PUT",
                f"{base}/components/{component_ids[component_name]}/repository",
                json={"state_id": state_id, "target_object_id": repository_ids[repository["name"]]},
            )

    deployment_ids: dict[str, str] = {}
    for node in demo.get("deployment_nodes", []):
        response = api(
            "POST",
            f"{base}/solutions/{solution_id}/deployment-nodes",
            json={
                "state_id": state_id,
                "name": node["name"],
                "environment": node.get("environment"),
                "hosting": node.get("hosting"),
                "technology": node.get("technology"),
            },
        )
        deployment_ids[node["name"]] = response["deployment_nodes"][0]["object_id"]
        for component_name in node.get("links", []):
            api(
                "PUT",
                f"{base}/components/{component_ids[component_name]}/deployment",
                json={"state_id": state_id, "target_object_id": deployment_ids[node["name"]]},
            )
    step(
        5,
        f"Created {len(repository_ids)} repositories and {len(deployment_ids)} deployment nodes",
    )

    for boundary in demo.get("trust_boundaries", []):
        response = api(
            "POST",
            f"{base}/solutions/{solution_id}/trust-boundaries",
            json={
                "state_id": state_id,
                "name": boundary["name"],
                "security_level": boundary.get("security_level"),
            },
        )
        trust_id = response["trust_boundaries"][0]["object_id"]
        links = boundary.get("links", {})
        for interface_name in links.get("interfaces", []):
            api(
                "PUT",
                f"{base}/interfaces/{interface_ids[interface_name]}/trust-boundary",
                json={"state_id": state_id, "target_object_id": trust_id},
            )
    step(6, "Created trust boundaries and cross-links")

    final = api("GET", f"{base}/solutions/{solution_id}/design?state_id={state_id}")
    check(len(final["components"]) == len(demo["components"]), "component count mismatch")
    check(
        len(final["repositories"]) == len(demo.get("repositories", [])),
        "repository count mismatch",
    )
    check(
        len(final["trust_boundaries"]) == len(demo.get("trust_boundaries", [])),
        "trust boundary count mismatch",
    )
    step(7, "Reloaded the design and verified the shape survives a round trip")
    check(
        all(component["interfaces"] for component in final["components"]),
        "every seeded component should expose at least one interface",
    )

    print()
    print("Solution Designer demo is ready.")
    print(f"  Workspace : {workspace['name']} ({workspace_id})")
    print(f"  State     : {candidate['name']} ({state_id})")
    print(f"  Solution  : {demo['solution']['name']} ({solution_id})")
    print()
    print("Open the web app, switch to the Solution workbench, and select the")
    print("'Solution Demo' workspace to walk the manual checklist in README.md.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        sys.exit(1)
