"""End-to-end verification of the Phase 3 guided import flow.

Runs the twelve verification steps against a live API (default
http://127.0.0.1:8000) using the sample files in this directory.

Usage:
    api/.venv/bin/python fixtures/architecture-import/verify_import_flow.py
"""

import csv
import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
EMAIL = "import-verify@example.test"
PASSWORD = "import-verify-password"
HERE = Path(__file__).parent

MAPPINGS = {
    "system": {
        "name": "Name",
        "description": "Description",
        "owner": "Owner",
        "business_domain": "Domain",
        "lifecycle": "Lifecycle",
        "status": "Status",
        "technology": "Technology",
        "external_id": "External ID",
        "aliases": "Aliases",
    },
    "information_object": {
        "name": "Name",
        "description": "Description",
        "owner": "Owner",
        "authoritative_system": "Authoritative System",
        "classification": "Classification",
        "external_id": "External ID",
    },
    "integration": {
        "name": "Name",
        "description": "Description or purpose",
        "source_system": "Source System",
        "target_system": "Target System",
        "source_object": "Source Object",
        "target_object": "Target Object",
        "integration_type": "Integration Type",
        "owner": "Owner",
        "lifecycle": "Lifecycle",
        "external_id": "External ID",
        "contract_reference": "Existing contract reference",
    },
    "solution": {
        "name": "Solution name",
        "description": "Description",
        "owner": "Owner",
        "external_id": "External ID",
        "included_systems": "Included systems",
    },
}

step_results: list[str] = []


def step(number: int, message: str) -> None:
    line = f"[{number:>2}] {message}"
    print(line, flush=True)
    step_results.append(line)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"Verification failed: {message}")


def read_fixture(name: str) -> tuple[str, list[str], list[list[str]]]:
    with (HERE / name).open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.reader(handle) if any(cell.strip() for cell in row)]
    return name, rows[0], rows[1:]


def main() -> int:
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
    workspace = api("POST", "/api/workspaces", json={"name": f"Phase 3 Verification {stamp}"})
    workspace_id = workspace["id"]
    step(0, f"Created verification workspace {workspace['name']}")

    # Current architecture starts empty so we can prove nothing is auto-placed.
    states = api("GET", f"/api/workspaces/{workspace_id}/states")
    current = next(item for item in states if item["state_type"] == "current")
    check(current["nodes"] == [], "Current state should start empty")

    # Existing catalog records the import must match, update, or skip.
    api(
        "POST",
        "/api/catalog/systems",
        json={
            "name": "Customer CRM",
            "external_identifier": "SYS-CRM",
            "metadata": {"aliases": ["Customer Relationship Mgmt"]},
        },
    )
    api(
        "POST",
        "/api/catalog/systems",
        json={"name": "Billing Platform", "description": "Legacy billing"},
    )

    systems_file, systems_headers, systems_rows = read_fixture("systems.csv")
    systems_body = {
        "import_type": "system",
        "headers": systems_headers,
        "rows": systems_rows,
        "column_mapping": MAPPINGS["system"],
        "source_filename": systems_file,
        "sheet_name": "CSV",
    }

    preview = api("POST", f"/api/workspaces/{workspace_id}/imports/preview", json=systems_body)
    methods = [row["matches"][0]["method"] if row["matches"] else "none" for row in preview["rows"]]
    check(methods[1] == "external_id", f"row 2 should match by external ID, got {methods[1]}")
    check(methods[2] == "exact_name", f"row 3 should match by name, got {methods[2]}")
    step(1, f"Previewed {len(preview['rows'])} system rows; matches: {methods}")

    decisions = [
        {"row_number": 1, "decision": "create"},
        {"row_number": 2, "decision": "use_existing"},
        {"row_number": 3, "decision": "update"},
        {"row_number": 4, "decision": "skip"},
    ]
    systems_batch = api(
        "POST",
        f"/api/workspaces/{workspace_id}/imports/commit",
        json={**systems_body, "decisions": decisions},
    )
    counts = systems_batch["counts"]
    check(counts["created"] == 1, f"expected 1 created, got {counts}")
    check(counts["matched"] == 1, f"expected 1 matched, got {counts}")
    check(counts["updated"] == 1, f"expected 1 updated, got {counts}")
    check(counts["skipped"] == 1, f"expected 1 skipped, got {counts}")
    step(2, f"Matched one row to an existing system: {counts}")
    step(3, f"Created one new system: {counts['created']}")
    step(4, f"Updated one existing system: {counts['updated']}")
    step(5, f"Skipped one row: {counts['skipped']}")

    systems = api("GET", "/api/catalog/systems")
    names = {item["name"] for item in systems}
    check("Payment Gateway" in names, "new system should exist")
    billing = next(item for item in systems if item["name"] == "Billing Platform")
    check(billing["description"] != "Legacy billing", "billing should have been updated")

    states = api("GET", f"/api/workspaces/{workspace_id}/states")
    current = next(item for item in states if item["state_type"] == "current")
    check(current["nodes"] == [], "import must not place objects on the canvas automatically")
    step(6, "Confirmed the import did not place anything on the Current canvas")

    info_file, info_headers, info_rows = read_fixture("information-objects.csv")
    info_body = {
        "import_type": "information_object",
        "headers": info_headers,
        "rows": info_rows,
        "column_mapping": MAPPINGS["information_object"],
        "source_filename": info_file,
        "sheet_name": "CSV",
    }
    info_preview = api("POST", f"/api/workspaces/{workspace_id}/imports/preview", json=info_body)
    check(
        info_preview["resolved_reference_counts"]["authoritative_systems_resolved"] == 3,
        f"expected 3 resolved authoritative systems, got {info_preview['resolved_reference_counts']}",
    )
    info_batch = api(
        "POST",
        f"/api/workspaces/{workspace_id}/imports/commit",
        json={
            **info_body,
            "decisions": [
                {"row_number": 1, "decision": "create"},
                {"row_number": 2, "decision": "create"},
                {"row_number": 3, "decision": "create"},
                {"row_number": 4, "decision": "create"},
            ],
        },
    )
    check(info_batch["counts"]["created"] == 3, f"expected 3 created, got {info_batch['counts']}")
    check(info_batch["counts"]["blocked"] == 1, f"expected 1 blocked, got {info_batch['counts']}")
    step(
        7,
        "Imported information objects with an authoritative system resolved by alias; "
        f"one unresolved row blocked: {info_batch['counts']}",
    )

    systems = api("GET", "/api/catalog/systems")
    by_name = {item["name"]: item for item in systems}
    created_objects: dict[str, dict] = {}
    for system_name, object_name in (
        ("Customer CRM", "Customer"),
        ("Billing Platform", "Invoice"),
        ("Payment Gateway", "Settlement"),
    ):
        created_objects[system_name] = api(
            "POST",
            f"/api/catalog/systems/{by_name[system_name]['id']}/objects",
            json={"name": object_name, "label": object_name},
        )

    # A contract that already exists, so the import must update instead of duplicating it.
    existing_contract = api(
        "POST",
        "/api/integrations",
        json={
            "source_system_id": by_name["Customer CRM"]["id"],
            "source_object_id": created_objects["Customer CRM"]["id"],
            "target_system_id": by_name["Billing Platform"]["id"],
            "target_object_id": created_objects["Billing Platform"]["id"],
            "name": "CRM to Billing",
            "description": "Nightly export",
        },
    )

    integration_file, integration_headers, integration_rows = read_fixture("integrations.csv")
    integration_body = {
        "import_type": "integration",
        "headers": integration_headers,
        "rows": integration_rows,
        "column_mapping": MAPPINGS["integration"],
        "source_filename": integration_file,
        "sheet_name": "CSV",
    }
    integration_preview = api(
        "POST", f"/api/workspaces/{workspace_id}/imports/preview", json=integration_body
    )
    check(
        integration_preview["rows"][0]["matches"][0]["id"] == existing_contract["id"],
        "row 1 should match the existing contract",
    )
    integration_batch = api(
        "POST",
        f"/api/workspaces/{workspace_id}/imports/commit",
        json={
            **integration_body,
            "decisions": [
                {
                    "row_number": 1,
                    "decision": "update",
                    "target_id": existing_contract["id"],
                },
                {"row_number": 2, "decision": "create"},
                {"row_number": 3, "decision": "create"},
            ],
        },
    )
    check(
        integration_batch["counts"]["created"] == 1,
        f"expected 1 new integration, got {integration_batch['counts']}",
    )
    check(
        integration_batch["counts"]["updated"] == 1,
        f"expected the existing contract to update, got {integration_batch['counts']}",
    )
    check(
        integration_batch["counts"]["blocked"] == 1,
        f"expected the unresolved endpoint row to block, got {integration_batch['counts']}",
    )
    contracts = api("GET", "/api/integrations")
    check(len(contracts) == 2, f"the existing contract must not be duplicated, got {len(contracts)}")
    refreshed_contract = next(item for item in contracts if item["id"] == existing_contract["id"])
    check(
        refreshed_contract["description"] != "Nightly export",
        "the existing contract should have been updated",
    )
    blocked_row = next(row for row in integration_batch["rows"] if row["status"] == "blocked")
    step(
        8,
        "Imported integrations whose endpoints resolve to canonical systems; updated the existing "
        f"contract instead of duplicating it; blocked row: {blocked_row['message']}",
    )

    solution_file, solution_headers, solution_rows = read_fixture("solutions.csv")
    solution_body = {
        "import_type": "solution",
        "headers": solution_headers,
        "rows": solution_rows,
        "column_mapping": MAPPINGS["solution"],
        "source_filename": solution_file,
        "sheet_name": "CSV",
    }
    solution_batch = api(
        "POST",
        f"/api/workspaces/{workspace_id}/imports/commit",
        json={
            **solution_body,
            "decisions": [
                {"row_number": 1, "decision": "create"},
                {"row_number": 2, "decision": "create"},
            ],
        },
    )
    check(solution_batch["counts"]["created"] == 1, f"expected 1 solution, got {solution_batch['counts']}")
    check(solution_batch["counts"]["blocked"] == 1, f"expected 1 blocked, got {solution_batch['counts']}")
    systems_after = api("GET", "/api/catalog/systems")
    check(
        {item["name"] for item in systems_after} == {item["name"] for item in systems},
        "solution import must not create system copies",
    )
    step(9, f"Imported a solution over existing canonical systems: {solution_batch['counts']}")

    reimport = api(
        "POST",
        f"/api/workspaces/{workspace_id}/imports/commit",
        json={
            **systems_body,
            "decisions": [
                {"row_number": 1, "decision": "use_existing"},
                {"row_number": 2, "decision": "use_existing"},
                {"row_number": 3, "decision": "use_existing"},
                {"row_number": 4, "decision": "skip"},
            ],
        },
    )
    check(reimport["counts"]["created"] == 0, f"re-import created duplicates: {reimport['counts']}")
    check(reimport["counts"]["matched"] == 3, f"re-import should match every known row: {reimport['counts']}")
    check(reimport["counts"]["skipped"] == 1, f"re-import should skip the skipped row: {reimport['counts']}")
    systems_again = api("GET", "/api/catalog/systems")
    check(
        len(systems_again) == len(systems_after),
        "re-import must not create duplicate systems",
    )
    step(10, f"Re-imported the same file: {reimport['counts']} (no duplicates)")

    systems = api("GET", "/api/catalog/systems")
    by_name = {item["name"]: item for item in systems}
    integrations = api("GET", "/api/integrations")
    billing_to_gateway = next(item for item in integrations if item["name"] == "Billing to Gateway")
    architecture_objects = api("GET", f"/api/workspaces/{workspace_id}/architecture-objects")
    solution_id = next(
        item["id"] for item in architecture_objects if item["kind"] == "solution_boundary"
    )
    selected_systems = [
        by_name["Customer CRM"]["id"],
        by_name["Billing Platform"]["id"],
        by_name["Payment Gateway"]["id"],
    ]
    include_body = {
        "system_ids": selected_systems,
        "architecture_object_ids": [solution_id],
        "integration_ids": [billing_to_gateway["id"]],
        "visualize_solution_membership": True,
    }
    included = api(
        "POST",
        f"/api/workspaces/{workspace_id}/states/{current['id']}/include-objects",
        json=include_body,
    )
    check(included["added_occurrences"] == 4, f"expected 4 occurrences, got {included['added_occurrences']}")
    check(
        included["added_relationships"] == 3,
        f"expected 2 containment links and 1 contract link, got {included['added_relationships']}",
    )
    node_objects = {node["object_id"] for node in included["state"]["nodes"]}
    check(
        node_objects == {*selected_systems, solution_id},
        "only the selected objects may be placed on the canvas",
    )
    step(
        11,
        "Enriched Current architecture with the selected imported objects: "
        f"{included['added_occurrences']} objects, {included['added_relationships']} relationships",
    )

    refreshed = api("GET", f"/api/workspaces/{workspace_id}/imports")
    check(len(refreshed) >= 4, f"expected the import history to persist, got {len(refreshed)}")
    detail = api("GET", f"/api/workspaces/{workspace_id}/imports/{systems_batch['id']}")
    check(detail["source_filename"] == systems_file, "provenance should persist")
    check(
        any(row["external_id"] == "SYS-CRM" for row in detail["rows"]),
        "row provenance should persist",
    )
    states = api("GET", f"/api/workspaces/{workspace_id}/states")
    current = next(item for item in states if item["state_type"] == "current")
    check(len(current["nodes"]) == 4, "Current membership should persist")
    step(12, "Refreshed: imported records, provenance, and Current membership persist")

    # Undo is conservative: the created system is still referenced by a contract
    # from another batch, so that row is reported as a conflict instead of deleted.
    protected = api("POST", f"/api/workspaces/{workspace_id}/imports/{systems_batch['id']}/undo")
    check(protected["status"] == "undo_blocked", f"expected a guarded undo, got {protected['status']}")
    conflict = next(row for row in protected["rows"] if row["status"] == "conflict")
    check("Billing to Gateway" in conflict["message"], f"unexpected conflict message: {conflict}")
    systems = api("GET", "/api/catalog/systems")
    names = {item["name"] for item in systems}
    check("Payment Gateway" in names, "a referenced created system must not be deleted")
    billing = next(item for item in systems if item["name"] == "Billing Platform")
    check(billing["description"] == "Legacy billing", "the update must still be reversed")
    step(13, f"Guarded undo reported the conflict instead of deleting a referenced record: {conflict['message']}")

    # Undoing the contract batch first frees the system, so the same batch can complete.
    contracts_undo = api(
        "POST", f"/api/workspaces/{workspace_id}/imports/{integration_batch['id']}/undo"
    )
    check(contracts_undo["status"] == "undone", f"contract undo failed: {contracts_undo['status']}")
    contracts = api("GET", "/api/integrations")
    check(
        all(item["name"] != "Billing to Gateway" for item in contracts),
        "the created contract should be removed by its batch undo",
    )
    check(
        any(item["id"] == existing_contract["id"] for item in contracts),
        "the updated contract must be restored, not deleted",
    )

    # The system is also the authoritative system of an imported information object,
    # so that batch must be undone before the system batch can complete.
    for dependent_batch in (info_batch, solution_batch):
        dependent_undo = api(
            "POST", f"/api/workspaces/{workspace_id}/imports/{dependent_batch['id']}/undo"
        )
        check(
            dependent_undo["status"] == "undone",
            f"dependent batch undo failed: {dependent_undo['status']}",
        )

    undone = api("POST", f"/api/workspaces/{workspace_id}/imports/{systems_batch['id']}/undo")
    check(undone["status"] == "undone", f"undo failed: {undone}")
    systems = api("GET", "/api/catalog/systems")
    names = {item["name"] for item in systems}
    check("Payment Gateway" not in names, "the created system should be removed by undo")
    billing = next(item for item in systems if item["name"] == "Billing Platform")
    check(billing["description"] == "Legacy billing", "undo should restore the previous values")
    check("Customer CRM" in names, "matched records must survive the undo")
    states = api("GET", f"/api/workspaces/{workspace_id}/states")
    current = next(item for item in states if item["state_type"] == "current")
    node_objects = {node["object_id"] for node in current["nodes"]}
    check(
        by_name["Payment Gateway"]["id"] not in node_objects,
        "undo should remove the placement of the reversed system",
    )
    check(
        by_name["Customer CRM"]["id"] in node_objects,
        "other placements must be untouched",
    )
    info_objects = api("GET", f"/api/workspaces/{workspace_id}/architecture-objects")
    check(
        all(item["kind"] != "information_object" for item in info_objects),
        "the information-object batch must be reversed by its own undo",
    )
    step(
        14,
        "Undid each batch in turn: created system removed, update restored, "
        "dependents reversed, unrelated records intact",
    )

    print("\nVerification complete:")
    for line in step_results:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as error:
        print(f"\nFAILED: {error}", file=sys.stderr)
        sys.exit(1)
