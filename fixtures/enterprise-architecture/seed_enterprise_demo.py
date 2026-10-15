"""Deterministic Enterprise Workbench demo fixture.

Seeds a complete strategy-to-execution model (goals, requirements,
capabilities, processes/value streams, principles/constraints/risks, roles),
its supporting applications, and the typed links between them into a live API
so the Enterprise workbench can be exercised by hand.

Usage:
    api/.venv/bin/python fixtures/enterprise-architecture/seed_enterprise_demo.py

The workspace name is stamped per run, so repeated runs create fresh demo
workspaces that converge on the same model shape described by demo.json.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE_URL = os.environ.get("ENTERPRISE_DEMO_BASE_URL", "http://127.0.0.1:8000")
EMAIL = os.environ.get("ENTERPRISE_DEMO_EMAIL", "solution-demo@example.test")
PASSWORD = os.environ.get("ENTERPRISE_DEMO_PASSWORD", "solution-demo-password")
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
        json={"name": f"Enterprise Demo {stamp}", "disciplines": ["enterprise"]},
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
    step(1, f"Created candidate strategy {candidate['name']}")

    base = f"/api/workspaces/{workspace_id}/enterprise"
    object_ids: dict[str, str] = {}
    for index, obj in enumerate(demo["objects"]):
        payload = {
            "state_id": state_id,
            "kind": obj["kind"],
            "name": obj["name"],
            "description": obj.get("description"),
            "owner": obj.get("owner"),
            "outcome_metric": obj.get("outcome_metric"),
            "horizon": obj.get("horizon"),
            "process_type": obj.get("process_type"),
            "principle_type": obj.get("principle_type"),
            "rationale": obj.get("rationale"),
            "role_type": obj.get("role_type"),
            "position": {"x": 80.0, "y": 80.0 + 120.0 * index},
        }
        response = api("POST", f"{base}/objects", json=payload)
        object_ids[obj["name"]] = next(
            item["object_id"]
            for group in (
                response["goals"],
                response["requirements"],
                response["capabilities"],
                response["processes"],
                response["principles"],
                response["roles"],
            )
            for item in group
            if item["name"] == obj["name"]
        )
    step(2, f"Created {len(object_ids)} enterprise objects")

    for name in demo["applications"]:
        system = api("POST", "/api/catalog/systems", json={"name": name, "kind": "service"})
        object_ids[name] = system["id"]
    step(3, f"Created {len(demo['applications'])} supporting applications")

    created_links = 0
    for link in demo["links"]:
        response = api(
            "POST",
            f"{base}/links",
            json={
                "state_id": state_id,
                "relationship_type": link["relationship_type"],
                "source_object_id": object_ids[link["source"]],
                "target_object_id": object_ids[link["target"]],
            },
        )
        created_links = len(response["links"])
    step(4, f"Created {created_links} typed links")

    capability_map = api("GET", f"{base}/capability-map?state_id={state_id}")
    process_impact = api("GET", f"{base}/process-impact?state_id={state_id}")
    application_support = api("GET", f"{base}/application-support?state_id={state_id}")
    trace = api("GET", f"{base}/strategy-trace?state_id={state_id}")
    impact = api("GET", f"{base}/impact?state_id={state_id}")

    check(
        len(capability_map["capabilities"]) == 2,
        f"expected 2 mapped capabilities, got {len(capability_map['capabilities'])}",
    )
    check(
        all(entry["processes"] for entry in capability_map["capabilities"]),
        "every capability should map to at least one process",
    )
    check(
        len(process_impact["processes"]) == 2,
        f"expected 2 process impact rows, got {len(process_impact['processes'])}",
    )
    check(
        len(application_support["applications"]) == len(demo["applications"]),
        "application support count mismatch",
    )
    check(
        len(trace["chains"]) == 2,
        f"expected 2 strategy chains, got {len(trace['chains'])}",
    )
    check(trace["gaps"] == [], f"strategy should be complete, gaps: {trace['gaps']}")
    check(
        [change["change"] for change in impact["changes"]] and
        all(change["change"] == "added" for change in impact["changes"]),
        "candidate built on an empty current should report only additions",
    )
    step(5, "Verified all five workbench views round-trip from the API")

    print()
    print("Enterprise Workbench demo is ready.")
    print(f"  Workspace : {workspace['name']} ({workspace_id})")
    print(f"  State     : {candidate['name']} ({state_id})")
    print()
    print("Open the web app, switch to the Enterprise workbench, and select the")
    print("'Enterprise Demo' workspace to walk the manual checklist in README.md.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        sys.exit(1)
