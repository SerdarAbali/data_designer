"""Lifecycle, operational-status and environment-scope facts (slice: facts).

Covers the controlled vocabularies on Catalog systems and Integration
contracts, the state-specific ``IntegrationStateOverride`` table and its
effective-value resolver, Current read-only enforcement, isolation, and the
"existing behaviour is unchanged" guarantees.
"""

from uuid import UUID, uuid4

import pytest

from app.architecture.vocabulary import (
    ENVIRONMENT_SCOPES,
    LIFECYCLE_STAGES,
    OPERATIONAL_STATUSES,
)
from app.auth.security import hash_password
from app.helper_actions.service import compute_proposal_hash
from app.models import HelperChangeOperation, HelperChangeSet, Tenant, User
from tests.baseline_support import lock_baseline
from tests.test_integrations import client as client_fixture
from tests.test_integrations import csrf_headers
from tests.test_scenarios import mapped_contract, string_endpoint

client = client_fixture

DESIGN = "integration-design"


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _workspace(test_client, headers, name=None):
    response = test_client.post(
        "/api/workspaces",
        json={"name": name or _unique("Facts"), "disciplines": ["integration"]},
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
    target = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": _unique("Target"), "target_state_type": "target"},
        headers=headers,
    ).json()
    return workspace, current, candidate, target


def _design(workspace_id) -> str:
    return f"/api/workspaces/{workspace_id}/{DESIGN}"


def _create_system(test_client, headers, name=None) -> dict:
    response = test_client.post(
        "/api/catalog/systems",
        json={"name": name or _unique("System"), "kind": "application"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _contract(test_client, name=None) -> tuple[dict, dict, dict]:
    """Create a mapped contract through the existing catalog/integration APIs."""
    label = name or _unique("Contract")
    source = string_endpoint(test_client, f"{label} source", "name")
    target = string_endpoint(test_client, f"{label} target", "code")
    contract = mapped_contract(test_client, label, source, target)
    return contract, source, target


def _patch_system(test_client, headers, system_id, **fields):
    return test_client.patch(
        f"/api/catalog/systems/{system_id}", json=fields, headers=headers
    )


def _patch_contract(test_client, headers, contract_id, **fields):
    current = test_client.get(f"/api/integrations/{contract_id}").json()
    body = {"expected_revision": current["revision"], **fields}
    return test_client.patch(
        f"/api/integrations/{contract_id}", json=body, headers=headers
    )


def _put_facts(test_client, headers, workspace_id, contract_id, state_id, **fields):
    body = {"state_id": state_id, **fields}
    return test_client.put(
        f"{_design(workspace_id)}/contracts/{contract_id}/facts",
        json=body,
        headers=headers,
    )


def _get_facts(test_client, workspace_id, contract_id, state_id):
    return test_client.get(
        f"{_design(workspace_id)}/contracts/{contract_id}/facts",
        params={"state_id": state_id},
    )


# --- Controlled vocabularies -------------------------------------------------


@pytest.mark.parametrize("value", LIFECYCLE_STAGES)
def test_catalog_system_lifecycle_values_accepted(client, value) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    response = _patch_system(test_client, headers, system["id"], lifecycle_stage=value)
    assert response.status_code == 200, response.text
    assert response.json()["lifecycle_stage"] == value


def test_invalid_lifecycle_value_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    response = _patch_system(test_client, headers, system["id"], lifecycle_stage="on_fire")
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", OPERATIONAL_STATUSES)
def test_catalog_system_operational_statuses_accepted(client, value) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    response = _patch_system(test_client, headers, system["id"], operational_status=value)
    assert response.status_code == 200, response.text
    assert response.json()["operational_status"] == value


def test_invalid_operational_status_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    response = _patch_system(test_client, headers, system["id"], operational_status="vibing")
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", ENVIRONMENT_SCOPES)
def test_catalog_system_environment_scopes_accepted(client, value) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    response = _patch_system(test_client, headers, system["id"], environment_scope=value)
    assert response.status_code == 200, response.text
    assert response.json()["environment_scope"] == value


def test_invalid_environment_scope_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    response = _patch_system(test_client, headers, system["id"], environment_scope="the_cloud")
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", LIFECYCLE_STAGES)
def test_canonical_integration_lifecycle_values_accepted(client, value) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    contract, _, _ = _contract(test_client)
    response = _patch_contract(test_client, headers, contract["id"], lifecycle_stage=value)
    assert response.status_code == 200, response.text
    assert response.json()["lifecycle_stage"] == value


def test_invalid_canonical_integration_status_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    contract, _, _ = _contract(test_client)
    response = _patch_contract(
        test_client, headers, contract["id"], operational_status="pretend_live"
    )
    assert response.status_code == 422, response.text


def test_null_canonical_values_remain_valid(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    assert system["lifecycle_stage"] is None
    assert system["operational_status"] is None
    assert system["environment_scope"] is None

    contract, _, _ = _contract(test_client)
    fetched = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert fetched["lifecycle_stage"] is None
    assert fetched["operational_status"] is None
    assert fetched["environment_scope"] is None


# --- Effective resolution ----------------------------------------------------


def test_contract_override_falls_back_to_canonical(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    patched = _patch_contract(
        test_client, headers, contract["id"], lifecycle_stage="active"
    )
    assert patched.status_code == 200, patched.text

    facts = _get_facts(
        test_client, workspace["id"], contract["id"], candidate["id"]
    ).json()
    assert facts["lifecycle_stage"] == {
        "value": "active",
        "canonical": "active",
        "override": None,
        "overridden": False,
    }
    assert facts["state_type"] == "candidate"
    assert facts["editable"] is True

    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": candidate["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["lifecycle_stage"]["value"] == "active"
    assert summary["lifecycle_stage"]["overridden"] is False


def test_contract_override_replaces_canonical_in_candidate(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    _patch_contract(test_client, headers, contract["id"], lifecycle_stage="active")

    written = _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        lifecycle_stage="retiring", environment_scope="staging",
    )
    assert written.status_code == 200, written.text
    body = written.json()
    assert body["lifecycle_stage"]["value"] == "retiring"
    assert body["lifecycle_stage"]["canonical"] == "active"
    assert body["lifecycle_stage"]["overridden"] is True
    assert body["environment_scope"]["value"] == "staging"
    assert body["operational_status"]["value"] is None

    fetched = _get_facts(
        test_client, workspace["id"], contract["id"], candidate["id"]
    ).json()
    assert fetched["lifecycle_stage"]["value"] == "retiring"

    # The canonical row is never touched by a state override.
    canonical = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert canonical["lifecycle_stage"] == "active"
    assert canonical["environment_scope"] is None

    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": candidate["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["lifecycle_stage"]["value"] == "retiring"
    assert summary["lifecycle_stage"]["overridden"] is True
    assert summary["lifecycle_stage"]["canonical"] == "active"


def test_contract_override_replaces_canonical_in_target(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, _candidate, target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    _patch_contract(test_client, headers, contract["id"], operational_status="tested")

    written = _put_facts(
        test_client, headers, workspace["id"], contract["id"], target["id"],
        operational_status="live",
    )
    assert written.status_code == 200, written.text
    assert written.json()["state_type"] == "target"
    assert written.json()["operational_status"]["value"] == "live"
    assert written.json()["operational_status"]["canonical"] == "tested"
    assert written.json()["operational_status"]["overridden"] is True


def test_clearing_an_override_returns_to_canonical(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    _patch_contract(test_client, headers, contract["id"], lifecycle_stage="active")
    _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        lifecycle_stage="retired",
    )
    cleared = _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        lifecycle_stage=None,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["lifecycle_stage"]["value"] == "active"
    assert cleared.json()["lifecycle_stage"]["override"] is None
    assert cleared.json()["lifecycle_stage"]["overridden"] is False


def test_facts_write_requires_a_fact(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    response = _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"]
    )
    assert response.status_code == 422, response.text


def test_facts_write_rejects_invalid_vocabulary(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    response = _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        lifecycle_stage="banana",
    )
    assert response.status_code == 422, response.text


# --- Current read-only + state writes ---------------------------------------


def test_current_override_write_is_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    # A draft Current accepts the override; the lock is what makes it read-only.
    lock_baseline(test_client, workspace["id"], current["id"], headers)
    response = _put_facts(
        test_client, headers, workspace["id"], contract["id"], current["id"],
        lifecycle_stage="retiring",
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "current_baseline_locked"


def test_current_override_read_returns_canonical_only(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    _patch_contract(test_client, headers, contract["id"], lifecycle_stage="active")
    lock_baseline(test_client, workspace["id"], current["id"], headers)
    facts = _get_facts(test_client, workspace["id"], contract["id"], current["id"]).json()
    assert facts["editable"] is False
    assert facts["lifecycle_stage"]["value"] == "active"
    assert facts["lifecycle_stage"]["override"] is None


def test_candidate_override_write_succeeds(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    response = _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        operational_status="live",
    )
    assert response.status_code == 200, response.text
    assert response.json()["editable"] is True


def test_target_override_write_succeeds(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, _candidate, target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    response = _put_facts(
        test_client, headers, workspace["id"], contract["id"], target["id"],
        lifecycle_stage="planned",
    )
    assert response.status_code == 200, response.text
    assert response.json()["state_type"] == "target"


def test_unknown_state_is_rejected(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, _candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    response = _put_facts(
        test_client, headers, workspace["id"], contract["id"], str(uuid4()),
        lifecycle_stage="active",
    )
    assert response.status_code == 404, response.text


# --- Isolation ---------------------------------------------------------------


def _add_second_tenant(sessions) -> tuple[str, str]:
    email = f"other-{uuid4().hex[:8]}@example.test"
    with sessions.begin() as db:
        tenant = Tenant(name=_unique("other-tenant"))
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email=email,
                password_hash=hash_password("other-test-password"),
            )
        )
    return email, "other-test-password"


def _login(test_client, email, password) -> dict[str, str]:
    csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
    response = test_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    return csrf_headers(test_client)


def test_tenant_isolation_enforced(client) -> None:
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)
    _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        lifecycle_stage="retiring",
    )

    other_email, other_password = _add_second_tenant(sessions)
    other_headers = _login(test_client, other_email, other_password)

    # Another tenant cannot read the contract...
    assert test_client.get(f"/api/integrations/{contract['id']}").status_code == 404
    # ...nor its state-specific facts, nor the workspace they belong to.
    assert (
        _get_facts(test_client, workspace["id"], contract["id"], candidate["id"]).status_code
        == 404
    )
    assert (
        _put_facts(
            test_client, other_headers, workspace["id"], contract["id"], candidate["id"],
            lifecycle_stage="planned",
        ).status_code
        == 404
    )


def test_workspace_access_is_enforced(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)

    # A contract id that belongs to the workspace but is requested through an
    # unknown workspace is not resolvable.
    stranger = test_client.get(
        f"{_design(uuid4())}/contracts/{contract['id']}/facts",
        params={"state_id": current["id"]},
    )
    assert stranger.status_code == 404

    # A state id from a different workspace is not resolvable either.
    other, other_current, _c, _t = _workspace(test_client, headers)
    assert other["id"] != workspace["id"]
    wrong_state = test_client.get(
        f"{_design(workspace['id'])}/contracts/{contract['id']}/facts",
        params={"state_id": other_current["id"]},
    )
    assert wrong_state.status_code == 404


# --- Existing behaviour is unchanged ----------------------------------------


def test_implementation_status_behaviour_unchanged(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate, _target = _workspace(test_client, headers)
    contract, _, _ = _contract(test_client)

    built = _patch_contract(test_client, headers, contract["id"], implementation_status="built")
    assert built.status_code == 200, built.text
    assert built.json()["implementation_status"] == "built"

    _put_facts(
        test_client, headers, workspace["id"], contract["id"], candidate["id"],
        lifecycle_stage="retiring",
    )
    fetched = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert fetched["implementation_status"] == "built"

    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": candidate["id"]}
    ).json()
    summary = next(item for item in landscape["contracts"] if item["id"] == contract["id"])
    assert summary["implementation_status"] == "built"
    assert summary["status"] == "built"


def test_default_implementation_status_unchanged(client) -> None:
    test_client, _ = client
    contract, _, _ = _contract(test_client)
    fetched = test_client.get(f"/api/integrations/{contract['id']}").json()
    assert fetched["implementation_status"] == "draft"


def test_binding_state_behaviour_unchanged(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    system = _create_system(test_client, headers)
    assert system["binding_state"] == "unbound"

    patched = _patch_system(test_client, headers, system["id"], lifecycle_stage="active")
    assert patched.status_code == 200, patched.text
    assert patched.json()["binding_state"] == "unbound"

    bound = _patch_system(test_client, headers, system["id"], binding_state="bound")
    assert bound.status_code == 200, bound.text
    assert bound.json()["binding_state"] == "bound"
    assert bound.json()["lifecycle_stage"] == "active"


def test_existing_proposal_hashes_are_unchanged() -> None:
    """Lock the operation-fingerprint/proposal-hash shape.

    The fact columns are additive, so a proposal built from rows that predate
    this slice must hash byte-for-byte as it always did.
    """

    def uid(n: int) -> UUID:
        return UUID(f"00000000-0000-0000-0000-{n:012d}")

    change_set = HelperChangeSet(
        id=uid(1),
        tenant_id=uid(2),
        workspace_id=uid(3),
        state_id=uid(4),
        helper_name="compose_integration",
        status="validated",
        summary="Add customer sync",
        assumptions=["a1"],
        unresolved_decisions=["d1"],
        warnings=["w1"],
    )
    operation = HelperChangeOperation(
        id=uid(10),
        change_set_id=uid(1),
        tenant_id=uid(2),
        workspace_id=uid(3),
        operation_id="op-1",
        ordinal=0,
        domain_action="create_integration",
        target_type="integration",
        target_id=uid(5),
        temporary_id=None,
        before_value=None,
        proposed_value={"name": "Customer sync"},
        depends_on=["x"],
        explanation="why",
    )
    assert (
        compute_proposal_hash(change_set, [operation])
        == "34c1dfc226eb08d4dba8293bf55ab08f13b108f61b3ef7fac8f36b02fa69097c"
    )


# --- Demos and bundles -------------------------------------------------------


@pytest.mark.parametrize(
    ("preset", "disciplines"),
    [
        ("full", ["enterprise", "information", "solution", "integration"]),
        ("solution_integration", ["solution", "integration"]),
        ("integration_only", ["integration"]),
    ],
)
def test_demo_presets_still_succeed(client, preset, disciplines) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    response = test_client.post(
        "/api/workspaces",
        json={"name": _unique(preset), "disciplines": disciplines, "demo_preset": preset},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    workspace = response.json()
    assert workspace["demo_preset"] == preset

    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    candidate = next((s for s in states if s["state_type"] == "candidate"), states[0])
    landscape = test_client.get(
        f"{_design(workspace['id'])}/landscape", params={"state_id": candidate["id"]}
    )
    assert landscape.status_code == 200, landscape.text
    if preset == "integration_only":
        assert landscape.json()["contracts"]
        # Generated contracts carry no fact values until a human sets them.
        assert all(
            item["lifecycle_stage"]["value"] is None
            for item in landscape.json()["contracts"]
        )


def test_bundle_without_new_facts_still_imports(client) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    bundle = {
        "format": "data-designer-workspace",
        "version": 1,
        "workspace": {"name": _unique("Legacy Bundle"), "description": None},
        "systems": [
            {
                "id": str(uuid4()),
                "name": "Legacy CRM",
                "description": None,
                "kind": "application",
                "icon": None,
                "color": None,
                "position": None,
                "binding_state": "unbound",
                "metadata": {},
            }
        ],
    }
    response = test_client.post("/api/workspaces/import", json=bundle, headers=headers)
    assert response.status_code == 201, response.text
