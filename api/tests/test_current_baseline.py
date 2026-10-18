"""Slice 8C: editable Current baseline capture and irreversible locking.

Risk-based coverage of the lifecycle: creation options, the one write policy, the
lock endpoint and its bounded validation, Assistant safety, Excel and bundle
protection, and the migration. Representative writes are parameterized rather
than repeated per route.
"""

from __future__ import annotations

import contextlib
import io
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import ArchitectureState, Tenant, User

ALL_DISCIPLINES = ["enterprise", "information", "solution", "integration"]


# --- fixtures -----------------------------------------------------------------


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
        tenant = Tenant(name=f"baseline-test-{uuid4()}")
        db.add(tenant)
        db.flush()
        user = User(
            tenant_id=tenant.id,
            email="baseline@example.test",
            password_hash=hash_password("baseline-test-password"),
        )
        db.add(user)
        db.flush()
        user_id = user.id
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "baseline@example.test", "password": "baseline-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions, user_id
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _workspace(test_client, headers, **payload) -> dict:
    body = {"name": f"Baseline {uuid4().hex[:6]}", "disciplines": ALL_DISCIPLINES, **payload}
    response = test_client.post("/api/workspaces", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _states(test_client, workspace_id: str) -> list[dict]:
    response = test_client.get(f"/api/workspaces/{workspace_id}/states")
    assert response.status_code == 200, response.text
    return response.json()


def _state_of(test_client, workspace_id: str, state_type: str) -> dict:
    return next(
        state for state in _states(test_client, workspace_id) if state["state_type"] == state_type
    )


def _lock(
    test_client, workspace_id: str, state_id: str, headers, **payload
) -> tuple[int, dict]:
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/states/{state_id}/lock-baseline",
        json=payload,
        headers=headers,
    )
    return response.status_code, response.json()


def _representative_write(test_client, headers, workspace_id: str, state_id: str):
    """One structural write through a normal workbench surface.

    Inclusion is the reviewed Catalog path into a state, so it exercises the
    shared policy without inventing an architecture object.
    """
    system = test_client.post(
        "/api/catalog/systems",
        json={"name": f"System {uuid4().hex[:6]}", "kind": "application"},
        headers=headers,
    )
    assert system.status_code == 201, system.text
    return test_client.post(
        f"/api/workspaces/{workspace_id}/states/{state_id}/include-objects",
        json={"system_ids": [system.json()["id"]]},
        headers=headers,
    )


# --- 1/2: creation options ----------------------------------------------------


def test_current_draft_option_starts_an_editable_draft(client) -> None:
    test_client, sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)

    current = _state_of(test_client, workspace["id"], "current")
    assert current["baseline_status"] == "draft"
    assert current["baseline_locked_at"] is None
    assert current["baseline_locked_by"] is None

    accepted = _representative_write(test_client, headers, workspace["id"], current["id"])
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["added_occurrences"] == 1

    # Nothing recorded a lock just because the state exists.
    with sessions() as db:
        row = db.get(ArchitectureState, UUID(current["id"]))
        assert row.baseline_status == "draft"
        assert row.baseline_locked_at is None


def test_candidate_starter_creates_an_editable_draft_and_a_candidate(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers, baseline="candidate_starter")

    current = _state_of(test_client, workspace["id"], "current")
    candidate = _state_of(test_client, workspace["id"], "candidate")
    # Current is a draft, exactly like the Current-baseline option: a new manual
    # workspace never starts with a locked baseline.
    assert current["baseline_status"] == "draft"
    assert current["baseline_locked_at"] is None
    assert current["baseline_locked_by"] is None
    assert candidate["baseline_status"] is None

    current_write = _representative_write(test_client, headers, workspace["id"], current["id"])
    assert current_write.status_code == 200, current_write.text
    candidate_write = _representative_write(
        test_client, headers, workspace["id"], candidate["id"]
    )
    assert candidate_write.status_code == 200, candidate_write.text


def test_current_baseline_draft_option_creates_no_candidate(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    states = _states(test_client, workspace["id"])
    assert [state["state_type"] for state in states] == ["current"]
    assert states[0]["baseline_status"] == "draft"


@pytest.mark.parametrize("baseline", ["current_draft", "candidate_starter"])
def test_no_manual_workspace_starts_with_a_locked_current(client, baseline) -> None:
    test_client, sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers, baseline=baseline)
    _states(test_client, workspace["id"])  # materialises the baseline

    with sessions() as db:
        currents = list(
            db.scalars(
                select(ArchitectureState).where(
                    ArchitectureState.workspace_id == UUID(workspace["id"]),
                    ArchitectureState.state_type == "current",
                )
            )
        )
    assert currents
    for current in currents:
        assert current.baseline_status == "draft", baseline
        assert current.baseline_locked_at is None
        assert current.baseline_locked_by is None


def test_demo_provided_current_stays_locked(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers, demo_preset="full")
    current = _state_of(test_client, workspace["id"], "current")
    # The demo supplies Current content, so it is a captured baseline.
    assert current["baseline_status"] == "locked"
    assert current["nodes"]

    blocked = _representative_write(test_client, headers, workspace["id"], current["id"])
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "current_baseline_locked"


# --- 3/4/10/14: the one write policy -----------------------------------------


@pytest.mark.parametrize(
    ("state_type", "status", "expected"),
    [
        ("current", "draft", 200),
        ("current", "locked", 409),
        ("candidate", None, 200),
        ("target", None, 200),
    ],
)
def test_write_policy_is_one_rule_for_every_state_type(
    client, state_type, status, expected
) -> None:
    test_client, sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")
    state_id = current["id"]
    if state_type != "current":
        duplicate = test_client.post(
            f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
            json={"target_name": f"{state_type} state", "target_state_type": state_type},
            headers=headers,
        )
        assert duplicate.status_code == 201, duplicate.text
        state_id = duplicate.json()["id"]
    elif status == "locked":
        code, body = _lock(
            test_client, workspace["id"], state_id, headers, confirm_empty=True
        )
        assert code == 200, body

    response = _representative_write(test_client, headers, workspace["id"], state_id)
    assert response.status_code == expected, response.text
    if expected == 409:
        assert response.json()["detail"]["code"] == "current_baseline_locked"
        assert "locked" in response.json()["detail"]["message"].lower()

    # Candidate and Target never carry a baseline status.
    if state_type != "current":
        with sessions() as db:
            assert db.get(ArchitectureState, UUID(state_id)).baseline_status is None


def test_locking_changes_effective_write_behaviour_immediately(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    before = _representative_write(test_client, headers, workspace["id"], current["id"])
    assert before.status_code == 200, before.text

    code, _body = _lock(test_client, workspace["id"], current["id"], headers, confirm_empty=True)
    assert code == 200

    after = _representative_write(test_client, headers, workspace["id"], current["id"])
    assert after.status_code == 409
    assert after.json()["detail"]["code"] == "current_baseline_locked"

    # A locked baseline is still fully readable.
    assert _states(test_client, workspace["id"])
    assert after.json()["detail"]["message"]


# --- 5: Assistant safety ------------------------------------------------------


def test_assistant_scan_never_exposes_proposals_for_a_current_baseline() -> None:
    from app.assistant import tools

    # No Current state exposes a proposal tool, whatever the baseline status or
    # the enabled disciplines — the Assistant gate is independent of the lock.
    for discipline_set in ([], ["enterprise"], ALL_DISCIPLINES):
        names = tools.allowed_tool_names(discipline_set, "current")
        assert not [name for name in names if "propose_" in name], discipline_set
    # Proposals remain available for the editable states, unchanged by this slice.
    for state_type in ("candidate", "target"):
        assert [
            name
            for name in tools.allowed_tool_names(ALL_DISCIPLINES, state_type)
            if "propose_" in name
        ]


def test_locking_is_not_reachable_from_the_model_surface() -> None:
    from app.assistant import tools

    manifest = {entry["name"] for entry in tools.plugin_manifest()}
    assert not [name for name in manifest if "lock" in name or "baseline" in name]
    assert "lock_baseline" not in tools.FORBIDDEN_TOOL_NAMES
    # The forbidden set still fences the surface the model must never reach.
    assert {"apply_change_set", "undo_change_set", "write", "execute"}.issubset(
        tools.FORBIDDEN_TOOL_NAMES
    )


# --- 6/7/8/9: the lock endpoint ----------------------------------------------


def test_lock_records_server_controlled_user_and_timestamp(client) -> None:
    test_client, sessions, user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    code, body = _lock(test_client, workspace["id"], current["id"], headers, confirm_empty=True)
    assert code == 200, body
    assert body["locked"] is True
    assert body["state"]["baseline_status"] == "locked"
    assert body["state"]["baseline_locked_by"] == str(user_id)
    assert body["state"]["baseline_locked_at"]

    with sessions() as db:
        row = db.get(ArchitectureState, UUID(current["id"]))
        assert row.baseline_locked_by == user_id
        assert row.baseline_locked_at is not None
        assert row.baseline_status == "locked"

    # Client-supplied lock metadata is refused outright, not ignored.
    other = _workspace(test_client, headers)
    other_current = _state_of(test_client, other["id"], "current")
    rejected = test_client.post(
        f"/api/workspaces/{other['id']}/states/{other_current['id']}/lock-baseline",
        json={"confirm_empty": True, "baseline_locked_by": str(uuid4())},
        headers=headers,
    )
    assert rejected.status_code == 422, rejected.text


@pytest.mark.parametrize("state_type", ["candidate", "target"])
def test_only_a_current_state_can_be_locked(client, state_type) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")
    duplicate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": f"{state_type} state", "target_state_type": state_type},
        headers=headers,
    )
    assert duplicate.status_code == 201, duplicate.text

    code, body = _lock(
        test_client, workspace["id"], duplicate.json()["id"], headers, confirm_empty=True
    )
    assert code == 422, body
    assert body["detail"]["code"] == "not_current_state"


def test_an_already_locked_baseline_conflicts_with_clear_metadata(client) -> None:
    test_client, _sessions, user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    first = _lock(test_client, workspace["id"], current["id"], headers, confirm_empty=True)
    assert first[0] == 200

    code, body = _lock(test_client, workspace["id"], current["id"], headers, confirm_empty=True)
    assert code == 409, body
    assert body["detail"]["code"] == "baseline_already_locked"
    assert body["detail"]["baseline_locked_by"] == str(user_id)
    assert body["detail"]["baseline_locked_at"]


def test_empty_baseline_requires_explicit_confirmation(client) -> None:
    test_client, sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    refused = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/lock-baseline",
        json={"confirm_empty": False},
        headers=headers,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "baseline_confirmation_required"
    assert any(
        issue["code"] == "empty_baseline"
        for issue in refused.json()["detail"]["validation"]["warnings"]
    )
    with sessions() as db:
        assert db.get(ArchitectureState, UUID(current["id"])).baseline_status == "draft"

    confirmed = _lock(
        test_client, workspace["id"], current["id"], headers, confirm_empty=True
    )
    assert confirmed[0] == 200, confirmed


def test_lock_validation_reports_warnings_and_lists_them_for_review(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    system = test_client.post(
        "/api/catalog/systems",
        json={"name": "Legacy ERP", "kind": "erp"},
        headers=headers,
    ).json()
    added = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/include-objects",
        json={"system_ids": [system["id"]]},
        headers=headers,
    )
    assert added.status_code == 200, added.text

    preview = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/lock-baseline",
        json={"validate_only": True},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["locked"] is False
    assert body["validation"]["blocking"] == []
    codes = {issue["code"] for issue in body["validation"]["warnings"]}
    assert {"unspecified_facts"} <= codes
    assert body["validation"]["summary"]["object_count"] == 1
    # The preview wrote nothing.
    assert _state_of(test_client, workspace["id"], "current")["baseline_status"] == "draft"

    locked = _lock(test_client, workspace["id"], current["id"], headers)
    assert locked[0] == 200
    assert locked[1]["validation"]["warnings"], locked[1]


@pytest.mark.parametrize("corruption", ["unknown_object", "dangling_relationship"])
def test_lock_validation_blocks_corrupt_state_references(client, corruption) -> None:
    test_client, sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    with sessions.begin() as db:
        row = db.get(ArchitectureState, UUID(current["id"]))
        if corruption == "unknown_object":
            row.nodes = [
                {
                    "occurrence_id": "occ-missing",
                    "object_id": str(uuid4()),
                    "position": {"x": 0.0, "y": 0.0},
                }
            ]
        else:
            row.nodes = [
                {
                    "occurrence_id": "occ-known",
                    "object_id": str(uuid4()),
                    "position": {"x": 0.0, "y": 0.0},
                }
            ]
            row.relationships = [
                {
                    "id": "rel-1",
                    "source_id": "occ-known",
                    "target_id": "occ-elsewhere",
                    "type": "Consumes",
                }
            ]

    code, body = _lock(test_client, workspace["id"], current["id"], headers, confirm_empty=True)
    assert code in (409, 422), body
    if code == 422:
        assert body["detail"]["code"] == "baseline_validation_failed"
        reported = {issue["code"] for issue in body["detail"]["validation"]["blocking"]}
    else:
        assert body["detail"]["code"] == "baseline_confirmation_required"
        reported = set()
    assert reported

    with sessions() as db:
        assert db.get(ArchitectureState, UUID(current["id"])).baseline_status == "draft"


def test_lock_validation_blocks_a_dangling_canvas_relationship(client) -> None:
    test_client, sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    with sessions.begin() as db:
        row = db.get(ArchitectureState, UUID(current["id"]))
        row.relationships = [
            {
                "id": "rel-1",
                "source_id": "occ-nowhere",
                "target_id": "occ-nowhere-either",
                "type": "Consumes",
            }
        ]
    code, body = _lock(test_client, workspace["id"], current["id"], headers, confirm_empty=True)
    assert code == 422, body
    assert body["detail"]["code"] == "baseline_validation_failed"
    codes = {issue["code"] for issue in body["detail"]["validation"]["blocking"]}
    assert "invalid_state_relationship" in codes


def test_lock_endpoint_enforces_access_and_csrf(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    anonymous = TestClient(main.app)
    try:
        assert anonymous.post(
            f"/api/workspaces/{workspace['id']}/states/{current['id']}/lock-baseline",
            json={"confirm_empty": True},
        ).status_code in (401, 403)
    finally:
        anonymous.close()

    without_csrf = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/lock-baseline",
        json={"confirm_empty": True},
    )
    assert without_csrf.status_code == 403

    # Another workspace cannot reach this state at all.
    second = _workspace(test_client, headers, name=f"Other {uuid4().hex[:6]}")
    foreign = test_client.post(
        f"/api/workspaces/{second['id']}/states/{current['id']}/lock-baseline",
        json={"confirm_empty": True},
        headers=headers,
    )
    assert foreign.status_code == 404


def test_current_state_still_cannot_be_deleted(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")
    response = test_client.delete(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "current_state_protected"


# --- 11: Excel protection -----------------------------------------------------


def test_excel_apply_cannot_mutate_a_contract_in_a_locked_baseline(client) -> None:
    import base64

    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers, demo_preset="full")
    current = _state_of(test_client, workspace["id"], "current")
    anchored = next(
        item["integration_id"]
        for item in current["relationships"]
        if item.get("integration_id")
    )
    contract = test_client.get(f"/api/integrations/{anchored}").json()
    base = (
        f"/api/workspaces/{workspace['id']}/integration-design/contracts/{contract['id']}/workbook"
    )
    exported = test_client.get(base)
    assert exported.status_code == 200, exported.text
    content = base64.b64encode(exported.content).decode("ascii")

    # The demo's Current state is a captured (locked) baseline.
    assert current["baseline_status"] == "locked"

    preview = test_client.post(
        f"{base}/preview",
        json={"filename": "w.xlsx", "content_base64": content},
        headers=headers,
    )
    assert preview.status_code == 409, preview.text
    assert preview.json()["detail"]["code"] == "current_baseline_locked"

    apply_response = test_client.post(
        f"{base}/apply",
        json={
            "filename": "w.xlsx",
            "content_base64": content,
            "expected_revision": contract["revision"],
            "preview_hash": "0" * 64,
        },
        headers=headers,
    )
    assert apply_response.status_code == 409, apply_response.text
    assert apply_response.json()["detail"]["code"] == "current_baseline_locked"
    # The contract is untouched.
    assert test_client.get(f"/api/integrations/{contract['id']}").json() == contract


# --- 12/13: portability -------------------------------------------------------


def test_bundle_round_trip_preserves_the_baseline_lifecycle(client) -> None:
    test_client, sessions, user_id = client
    headers = csrf_headers(test_client)
    source = _workspace(test_client, headers)
    current = _state_of(test_client, source["id"], "current")
    locked = _lock(test_client, source["id"], current["id"], headers, confirm_empty=True)
    assert locked[0] == 200
    draft_workspace = _workspace(test_client, headers)

    bundle = test_client.get(f"/api/workspaces/{source['id']}/export").json()
    bundle["workspace"]["name"] = f"Imported {uuid4().hex[:6]}"
    imported = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert imported.status_code == 201, imported.text
    imported_current = _state_of(test_client, imported.json()["id"], "current")
    assert imported_current["baseline_status"] == "locked"
    assert imported_current["baseline_locked_by"] == str(user_id)
    assert imported_current["baseline_locked_at"] == locked[1]["state"]["baseline_locked_at"]

    # A draft baseline stays a draft through the same path.
    draft_bundle = test_client.get(f"/api/workspaces/{draft_workspace['id']}/export").json()
    draft_bundle["workspace"]["name"] = f"Draft import {uuid4().hex[:6]}"
    imported_draft = test_client.post(
        "/api/workspaces/import", json=draft_bundle, headers=headers
    )
    assert imported_draft.status_code == 201, imported_draft.text
    assert (
        _state_of(test_client, imported_draft.json()["id"], "current")["baseline_status"]
        == "draft"
    )

    fork = test_client.post(
        f"/api/workspaces/{source['id']}/fork",
        json={"name": f"Fork {uuid4().hex[:6]}"},
        headers=headers,
    )
    assert fork.status_code == 201, fork.text
    forked_current = _state_of(test_client, fork.json()["id"], "current")
    assert forked_current["baseline_status"] == "locked"
    assert forked_current["baseline_locked_by"] == str(user_id)
    with sessions() as db:
        assert db.scalar(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == UUID(fork.json()["id"]),
                ArchitectureState.state_type == "current",
            )
        ).baseline_locked_by == user_id


def test_old_bundle_imports_current_as_locked(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    source = _workspace(test_client, headers)
    # Materialise the Current state (the lazy draft baseline) before exporting.
    _state_of(test_client, source["id"], "current")
    bundle = test_client.get(f"/api/workspaces/{source['id']}/export").json()
    assert any(row["state_type"] == "current" for row in bundle["states"])
    # A bundle written before this slice: v2 with Current content but no fields.
    for row in bundle["states"]:
        row.pop("baseline_status", None)
        row.pop("baseline_locked_at", None)
        row.pop("baseline_locked_by", None)
    bundle["workspace"]["name"] = f"Legacy {uuid4().hex[:6]}"

    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    imported = response.json()["id"]
    assert _state_of(test_client, imported, "current")["baseline_status"] == "locked"

    # And the imported baseline is read-only, exactly as before this slice.
    blocked = _representative_write(
        test_client, headers, imported, _state_of(test_client, imported, "current")["id"]
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "current_baseline_locked"


def test_bundle_rejects_an_unknown_baseline_status(client) -> None:
    test_client, _sessions, _user_id = client
    headers = csrf_headers(test_client)
    bundle = {
        "format": "data-designer-workspace",
        "version": 2,
        "schema": "data-designer-workspace/v2",
        "workspace": {"name": f"Bad {uuid4().hex[:6]}", "description": None},
        "systems": [],
        "objects": [],
        "fields": [],
        "integrations": [],
        "scenarios": [],
        "states": [
            {
                "id": str(uuid4()),
                "name": "Current State",
                "state_type": "current",
                "baseline_status": "eternal",
                "nodes": [],
                "relationships": [],
            }
        ],
        "architecture_objects": [],
        "architecture_relationships": [],
        "architecture_state_members": [],
        "business_goals": [],
        "business_requirements": [],
        "business_capabilities": [],
        "business_processes": [],
        "architecture_principles": [],
        "organization_roles": [],
        "information_objects": [],
        "information_attributes": [],
        "solution_boundaries": [],
        "solution_components": [],
        "solution_interfaces": [],
        "interface_operations": [],
        "data_repositories": [],
        "deployment_nodes": [],
        "trust_boundaries": [],
        "integration_field_refs": [],
        "integration_dependencies": [],
        "integration_state_overrides": [],
        "solution_members": [],
        "solution_integrations": [],
        "evidence": [],
    }
    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 422, response.text
    codes = {problem["code"] for problem in response.json()["detail"]["problems"]}
    assert "invalid_baseline_status" in codes


def test_bundle_format_version_is_unchanged() -> None:
    """Adding the baseline fields is additive, so the format version stands."""
    from app.workspaces.bundle import BUNDLE_SCHEMA, BUNDLE_VERSION

    assert BUNDLE_VERSION == 2
    assert BUNDLE_SCHEMA == "data-designer-workspace/v2"


# --- 15: migration ------------------------------------------------------------


def test_migration_declares_additive_baseline_revision() -> None:
    from tests.test_migrations import _script

    script = _script()
    revision = script.get_revision("0028_current_baseline")
    assert revision is not None
    assert revision.down_revision == "0027_solution_integrations"


def test_offline_upgrade_adds_the_baseline_fields() -> None:
    from alembic import command
    from tests.test_migrations import _config

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.upgrade(_config(), "head", sql=True)
    sql = buffer.getvalue()
    assert "ALTER TABLE architecture_states ADD COLUMN baseline_status" in sql
    assert "ALTER TABLE architecture_states ADD COLUMN baseline_locked_at" in sql
    assert "ALTER TABLE architecture_states ADD COLUMN baseline_locked_by" in sql
    assert "UPDATE architecture_states SET baseline_status = 'locked'" in sql
    assert "ck_architecture_states_baseline_status" in sql
    assert "fk_architecture_states_baseline_locked_by" in sql
    assert "ix_architecture_states_workspace_type" in sql


def test_offline_downgrade_removes_only_the_baseline_additions() -> None:
    from alembic import command
    from tests.test_migrations import _config

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.downgrade(
            _config(), "0028_current_baseline:0027_solution_integrations", sql=True
        )
    sql = buffer.getvalue()
    assert "DROP COLUMN baseline_locked_by" in sql
    assert "DROP COLUMN baseline_locked_at" in sql
    assert "DROP COLUMN baseline_status" in sql
    assert "DROP INDEX ix_architecture_states_workspace_type" in sql
    # Nothing unrelated is removed.
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN state_type" not in sql
    assert "DROP COLUMN nodes" not in sql
    assert "DROP COLUMN description" not in sql


# --- a concise baseline summary is available for the dialog -------------------


def test_validation_preview_never_writes_and_reports_a_summary(client) -> None:
    test_client, sessions, _user_id = client
    headers = csrf_headers(test_client)
    workspace = _workspace(test_client, headers)
    current = _state_of(test_client, workspace["id"], "current")

    before = json.dumps(_state_of(test_client, workspace["id"], "current"), sort_keys=True)
    response = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/lock-baseline",
        json={"validate_only": True},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["locked"] is False
    assert body["state"]["baseline_status"] == "draft"
    assert body["validation"]["summary"]["node_count"] == 0
    assert json.dumps(
        _state_of(test_client, workspace["id"], "current"), sort_keys=True
    ) == before
    with sessions() as db:
        assert db.get(ArchitectureState, UUID(current["id"])).baseline_locked_at is None
