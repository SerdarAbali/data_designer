"""Explicit single mediator on Integration Contracts (slice: mediator).

Covers the canonical ``mediator_system_id`` / ``mediator_responsibility`` fields,
their validation, the effective mediation resolution (explicit vs legacy
runtime-endpoint heuristic), the projection surfaces, the proposal apply path,
the Catalog archive guard, traceability and isolation.

The business direction (source -> target) is never rewritten by a mediator, and
``NULL`` always means "no explicitly modelled mediator".
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.helper_actions.service import compute_proposal_hash
from app.models import (
    CatalogSystem,
    HelperChangeOperation,
    HelperChangeSet,
    Integration,
    Tenant,
)
from tests.baseline_support import lock_baseline
from tests.test_helper_action_apply import _apply as apply_change_set
from tests.test_helper_action_apply import _approve, _propose, _undo, _validate
from tests.test_helper_action_apply import client as apply_client_fixture
from tests.test_integrations import client as client_fixture
from tests.test_integrations import csrf_headers
from tests.test_scenarios import string_endpoint

client = client_fixture

# The proposal-apply pipeline needs a workspace with every discipline enabled.
apply_client = apply_client_fixture

# Frozen hash of a runtime-mediated ``create_contract`` operation shape. Any
# change to it invalidates every previously stored proposal hash, so later
# slices re-assert it (see the evidence suite) as well as this one.
RUNTIME_MEDIATED_CREATE_CONTRACT_HASH = (
    "cac8374831284224bb52b7dc15453c3079e8149a6278ce9890b0cf938d2e08a0"
)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


# --- fixtures / helpers -------------------------------------------------------


def _workspace(test_client, headers, disciplines=("integration",), name=None):
    response = test_client.post(
        "/api/workspaces",
        json={"name": name or _unique("Mediator"), "disciplines": list(disciplines)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    workspace = response.json()
    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    current = next(state for state in states if state["state_type"] == "current")
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": _unique("Candidate"), "target_state_type": "candidate"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _system(test_client, headers, *, name=None, kind="application"):
    response = test_client.post(
        "/api/catalog/systems",
        json={"name": name or _unique("System"), "kind": kind},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _design(workspace_id) -> str:
    return f"/api/workspaces/{workspace_id}/integration-design"


def _endpoints(test_client, label):
    source = string_endpoint(test_client, f"{label} source", "name")
    target = string_endpoint(test_client, f"{label} target", "code")
    return source, target


def _create_contract(test_client, headers, source, target, *, name=None, **extra):
    body = {
        "source_system_id": source["system"]["id"],
        "source_object_id": source["object"]["id"],
        "target_system_id": target["system"]["id"],
        "target_object_id": target["object"]["id"],
        "name": name or _unique("Contract"),
        **extra,
    }
    return test_client.post("/api/integrations", json=body, headers=headers)


def _contract_with_mediator(test_client, headers, *, mediator_kind="runtime"):
    """Salesforce -> FRENDS -> NetSuite: the required example, generalised."""
    source, target = _endpoints(test_client, _unique("Mediation"))
    mediator = _system(test_client, headers, kind=mediator_kind)
    response = _create_contract(
        test_client,
        headers,
        source,
        target,
        mediator_system_id=mediator["id"],
        mediator_responsibility="Routes and translates the exchange.",
    )
    assert response.status_code == 201, response.text
    return response.json(), source, target, mediator


def _patch_contract(test_client, headers, contract_id, **fields):
    current = test_client.get(f"/api/integrations/{contract_id}").json()
    return test_client.patch(
        f"/api/integrations/{contract_id}",
        json={"expected_revision": current["revision"], **fields},
        headers=headers,
    )


# --- creation / validation ---------------------------------------------------


def test_null_mediator_accepted(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source, target = _endpoints(test_client, _unique("Null"))
    response = _create_contract(test_client, headers, source, target)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mediator_system_id"] is None
    assert body["mediator_responsibility"] is None


def test_valid_mediator_accepted(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    assert contract["mediator_system_id"] == mediator["id"]
    assert contract["mediator_responsibility"] == "Routes and translates the exchange."


def test_unknown_mediator_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source, target = _endpoints(test_client, _unique("Unknown"))
    response = _create_contract(
        test_client, headers, source, target, mediator_system_id=str(uuid4())
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "unknown_mediator"


def test_cross_tenant_mediator_rejected(client) -> None:
    test_client, sessions = client
    headers = csrf_headers(test_client)
    source, target = _endpoints(test_client, _unique("CrossTenant"))
    with sessions.begin() as db:
        other_tenant = Tenant(name=_unique("Other"))
        db.add(other_tenant)
        db.flush()
        foreign = CatalogSystem(
            tenant_id=other_tenant.id, name=_unique("Foreign runtime"), kind="runtime"
        )
        db.add(foreign)
        db.flush()
        foreign_id = str(foreign.id)
    response = _create_contract(
        test_client, headers, source, target, mediator_system_id=foreign_id
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "cross_tenant_mediator"


def test_archived_mediator_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source, target = _endpoints(test_client, _unique("Archived"))
    mediator = _system(test_client, headers, kind="runtime")
    archived = test_client.delete(
        f"/api/catalog/systems/{mediator['id']}", headers=headers
    )
    assert archived.status_code == 204, archived.text
    response = _create_contract(
        test_client, headers, source, target, mediator_system_id=mediator["id"]
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "archived_mediator"


def test_mediator_equal_to_source_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source, target = _endpoints(test_client, _unique("SourceEq"))
    response = _create_contract(
        test_client,
        headers,
        source,
        target,
        mediator_system_id=source["system"]["id"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "mediator_is_source"


def test_mediator_equal_to_target_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source, target = _endpoints(test_client, _unique("TargetEq"))
    response = _create_contract(
        test_client,
        headers,
        source,
        target,
        mediator_system_id=target["system"]["id"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "mediator_is_target"


def _assert_check_rejects_endpoint_change(sessions, contract_id, field: str, value: str):
    """Source/target are immutable through the API, so the invariant is enforced
    at the database boundary too: no writer can make an endpoint the mediator."""
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            row = db.get(Integration, UUID(str(contract_id)))
            setattr(row, field, UUID(str(value)))
    with sessions() as db:
        row = db.get(Integration, UUID(str(contract_id)))
        assert getattr(row, field) != UUID(str(value))


def test_updating_source_to_equal_mediator_rejected(client) -> None:
    test_client, sessions = client
    headers = csrf_headers(test_client)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    _assert_check_rejects_endpoint_change(
        sessions, contract["id"], "source_system_id", mediator["id"]
    )


def test_updating_target_to_equal_mediator_rejected(client) -> None:
    test_client, sessions = client
    headers = csrf_headers(test_client)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    _assert_check_rejects_endpoint_change(
        sessions, contract["id"], "target_system_id", mediator["id"]
    )


def test_update_can_set_replace_and_clear_the_mediator(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    source, target = _endpoints(test_client, _unique("Update"))
    mediator_a = _system(test_client, headers, kind="runtime")
    mediator_b = _system(test_client, headers, kind="runtime")
    contract = _create_contract(test_client, headers, source, target).json()

    set_response = _patch_contract(
        test_client,
        headers,
        contract["id"],
        mediator_system_id=mediator_a["id"],
        mediator_responsibility="First mediator.",
    )
    assert set_response.status_code == 200, set_response.text
    assert set_response.json()["mediator_system_id"] == mediator_a["id"]

    replace_response = _patch_contract(
        test_client, headers, contract["id"], mediator_system_id=mediator_b["id"]
    )
    assert replace_response.status_code == 200, replace_response.text
    assert replace_response.json()["mediator_system_id"] == mediator_b["id"]
    # The responsibility is independent: it is only cleared when explicitly asked.
    assert replace_response.json()["mediator_responsibility"] == "First mediator."

    clear_response = _patch_contract(
        test_client,
        headers,
        contract["id"],
        mediator_system_id=None,
        mediator_responsibility=None,
    )
    assert clear_response.status_code == 200, clear_response.text
    assert clear_response.json()["mediator_system_id"] is None
    assert clear_response.json()["mediator_responsibility"] is None


def test_update_revalidates_mediator_against_endpoints(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    contract, source, _target, _mediator = _contract_with_mediator(test_client, headers)
    response = _patch_contract(
        test_client, headers, contract["id"], mediator_system_id=source["system"]["id"]
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "mediator_is_source"


# --- projections -------------------------------------------------------------


def test_explicit_mediator_returned_by_contract_response(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    body = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert body["mediator_system_id"] == mediator["id"]
    assert body["mediator_responsibility"] == "Routes and translates the exchange."


def test_explicit_mediator_returned_by_landscape(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    contract, source, target, mediator = _contract_with_mediator(test_client, headers)
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["mediator"]["system_id"] == mediator["id"]
    assert summary["mediator"]["responsibility"] == "Routes and translates the exchange."
    # The mediator is an overlay: the business endpoints are untouched.
    assert summary["source"]["system_id"] == source["system"]["id"]
    assert summary["target"]["system_id"] == target["system"]["id"]
    assert summary["mediator"]["system_id"] not in (
        summary["source"]["system_id"],
        summary["target"]["system_id"],
    )


def test_explicit_mediator_returned_by_contract_detail(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    detail = test_client.get(
        f"{_design(workspace['id'])}/contracts/{contract['id']}",
        params={"state_id": current["id"]},
    ).json()
    assert detail["contract"]["mediator"]["system_id"] == mediator["id"]


def test_explicit_mediator_returned_by_message_flow(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    flow = test_client.get(
        f"{_design(workspace['id'])}/contracts/{contract['id']}/flow",
        params={"state_id": current["id"]},
    ).json()
    assert flow["contract"]["mediator"]["system_id"] == mediator["id"]
    assert flow["contract"]["mediated"] is True


def test_mediated_true_and_source_explicit_for_explicit_mediator(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    contract, _source, _target, _mediator = _contract_with_mediator(test_client, headers)
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["mediated"] is True
    assert summary["explicit_mediator"] is True
    assert summary["mediation_source"] == "explicit"
    assert summary["mediator"]["explicit"] is True


def test_legacy_endpoint_heuristic_still_works(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    source, target = _endpoints(test_client, _unique("Legacy"))
    runtime = _system(test_client, headers, kind="integration_runtime")
    patched = test_client.patch(
        f"/api/catalog/systems/{target['system']['id']}",
        json={"kind": "integration_runtime"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    contract = _create_contract(test_client, headers, source, target).json()
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["mediated"] is True
    assert summary["explicit_mediator"] is False
    assert summary["mediation_source"] == "legacy_endpoint_heuristic"
    assert summary["mediator"]["system_id"] == target["system"]["id"]
    assert summary["mediator"]["explicit"] is False
    # The heuristic is a compatibility fallback: nothing is persisted.
    stored = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert stored["mediator_system_id"] is None
    assert runtime["id"] != stored["mediator_system_id"]


def test_direct_contract_remains_non_mediated(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    source, target = _endpoints(test_client, _unique("Direct"))
    contract = _create_contract(test_client, headers, source, target).json()
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["mediated"] is False
    assert summary["explicit_mediator"] is False
    assert summary["mediation_source"] == "none"
    assert summary["mediator"] is None


def test_existing_contract_creation_without_mediator_unchanged(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    source, target = _endpoints(test_client, _unique("Unchanged"))
    contract = _create_contract(
        test_client, headers, source, target, name="Existing shape"
    ).json()
    assert contract["name"] == "Existing shape"
    assert contract["revision"] == 1
    assert contract["mediator_system_id"] is None
    # A legacy response payload (no mediation fields at all) must still render
    # through the projections without inventing a mediator.
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["source"]["object_id"] == source["object"]["id"]
    assert summary["target"]["object_id"] == target["object"]["id"]
    assert summary["mediation_source"] == "none"


# --- proposal apply ----------------------------------------------------------


def _proposal_body(workspace, candidate, source, target, **overrides):
    body = {
        "state_id": candidate["id"],
        "summary": "Runtime mediated integration",
        "contract": {
            "name": f"Runtime contract {uuid4().hex[:6]}",
            "source_system_id": source["system_id"],
            "source_object_id": source["object_id"],
            "target_system_id": target["system_id"],
            "target_object_id": target["object_id"],
            "interaction_type": "REQUEST_RESPONSE",
            "pattern": "request_reply",
        },
    }
    # runtime_mediated / runtime_system_id / runtime_responsibility are top-level
    # request fields, not Contract fields.
    body.update(overrides)
    return body


def _runtime_nodes(test_client, headers):
    source = _system(test_client, headers)
    target = _system(test_client, headers)
    runtime = _system(test_client, headers, kind="runtime")
    source_object = test_client.post(
        f"/api/catalog/systems/{source['id']}/objects",
        json={"name": "Customer"},
        headers=headers,
    ).json()["id"]
    target_object = test_client.post(
        f"/api/catalog/systems/{target['id']}/objects",
        json={"name": "Account"},
        headers=headers,
    ).json()["id"]
    return {
        "source": {"system_id": source["id"], "object_id": source_object},
        "target": {"system_id": target["id"], "object_id": target_object},
        "runtime": runtime,
    }


def test_proposal_runtime_system_id_persists_as_mediator_system_id(apply_client) -> None:
    test_client, sessions = apply_client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Apply"), "disciplines": ["solution", "integration"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    nodes = _runtime_nodes(test_client, headers)
    body = _proposal_body(
        workspace,
        candidate,
        nodes["source"],
        nodes["target"],
        runtime_mediated=True,
        runtime_system_id=nodes["runtime"]["id"],
        runtime_responsibility="Translates CRM payloads for Billing.",
    )
    proposal = _propose(
        test_client, headers, workspace["id"], "propose_runtime_mediated_integration", body
    ).json()
    assert (
        _validate(test_client, headers, workspace["id"], proposal["id"]).json()["status"]
        == "validated"
    )
    assert _approve(test_client, headers, workspace["id"], proposal["id"]).status_code == 200
    applied = apply_change_set(test_client, headers, workspace["id"], proposal["id"])
    assert applied.status_code == 200, applied.text

    with sessions() as db:
        contract = db.scalar(
            select(Integration).where(
                Integration.name == body["contract"]["name"],
                Integration.deleted_at.is_(None),
            )
        )
        assert contract is not None
        assert contract.mediator_system_id == UUID(str(nodes["runtime"]["id"]))
        assert contract.mediator_responsibility == "Translates CRM payloads for Billing."
        # Business direction is preserved exactly as proposed.
        assert contract.source_system_id == UUID(str(nodes["source"]["system_id"]))
        assert contract.target_system_id == UUID(str(nodes["target"]["system_id"]))


def test_proposal_apply_rejects_incoherent_mediator(apply_client) -> None:
    test_client, _ = apply_client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Incoherent"), "disciplines": ["solution", "integration"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    # The source is itself a runtime, so the runtime selection is degenerate.
    runtime = _system(test_client, headers, kind="runtime")
    target = _system(test_client, headers)
    runtime_object = test_client.post(
        f"/api/catalog/systems/{runtime['id']}/objects",
        json={"name": "Customer"},
        headers=headers,
    ).json()["id"]
    target_object = test_client.post(
        f"/api/catalog/systems/{target['id']}/objects",
        json={"name": "Account"},
        headers=headers,
    ).json()["id"]
    body = _proposal_body(
        workspace,
        candidate,
        {"system_id": runtime["id"], "object_id": runtime_object},
        {"system_id": target["id"], "object_id": target_object},
        runtime_mediated=True,
        runtime_system_id=runtime["id"],
    )
    proposal = _propose(
        test_client, headers, workspace["id"], "propose_runtime_mediated_integration", body
    ).json()
    assert (
        _validate(test_client, headers, workspace["id"], proposal["id"]).json()["status"]
        == "validated"
    )
    assert _approve(test_client, headers, workspace["id"], proposal["id"]).status_code == 200
    rejected = apply_change_set(test_client, headers, workspace["id"], proposal["id"])
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "mediator_is_endpoint"


def test_apply_and_undo_remains_safe(apply_client) -> None:
    test_client, sessions = apply_client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Undo"), "disciplines": ["solution", "integration"]},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    nodes = _runtime_nodes(test_client, headers)
    body = _proposal_body(
        workspace,
        candidate,
        nodes["source"],
        nodes["target"],
        runtime_mediated=True,
        runtime_system_id=nodes["runtime"]["id"],
    )
    proposal = _propose(
        test_client, headers, workspace["id"], "propose_runtime_mediated_integration", body
    ).json()
    assert _validate(test_client, headers, workspace["id"], proposal["id"]).status_code == 200
    assert _approve(test_client, headers, workspace["id"], proposal["id"]).status_code == 200
    applied = apply_change_set(test_client, headers, workspace["id"], proposal["id"])
    assert applied.status_code == 200, applied.text

    undone = _undo(test_client, headers, workspace["id"], proposal["id"])
    assert undone.status_code == 200, undone.text
    with sessions() as db:
        remaining = db.scalar(
            select(Integration).where(
                Integration.name == body["contract"]["name"],
                Integration.deleted_at.is_(None),
            )
        )
        assert remaining is None


# --- proposal hash regression lock ------------------------------------------


def test_operation_hash_regression_lock() -> None:
    """Freezes the hashing inputs for the runtime-mediated create_contract shape.

    The proposal hash is computed from ``proposed_value``; persisting the mediator
    at apply time must not change a single stored hash. If this literal changes,
    every previously approved proposal hash becomes invalid.
    """
    change_set = HelperChangeSet(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        tenant_id=UUID("22222222-2222-2222-2222-222222222222"),
        workspace_id=UUID("22222222-2222-2222-2222-222222222222"),
        state_id=UUID("33333333-3333-3333-3333-333333333333"),
        helper_name="propose_runtime_mediated_integration",
        summary="Integration proposal",
        assumptions=["a"],
        unresolved_decisions=[],
        warnings=[],
    )
    operation = HelperChangeOperation(
        id=UUID("44444444-4444-4444-4444-444444444444"),
        change_set_id=change_set.id,
        tenant_id=change_set.tenant_id,
        workspace_id=change_set.workspace_id,
        operation_id="op-1",
        ordinal=1,
        domain_action="create_contract",
        target_type="contract",
        target_id=None,
        temporary_id="temp-contract-1",
        before_value=None,
        proposed_value={
            "kind": "contract",
            "status": "draft",
            "name": "CRM Customer Onboarding",
            "source_system_id": "55555555-5555-5555-5555-555555555555",
            "source_object_id": "66666666-6666-6666-6666-666666666666",
            "target_system_id": "77777777-7777-7777-7777-777777777777",
            "target_object_id": "88888888-8888-8888-8888-888888888888",
            "runtime_mediated": True,
            "runtime_system_id": "99999999-9999-9999-9999-999999999999",
            "runtime_responsibility": "Not defined.",
        },
        depends_on=[],
        explanation="Propose new draft Contract 'CRM Customer Onboarding'",
        resolution_state="active",
    )
    assert (
        compute_proposal_hash(change_set, [operation])
        == RUNTIME_MEDIATED_CREATE_CONTRACT_HASH
    )


# --- catalog archive guard ---------------------------------------------------


def test_catalog_archive_guard_detects_mediator_references(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    response = test_client.delete(
        f"/api/catalog/systems/{mediator['id']}", headers=headers
    )
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "catalog_item_in_use"
    assert contract["id"] in {item["id"] for item in detail["integrations"]}


def test_cascade_archive_clears_the_mediator_overlay(client) -> None:
    """Chosen cascade behaviour: the overlay is dropped, the Contract survives."""
    test_client, _ = client
    headers = csrf_headers(test_client)
    contract, _source, target, mediator = _contract_with_mediator(test_client, headers)
    response = test_client.delete(
        f"/api/catalog/systems/{mediator['id']}",
        params={"cascade": "true"},
        headers=headers,
    )
    assert response.status_code == 204, response.text
    after = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert after["deleted_at"] is None
    assert after["mediator_system_id"] is None
    assert after["mediator_responsibility"] is None
    assert after["revision"] == contract["revision"] + 1
    # The business direction survives the mediator retirement.
    assert after["source_system_id"] == contract["source_system_id"]
    assert after["target_system_id"] == target["system"]["id"]


# --- traceability ------------------------------------------------------------


def _graph_edges(test_client, workspace_id, state_id):
    graph = test_client.get(
        f"/api/workspaces/{workspace_id}/architecture-graph",
        params={"state_id": state_id},
    ).json()
    return graph["edges"]


def _system_kind_for_contract(test_client, headers, *, kind):
    source, target = _endpoints(test_client, _unique("Graph"))
    runtime = _system(test_client, headers, kind=kind)
    contract = _create_contract(
        test_client, headers, source, target, mediator_system_id=runtime["id"]
    ).json()
    return contract, runtime


def test_traceability_contains_one_mediated_by_edge(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    contract, runtime = _system_kind_for_contract(test_client, headers, kind="runtime")
    edges = _graph_edges(test_client, workspace["id"], current["id"])
    mediation_edges = [
        edge for edge in edges if edge["relationship_type"] == "mediated_by"
    ]
    assert len(mediation_edges) == 1
    assert mediation_edges[0]["source_object_id"] == contract["id"]
    assert mediation_edges[0]["target_object_id"] == runtime["id"]
    assert mediation_edges[0]["derived"] is True


def test_no_duplicate_derived_mediation_edge(client) -> None:
    """The explicit mediator wins even when the legacy heuristic also matches."""
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    # A runtime business endpoint (legacy heuristic matches) *and* an explicit
    # mediator. Only the explicit mediator may be derived.
    source, target = _endpoints(test_client, _unique("Dup"))
    patched = test_client.patch(
        f"/api/catalog/systems/{target['system']['id']}",
        json={"kind": "integration_runtime"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    explicit = _system(test_client, headers, kind="runtime")
    contract = _create_contract(
        test_client, headers, source, target, mediator_system_id=explicit["id"]
    ).json()
    edges = _graph_edges(test_client, workspace["id"], current["id"])
    mediation_edges = [
        edge
        for edge in edges
        if edge["relationship_type"] == "mediated_by"
        and edge["source_object_id"] == contract["id"]
    ]
    assert len(mediation_edges) == 1
    assert mediation_edges[0]["target_object_id"] == explicit["id"]
    # Source/target traceability is unchanged by mediation.
    assert not any(
        edge["target_object_id"] in (source["system"]["id"], target["system"]["id"])
        and edge["source_object_id"] == contract["id"]
        and edge["relationship_type"] == "mediated_by"
        for edge in edges
    )


# --- isolation ---------------------------------------------------------------


def test_tenant_and_workspace_isolation(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    # A workspace without the Integration discipline cannot read the landscape.
    other, other_current, _other_candidate = _workspace(
        test_client, headers, disciplines=("information",)
    )
    gated = test_client.get(
        f"{_design(other['id'])}/landscape", params={"state_id": other_current["id"]}
    )
    assert gated.status_code == 404

    # Mediators never leak across tenants (see also the cross-tenant rejection).
    workspace, current, _candidate = _workspace(test_client, headers)
    contract, _source, _target, mediator = _contract_with_mediator(test_client, headers)
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["mediator"]["system_id"] == mediator["id"]
    # A workspace is backed by its own tenant, so a *different* workspace must
    # never see this tenant's contracts or its mediator.
    second, second_current, _second_candidate = _workspace(test_client, headers)
    second_landscape = test_client.get(
        f"{_design(second['id'])}/landscape", params={"state_id": second_current["id"]}
    ).json()
    assert second_landscape["contracts"] == []


# --- migration / model invariants -------------------------------------------


def test_model_declares_mediator_constraints() -> None:
    table = Integration.__table__
    assert "ck_integrations_mediator_distinct" in {c.name for c in table.constraints}
    assert "fk_integrations_mediator_system" in {c.name for c in table.constraints}
    assert "ix_integrations_mediator_system" in {i.name for i in table.indexes}


def test_migration_declares_additive_mediator_revision() -> None:
    from tests.test_migrations import _script

    script = _script()
    revision = script.get_revision("0025_contract_mediator")
    assert revision is not None
    assert revision.down_revision == "0024_architecture_facts"


# --- regressions: facts + demo presets ---------------------------------------


def test_architecture_facts_still_work_with_a_mediator(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace(test_client, headers)
    contract, _source, _target, _mediator = _contract_with_mediator(test_client, headers)
    response = test_client.put(
        f"{_design(workspace['id'])}/contracts/{contract['id']}/facts",
        json={"state_id": candidate["id"], "lifecycle_stage": "active"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["lifecycle_stage"]["value"] == "active"
    # Candidate facts and canonical mediation are independent concerns.
    # The Current baseline accepts state-scoped facts while it is a draft and
    # refuses them once it is locked.
    draft = test_client.put(
        f"{_design(workspace['id'])}/contracts/{contract['id']}/facts",
        json={"state_id": current["id"], "lifecycle_stage": "active"},
        headers=headers,
    )
    assert draft.status_code == 200, draft.text

    lock_baseline(test_client, workspace["id"], current["id"], headers)
    readonly = test_client.put(
        f"{_design(workspace['id'])}/contracts/{contract['id']}/facts",
        json={"state_id": current["id"], "lifecycle_stage": "active"},
        headers=headers,
    )
    assert readonly.status_code == 409
    assert readonly.json()["detail"]["code"] == "current_baseline_locked"
    stored = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert stored["lifecycle_stage"] is None


@pytest.mark.parametrize("preset", ["full", "solution_integration", "integration_only"])
def test_demo_presets_still_generate_a_usable_workspace(client, preset) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    response = test_client.post(
        "/api/workspaces",
        json={
            "name": _unique(f"Demo {preset}"),
            "disciplines": ["enterprise", "information", "solution", "integration"],
            "demo_preset": preset,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    workspace = response.json()
    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    current = next(state for state in states if state["state_type"] == "current")
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": current["id"]}
    )
    assert landscape.status_code == 200, landscape.text
    # Demo contracts keep their previous (direct or legacy-heuristic) shape.
    for summary in landscape.json()["contracts"]:
        assert summary["mediation_source"] in ("none", "legacy_endpoint_heuristic")
