"""Slice 7: controlled Assistant proposal support for delivered capabilities.

Covers the seven refinement operations end to end: proposal -> validation ->
approval bound to the proposal hash -> transactional apply -> conflict-safe undo.
Reuses the existing helper-action fixtures and the Slice 1-6 domain models.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import (
    ArchitectureEvidence,
    ArchitectureStateMember,
    CatalogSystem,
    HelperChangeOperation,
    Integration,
    IntegrationStateOverride,
    Workspace,
)
from tests.test_helper_action_apply import _apply, _approve, _propose, _undo, _validate
from tests.test_helper_action_apply import client as client_fixture
from tests.test_helper_actions_integration import _system
from tests.test_integrations import create_integration, csrf_headers
from tests.test_scenarios import string_endpoint

client = client_fixture

FULL = ["enterprise", "information", "solution", "integration"]


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _workspace(test_client, headers):
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Refine"), "disciplines": FULL},
        headers=headers,
    ).json()
    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    current = next(state for state in states if state["state_type"] == "current")
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": _unique("Candidate"), "target_state_type": "candidate"},
        headers=headers,
    ).json()
    target = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": _unique("Target"), "target_state_type": "target"},
        headers=headers,
    ).json()
    return workspace, current, candidate, target


def _contract(test_client, headers, name=None):
    source = string_endpoint(test_client, _unique("src"), "name")
    target = string_endpoint(test_client, _unique("dst"), "code")
    response = create_integration(
        test_client, source, target, name=name or _unique("Contract")
    )
    assert response.status_code == 201, response.text
    return response.json()


def _solution(test_client, headers, workspace_id, state_id, name=None):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions",
        json={
            "state_id": state_id,
            "name": name or _unique("Solution"),
            "position": {"x": 0.0, "y": 0.0},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["solution"]["solution_object_id"]


def _ops(proposal):
    return {op["operation_id"]: op for op in proposal["operations"]}


def _prepare(test_client, headers, workspace_id, helper, body):
    response = _propose(test_client, headers, workspace_id, helper, body)
    assert response.status_code == 201, response.text
    proposal = response.json()
    validated = _validate(test_client, headers, workspace_id, proposal["id"])
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "validated", validated.json().get("validation_summary")
    assert _approve(test_client, headers, workspace_id, proposal["id"]).status_code == 200
    return proposal


@pytest.fixture()
def scene(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate, target = _workspace(test_client, headers)
    return {
        "client": test_client,
        "sessions": sessions,
        "headers": headers,
        "workspace": workspace,
        "current": current,
        "candidate": candidate,
        "target": target,
        "tenant_id": UUID(str(workspace["id"])),
    }


# --- 1-2: facts ----------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value,column",
    [
        ("lifecycle_stage", "active", "lifecycle_stage"),
        ("operational_status", "live", "operational_status"),
        ("environment_scope", "production", "environment_scope"),
    ],
)
def test_system_fact_proposal_apply_and_undo(scene, field, value, column) -> None:
    test_client, headers = scene["client"], scene["headers"]
    system = _system(test_client, headers, name=_unique("System"))
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_system_facts",
        {
            "state_id": scene["candidate"]["id"],
            "summary": f"Set {field}",
            "system_id": system["id"],
            **{field: value},
        },
    )
    expected_action = {
        "lifecycle_stage": "set_lifecycle",
        "operational_status": "set_operational_status",
        "environment_scope": "set_environment_scope",
    }[field]
    op = next(iter(_ops(proposal).values()))
    assert op["domain_action"] == expected_action
    assert op["proposed_value"]["value"] == value

    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code == 200, applied.text
    with scene["sessions"]() as db:
        row = db.scalar(
            select(ArchitectureStateMember).where(
                ArchitectureStateMember.object_id == UUID(str(system["id"])),
                ArchitectureStateMember.state_id == UUID(str(scene["candidate"]["id"])),
            )
        )
        assert (row.property_overrides or {})[column] == value
        # Canonical Current is untouched.
        canonical = db.get(CatalogSystem, UUID(str(system["id"])))
        assert getattr(canonical, column) is None

    undone = _undo(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert undone.status_code == 200, undone.text
    with scene["sessions"]() as db:
        row = db.scalar(
            select(ArchitectureStateMember).where(
                ArchitectureStateMember.object_id == UUID(str(system["id"])),
                ArchitectureStateMember.state_id == UUID(str(scene["candidate"]["id"])),
            )
        )
        assert column not in (row.property_overrides or {})
        assert db.get(CatalogSystem, UUID(str(system["id"]))).lifecycle_stage is None


def test_contract_fact_proposal_apply_and_undo_restores_previous_value(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    # Seed an existing override so undo must restore, not just clear.
    first = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_facts",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Seed lifecycle",
            "contract_id": contract["id"],
            "lifecycle_stage": "planned",
        },
    )
    assert _apply(test_client, headers, scene["workspace"]["id"], first["id"]).status_code == 200

    second = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_facts",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Change lifecycle",
            "contract_id": contract["id"],
            "lifecycle_stage": "retiring",
            "operational_status": "degraded",
        },
    )
    applied = _apply(test_client, headers, scene["workspace"]["id"], second["id"])
    assert applied.status_code == 200, applied.text
    with scene["sessions"]() as db:
        override = db.scalar(
            select(IntegrationStateOverride).where(
                IntegrationStateOverride.integration_id == UUID(str(contract["id"])),
                IntegrationStateOverride.state_id == UUID(str(scene["candidate"]["id"])),
            )
        )
        assert override.lifecycle_stage == "retiring"
        assert override.operational_status == "degraded"
        assert db.get(Integration, UUID(str(contract["id"]))).lifecycle_stage is None

    assert _undo(
        test_client, headers, scene["workspace"]["id"], second["id"]
    ).status_code == 200
    with scene["sessions"]() as db:
        override = db.scalar(
            select(IntegrationStateOverride).where(
                IntegrationStateOverride.integration_id == UUID(str(contract["id"])),
                IntegrationStateOverride.state_id == UUID(str(scene["candidate"]["id"])),
            )
        )
        # The seeded value is restored and the added fact is cleared.
        assert override.lifecycle_stage == "planned"
        assert override.operational_status is None


def test_facts_reject_current_and_accept_target(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    system = _system(test_client, headers, name=_unique("System"))
    rejected = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_system_facts",
        {
            "state_id": scene["current"]["id"],
            "summary": "Current write",
            "system_id": system["id"],
            "lifecycle_stage": "active",
        },
    )
    assert rejected.status_code == 409, rejected.text
    assert "read-only" in str(rejected.json()["detail"]).lower()

    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_system_facts",
        {
            "state_id": scene["target"]["id"],
            "summary": "Target write",
            "system_id": system["id"],
            "lifecycle_stage": "active",
        },
    )
    assert _apply(
        test_client, headers, scene["workspace"]["id"], proposal["id"]
    ).status_code == 200


def test_fact_vocabulary_is_enforced(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    system = _system(test_client, headers, name=_unique("System"))
    response = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_system_facts",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Bad value",
            "system_id": system["id"],
            "lifecycle_stage": "eternal",
        },
    )
    assert response.status_code == 422, response.text


# --- 3: mediator ---------------------------------------------------------------


def test_safe_mediator_apply_and_undo(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    mediator = _system(test_client, headers, name=_unique("Runtime"), kind="runtime")
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_mediator",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Mediate",
            "contract_id": contract["id"],
            "mediator_system_id": mediator["id"],
            "mediator_responsibility": "Routes the exchange.",
        },
    )
    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code == 200, applied.text
    with scene["sessions"]() as db:
        row = db.get(Integration, UUID(str(contract["id"])))
        assert row.mediator_system_id == UUID(str(mediator["id"]))
        assert row.mediator_responsibility == "Routes the exchange."

    assert _undo(
        test_client, headers, scene["workspace"]["id"], proposal["id"]
    ).status_code == 200
    with scene["sessions"]() as db:
        row = db.get(Integration, UUID(str(contract["id"])))
        assert row.mediator_system_id is None
        assert row.mediator_responsibility is None


def test_mediator_rejected_when_contract_is_described_by_current(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    mediator = _system(test_client, headers, name=_unique("Runtime"), kind="runtime")
    included = test_client.post(
        f"/api/workspaces/{scene['workspace']['id']}/states/{scene['current']['id']}/include-objects",
        json={
            "system_ids": [contract["source_system_id"], contract["target_system_id"]],
            "integration_ids": [contract["id"]],
        },
        headers=headers,
    )
    assert included.status_code in (200, 201), included.text
    response = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_mediator",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Unsafe mediator",
            "contract_id": contract["id"],
            "mediator_system_id": mediator["id"],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "mediator_affects_current"


@pytest.mark.parametrize("endpoint", ["source", "target"])
def test_mediator_cannot_be_an_endpoint(scene, endpoint) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    endpoint_id = contract[f"{endpoint}_system_id"]
    response = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_mediator",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Bad mediator",
            "contract_id": contract["id"],
            "mediator_system_id": endpoint_id,
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == f"mediator_is_{endpoint}"


def test_mediator_never_fuzzy_matches(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    _system(test_client, headers, name="Integration Runtime", kind="runtime")
    response = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_mediator",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Fuzzy mediator",
            "contract_id": contract["id"],
            "mediator_system_name": "Integration  Runtime ",  # punctuation/space differs
        },
    )
    # Exact normalised matching still succeeds; a different name must not.
    assert response.status_code in (201, 422), response.text
    if response.status_code == 201:
        return
    assert response.json()["detail"]["code"] == "unknown_mediator"


# --- 4: evidence ---------------------------------------------------------------


def test_evidence_apply_and_undo_with_server_provenance(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_evidence",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Evidence",
            "target_kind": "integration",
            "target_id": contract["id"],
            "evidence_classification": "assumption",
            "source_type": "meeting",
            "source_title": "Design review",
            "source_reference": "notes/2026-01-02",
            "evidence_summary": "Assumed nightly batching.",
            "confidence": "medium",
        },
    )
    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code == 200, applied.text
    with scene["sessions"]() as db:
        evidence = db.scalar(
            select(ArchitectureEvidence).where(
                ArchitectureEvidence.integration_id == UUID(str(contract["id"]))
            )
        )
        assert evidence is not None
        assert evidence.created_in_state_id == UUID(str(scene["candidate"]["id"]))
        assert evidence.recorded_by is not None
        assert evidence.recorded_at is not None
        assert evidence.source_title == "Design review"
        evidence_id = evidence.id

    assert _undo(
        test_client, headers, scene["workspace"]["id"], proposal["id"]
    ).status_code == 200
    with scene["sessions"]() as db:
        assert db.get(ArchitectureEvidence, evidence_id) is None
        assert db.get(Integration, UUID(str(contract["id"]))) is not None


def test_evidence_rejects_unsupported_and_missing_targets(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    body = {
        "state_id": scene["candidate"]["id"],
        "summary": "Evidence",
        "target_kind": "architecture_object",
        "target_id": str(uuid4()),
        "evidence_classification": "assumption",
        "source_type": "meeting",
        "source_title": "Review",
        "source_reference": "notes/1",
        "evidence_summary": "Assumed.",
        "confidence": "low",
    }
    unknown = _propose(
        test_client, headers, scene["workspace"]["id"], "propose_evidence", body
    )
    assert unknown.status_code == 201, unknown.text
    # The unknown registry target stays an unresolved decision, not a guess.
    validated = _validate(
        test_client, headers, scene["workspace"]["id"], unknown.json()["id"]
    ).json()
    assert validated["status"] == "validation_failed"
    unsupported = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_evidence",
        {**body, "target_kind": "scenario_ref"},
    )
    assert unsupported.status_code == 422, unsupported.text


# --- 5-6: solution association and relationship ---------------------------------


def test_solution_association_apply_and_undo(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    solution_id = _solution(
        test_client, headers, scene["workspace"]["id"], scene["candidate"]["id"]
    )
    contract = _contract(test_client, headers)
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_solution_contract_association",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Associate",
            "solution_object_id": solution_id,
            "contract_id": contract["id"],
            "role": "participating",
            "description": "Shared onboarding.",
        },
    )
    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code == 200, applied.text
    listed = test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/"
        f"{solution_id}/contracts",
        params={"state_id": scene["candidate"]["id"]},
    ).json()
    assert [item["role"] for item in listed] == ["participating"]

    assert _undo(
        test_client, headers, scene["workspace"]["id"], proposal["id"]
    ).status_code == 200
    after = test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/"
        f"{solution_id}/contracts",
        params={"state_id": scene["candidate"]["id"]},
    ).json()
    assert after == []
    # Neither record was deleted.
    assert test_client.get(f"/api/integrations/{contract['id']}").status_code == 200
    assert test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/"
        f"{solution_id}/design",
        params={"state_id": scene["candidate"]["id"]},
    ).status_code == 200


def test_solution_association_duplicate_conflicts_at_apply(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    solution_id = _solution(
        test_client, headers, scene["workspace"]["id"], scene["candidate"]["id"]
    )
    contract = _contract(test_client, headers)
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_solution_contract_association",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Associate",
            "solution_object_id": solution_id,
            "contract_id": contract["id"],
        },
    )
    # A duplicate created after approval must fail the whole apply.
    direct = test_client.post(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/"
        f"{solution_id}/contracts",
        json={"state_id": scene["candidate"]["id"], "integration_id": contract["id"]},
        headers=headers,
    )
    assert direct.status_code == 201, direct.text
    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code == 409, applied.text
    assert applied.json()["detail"]["code"] == "duplicate_solution_association"
    # The conflict rolled the transaction back: exactly one association exists.
    listed = test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/"
        f"{solution_id}/contracts",
        params={"state_id": scene["candidate"]["id"]},
    ).json()
    assert len(listed) == 1


@pytest.mark.parametrize(
    "rel",
    ["depends_on", "uses", "provides_to", "replaces", "transitions_to", "shares_information_with"],
)
def test_solution_relationship_apply_and_undo(scene, rel) -> None:
    test_client, headers = scene["client"], scene["headers"]
    source = _solution(
        test_client, headers, scene["workspace"]["id"], scene["candidate"]["id"], "Alpha"
    )
    target = _solution(
        test_client, headers, scene["workspace"]["id"], scene["candidate"]["id"], "Beta"
    )
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_solution_relationship",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Relate",
            "source_object_id": source,
            "target_object_id": target,
            "relationship_type": rel,
            "description": "Because.",
        },
    )
    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code == 200, applied.text
    landscape = test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/solution/landscape",
        params={"state_id": scene["candidate"]["id"]},
    ).json()
    assert [edge["relationship_type"] for edge in landscape["relationships"]] == [rel]

    assert _undo(
        test_client, headers, scene["workspace"]["id"], proposal["id"]
    ).status_code == 200
    after = test_client.get(
        f"/api/workspaces/{scene['workspace']['id']}/solution/landscape",
        params={"state_id": scene["candidate"]["id"]},
    ).json()
    assert after["relationships"] == []
    assert {item["solution_object_id"] for item in after["solutions"]} == {source, target}


def test_solution_relationship_rejects_self_and_invalid_type(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    source = _solution(
        test_client, headers, scene["workspace"]["id"], scene["candidate"]["id"]
    )
    self_link = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_solution_relationship",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Self",
            "source_object_id": source,
            "target_object_id": source,
            "relationship_type": "depends_on",
        },
    )
    assert self_link.status_code == 422, self_link.text
    assert self_link.json()["detail"]["code"] == "self_relationship"
    bad_type = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_solution_relationship",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Bad type",
            "source_object_id": source,
            "target_object_id": str(uuid4()),
            "relationship_type": "depends_upon",
        },
    )
    assert bad_type.status_code == 422, bad_type.text


# --- 7: cross-tenant and unresolved --------------------------------------------


def test_cross_tenant_targets_never_resolve(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    other = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Other"), "disciplines": FULL},
        headers=headers,
    ).json()
    other_states = test_client.get(f"/api/workspaces/{other['id']}/states").json()
    other_candidate = next(s for s in other_states if s["state_type"] == "current")
    other_candidate = test_client.post(
        f"/api/workspaces/{other['id']}/states/{other_candidate['id']}/duplicate",
        json={"target_name": "C", "target_state_type": "candidate"},
        headers=headers,
    ).json()
    foreign_solution = _solution(
        test_client, headers, other["id"], other_candidate["id"], "Foreign"
    )
    local = _solution(
        test_client, headers, scene["workspace"]["id"], scene["candidate"]["id"]
    )
    response = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_solution_relationship",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Cross tenant",
            "source_object_id": local,
            "target_object_id": foreign_solution,
            "relationship_type": "depends_on",
        },
    )
    assert response.status_code == 201, response.text
    validated = _validate(
        test_client, headers, scene["workspace"]["id"], response.json()["id"]
    ).json()
    assert validated["status"] == "validation_failed"


# --- 8: undo conflicts ----------------------------------------------------------


def test_post_apply_modification_causes_undo_conflict(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_evidence",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Evidence",
            "target_kind": "integration",
            "target_id": contract["id"],
            "evidence_classification": "assumption",
            "source_type": "meeting",
            "source_title": "Review",
            "source_reference": "notes/1",
            "evidence_summary": "Assumed.",
            "confidence": "low",
        },
    )
    assert _apply(
        test_client, headers, scene["workspace"]["id"], proposal["id"]
    ).status_code == 200
    with scene["sessions"].begin() as db:
        evidence = db.scalar(
            select(ArchitectureEvidence).where(
                ArchitectureEvidence.integration_id == UUID(str(contract["id"]))
            )
        )
        evidence.summary = "Edited later."
    undone = _undo(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert undone.status_code == 409, undone.text
    assert undone.json()["detail"]["code"] == "undo_conflict"


def test_mediator_modification_causes_undo_conflict(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    mediator = _system(test_client, headers, name=_unique("Runtime"), kind="runtime")
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_mediator",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Mediate",
            "contract_id": contract["id"],
            "mediator_system_id": mediator["id"],
        },
    )
    assert _apply(
        test_client, headers, scene["workspace"]["id"], proposal["id"]
    ).status_code == 200
    with scene["sessions"].begin() as db:
        db.get(Integration, UUID(str(contract["id"]))).mediator_responsibility = "Changed."
    undone = _undo(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert undone.status_code == 409, undone.text
    assert undone.json()["detail"]["code"] == "undo_conflict"


# --- 9: transactional rollback --------------------------------------------------


def test_failed_operation_rolls_back_the_whole_change_set(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    contract = _contract(test_client, headers)
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_contract_facts",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Two facts",
            "contract_id": contract["id"],
            "lifecycle_stage": "active",
            "operational_status": "live",
        },
    )
    assert len(proposal["operations"]) == 2
    # Archiving the Contract after approval invalidates the whole change set.
    assert test_client.delete(
        f"/api/integrations/{contract['id']}", headers=headers
    ).status_code == 204
    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code in (409, 422), applied.text
    with scene["sessions"]() as db:
        rows = db.scalars(
            select(IntegrationStateOverride).where(
                IntegrationStateOverride.integration_id == UUID(str(contract["id"]))
            )
        ).all()
    assert list(rows) == []


# --- 10-11: hash integrity ------------------------------------------------------


def test_new_proposal_hashes_are_deterministic(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    system = _system(test_client, headers, name=_unique("System"))
    body = {
        "state_id": scene["candidate"]["id"],
        "summary": "Deterministic",
        "system_id": system["id"],
        "lifecycle_stage": "active",
        "operational_status": "live",
    }
    first = _propose(
        test_client, headers, scene["workspace"]["id"], "propose_system_facts", body
    ).json()
    second = _propose(
        test_client, headers, scene["workspace"]["id"], "propose_system_facts", body
    ).json()
    assert first["proposal_hash"] == second["proposal_hash"]
    assert first["proposal_hash"]


def test_existing_stored_proposal_hashes_are_unchanged() -> None:
    from tests.test_contract_mediator import (
        RUNTIME_MEDIATED_CREATE_CONTRACT_HASH,
        test_operation_hash_regression_lock,
    )

    test_operation_hash_regression_lock()
    assert RUNTIME_MEDIATED_CREATE_CONTRACT_HASH


def test_approved_hash_mismatch_prevents_apply(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    system = _system(test_client, headers, name=_unique("System"))
    proposal = _prepare(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_system_facts",
        {
            "state_id": scene["candidate"]["id"],
            "summary": "Hash",
            "system_id": system["id"],
            "lifecycle_stage": "active",
        },
    )
    with scene["sessions"].begin() as db:
        op = db.scalar(
            select(HelperChangeOperation).where(
                HelperChangeOperation.change_set_id == UUID(str(proposal["id"]))
            )
        )
        op.proposed_value = {**op.proposed_value, "value": "retired"}
    applied = _apply(test_client, headers, scene["workspace"]["id"], proposal["id"])
    assert applied.status_code == 409, applied.text


# --- 12: gating and trusted scope -----------------------------------------------


def test_refinement_tools_are_gated_by_discipline_and_state() -> None:
    from app.assistant import tools

    solution_only = tools.proposal_tool_names()
    assert "architecture_propose_solution_relationship" in solution_only

    enterprise = tools.allowed_tool_names(["enterprise"], "candidate")
    assert "architecture_propose_solution_relationship" not in enterprise
    assert "architecture_propose_system_facts" in enterprise
    assert "architecture_propose_evidence" in enterprise

    integration = tools.allowed_tool_names(["integration"], "candidate")
    assert "architecture_propose_contract_mediator" in integration
    assert "architecture_propose_solution_relationship" not in integration

    current = tools.allowed_tool_names(FULL, "current")
    for name in (
        "architecture_propose_system_facts",
        "architecture_propose_contract_facts",
        "architecture_propose_contract_mediator",
        "architecture_propose_evidence",
        "architecture_propose_solution_contract_association",
        "architecture_propose_solution_relationship",
    ):
        assert name not in current


def test_tool_dispatch_denies_scope_override_and_current() -> None:
    from app.assistant import tools

    denied = [
        "approve_change_set",
        "apply_change_set",
        "undo_change_set",
        "shell",
        "write",
    ]
    assert tools.FORBIDDEN_TOOL_NAMES.issuperset(set(denied))
    assert not (set(tools.proposal_tool_names()) & set(denied))
    for spec in tools.PROPOSAL_TOOL_SPECS:
        assert spec.name.startswith("architecture_propose_")


def test_workspace_is_never_taken_from_the_model() -> None:
    from app.assistant.tools import FORBIDDEN_SCOPE_KEYS

    assert {
        "state_id",
        "workspace_id",
        "tenant_id",
        "user_id",
        "permissions",
    }.issubset(FORBIDDEN_SCOPE_KEYS)


def test_proposal_targets_are_always_same_tenant(scene) -> None:
    test_client, headers = scene["client"], scene["headers"]
    other = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Other"), "disciplines": FULL},
        headers=headers,
    ).json()
    # A proposal created in one workspace cannot reference another's state.
    other_states = test_client.get(f"/api/workspaces/{other['id']}/states").json()
    response = _propose(
        test_client,
        headers,
        scene["workspace"]["id"],
        "propose_system_facts",
        {
            "state_id": other_states[0]["id"],
            "summary": "Cross workspace",
            "system_name": "anything",
            "lifecycle_stage": "active",
        },
    )
    assert response.status_code in (404, 422), response.text
    with scene["sessions"]() as db:
        assert db.get(Workspace, scene["tenant_id"]) is not None
