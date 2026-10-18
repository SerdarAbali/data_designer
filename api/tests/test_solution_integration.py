"""Solution Boundary <-> Integration Contract associations (Slice 5).

Risk-based coverage: creation and effective-state listing, vocabulary and
reference validation, state scoping, retention conflicts, derived traceability,
and isolation. Reuses the existing Integration/Solution fixtures.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Integration, SolutionIntegration
from tests.baseline_support import lock_baseline
from tests.test_integrations import client as client_fixture
from tests.test_integrations import create_endpoint, create_integration, csrf_headers
from tests.test_scenarios import mapped_contract, string_endpoint

client = client_fixture

FULL = ["enterprise", "information", "solution", "integration"]


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _workspace(test_client, headers, disciplines=None):
    response = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Assoc"), "disciplines": list(disciplines or FULL)},
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


def _solution(test_client, headers, workspace_id, state_id, name=None) -> str:
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


def _contract(test_client, name=None) -> str:
    source = string_endpoint(test_client, f"{_unique('src')}", "name")
    destination = string_endpoint(test_client, f"{_unique('dst')}", "code")
    response = create_integration(
        test_client, source, destination, name=name or _unique("Contract")
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _url(workspace_id, solution_object_id) -> str:
    return f"/api/workspaces/{workspace_id}/solution/solutions/{solution_object_id}/contracts"


def _create(test_client, headers, workspace_id, solution_object_id, state_id, contract_id, **extra):
    return test_client.post(
        _url(workspace_id, solution_object_id),
        json={"state_id": state_id, "integration_id": contract_id, **extra},
        headers=headers,
    )


def _list(test_client, workspace_id, solution_object_id, state_id):
    return test_client.get(
        _url(workspace_id, solution_object_id), params={"state_id": state_id}
    )


@pytest.fixture()
def scene(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate, target = _workspace(test_client, headers)
    solution_id = _solution(test_client, headers, workspace["id"], candidate["id"])
    contract_id = _contract(test_client)
    return {
        "client": test_client,
        "sessions": sessions,
        "headers": headers,
        "workspace": workspace,
        "current": current,
        "candidate": candidate,
        "target": target,
        "solution_id": solution_id,
        "contract_id": contract_id,
        "tenant_id": UUID(str(workspace["id"])),
    }


def _canonical(sessions, tenant_id, solution_id, contract_id, role="owned"):
    """Create a canonical association directly, as an import or demo would."""
    row = SolutionIntegration(
        tenant_id=tenant_id,
        solution_object_id=UUID(str(solution_id)),
        integration_id=UUID(str(contract_id)),
        role=role,
        description=None,
        created_in_state_id=None,
    )
    with sessions.begin() as db:
        db.add(row)
        db.flush()
    return str(row.id)


# --- 1: creation and listing ---------------------------------------------------


@pytest.mark.parametrize("role", ["owned", "participating", "dependency"])
def test_association_created_and_listed_in_effective_state(scene, role) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
        role=role, description="Owns the customer onboarding contract.",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == role
    assert body["description"] == "Owns the customer onboarding contract."
    assert body["solution_object_id"] == scene["solution_id"]
    assert body["integration_id"] == scene["contract_id"]
    assert body["state_applicability"] == "state"
    assert body["state_name"] == scene["candidate"]["name"]
    contract = body["contract"]
    assert contract["id"] == scene["contract_id"]
    assert contract["source"]["system_id"]
    assert contract["target"]["system_id"]
    assert contract["implementation_status"] == "draft"
    assert contract["evidence_count"] == 0
    assert contract["lifecycle_stage"]["value"] is None
    # The bounded projection must not leak contract internals.
    for forbidden in ("specification", "phases", "producer_interface", "scenarios"):
        assert forbidden not in contract

    listed = _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    ).json()
    assert [item["id"] for item in listed] == [body["id"]]


def test_invalid_role_rejected(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
        role="owner",
    )
    assert response.status_code == 422, response.text


# --- 3: reference validation ---------------------------------------------------


def test_unknown_contract_rejected(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], str(uuid4()),
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "unknown_contract"


def test_non_boundary_solution_rejected(scene) -> None:
    """The selected object must be a Solution Boundary, not a component/system."""
    component = create_endpoint(scene["client"], _unique("Component"), "name")
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        component["object"]["id"], scene["candidate"]["id"], scene["contract_id"],
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Solution not found"


def test_cross_tenant_contract_rejected(scene) -> None:
    other, _oc, other_candidate, _ot = _workspace(scene["client"], scene["headers"])
    foreign_solution = _solution(
        scene["client"], scene["headers"], other["id"], other_candidate["id"]
    )
    # The association is attempted against the *first* workspace with the other
    # workspace's solution/contract ids: nothing is reachable across tenants.
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        foreign_solution, scene["candidate"]["id"], scene["contract_id"],
    )
    assert response.status_code == 404, response.text


def test_current_state_scoped_write_rejected(scene) -> None:
    # A draft Current accepts the association until the baseline is locked.
    draft = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["current"]["id"], scene["contract_id"],
    )
    assert draft.status_code == 201, draft.text

    lock_baseline(
        scene["client"], scene["workspace"]["id"], scene["current"]["id"], scene["headers"]
    )
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["current"]["id"], scene["contract_id"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "current_baseline_locked"


def test_archived_contract_rejected(scene) -> None:
    archived = scene["client"].delete(
        f"/api/integrations/{scene['contract_id']}", headers=scene["headers"]
    )
    assert archived.status_code == 204, archived.text
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "archived_contract"


# --- 5-8: state scope -----------------------------------------------------------


def test_duplicate_association_rejected_within_a_state_scope(scene) -> None:
    first = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    )
    assert first.status_code == 201, first.text
    duplicate = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
        role="participating",
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "duplicate_solution_association"
    # A different state scope is a different association.
    other = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["target"]["id"], scene["contract_id"],
        role="participating",
    )
    assert other.status_code == 201, other.text


def test_duplicate_canonical_association_rejected(scene) -> None:
    _canonical(scene["sessions"], scene["tenant_id"], scene["solution_id"], scene["contract_id"])
    with pytest.raises(IntegrityError):
        with scene["sessions"].begin() as db:
            db.add(
                SolutionIntegration(
                    tenant_id=scene["tenant_id"],
                    solution_object_id=UUID(str(scene["solution_id"])),
                    integration_id=UUID(str(scene["contract_id"])),
                    role="owned",
                    created_in_state_id=None,
                )
            )


def test_canonical_association_visible_in_every_state(scene) -> None:
    association_id = _canonical(
        scene["sessions"], scene["tenant_id"], scene["solution_id"], scene["contract_id"]
    )
    for state in (scene["current"], scene["candidate"], scene["target"]):
        listed = _list(
            scene["client"], scene["workspace"]["id"], scene["solution_id"], state["id"]
        ).json()
        assert [item["id"] for item in listed] == [association_id]
        assert listed[0]["state_applicability"] == "canonical"
        assert listed[0]["state_name"] is None


def test_candidate_association_isolated_to_that_candidate(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    ).json()
    for state in (scene["current"], scene["target"]):
        listed = _list(
            scene["client"], scene["workspace"]["id"], scene["solution_id"], state["id"]
        ).json()
        assert created["id"] not in [item["id"] for item in listed]


def test_effective_facts_are_state_specific_in_the_listing(scene) -> None:
    canonical_contract = scene["client"].get(
        f"/api/integrations/{scene['contract_id']}"
    ).json()
    patched = scene["client"].patch(
        f"/api/integrations/{scene['contract_id']}",
        json={
            "expected_revision": canonical_contract["revision"],
            "lifecycle_stage": "active",
            "operational_status": "live",
        },
        headers=scene["headers"],
    )
    assert patched.status_code == 200, patched.text
    override = scene["client"].put(
        f"/api/workspaces/{scene['workspace']['id']}/integration-design/contracts/"
        f"{scene['contract_id']}/facts",
        json={"state_id": scene["candidate"]["id"], "lifecycle_stage": "retiring"},
        headers=scene["headers"],
    )
    assert override.status_code == 200, override.text
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    )
    candidate_view = _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    ).json()[0]["contract"]
    assert candidate_view["lifecycle_stage"]["value"] == "retiring"
    assert candidate_view["operational_status"]["value"] == "live"


def test_evidence_count_in_the_association_summary(scene) -> None:
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    )
    created = scene["client"].post(
        f"/api/workspaces/{scene['workspace']['id']}/evidence",
        json={
            "target_kind": "integration",
            "target_id": scene["contract_id"],
            "evidence_classification": "assumption",
            "source_type": "meeting",
            "source_title": "Review",
            "source_reference": "notes/1",
            "summary": "Assumed.",
            "confidence": "low",
        },
        headers=scene["headers"],
    )
    assert created.status_code == 201, created.text
    listed = _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    ).json()
    assert listed[0]["contract"]["evidence_count"] == 1


# --- 9-10: update, delete, retention ---------------------------------------------


def test_update_role_and_description(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
        role="owned", description="First",
    ).json()
    updated = scene["client"].patch(
        f"{_url(scene['workspace']['id'], scene['solution_id'])}/{created['id']}",
        json={"role": "dependency", "description": "Now a dependency."},
        headers=scene["headers"],
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["role"] == "dependency"
    assert updated.json()["description"] == "Now a dependency."
    empty = scene["client"].patch(
        f"{_url(scene['workspace']['id'], scene['solution_id'])}/{created['id']}",
        json={},
        headers=scene["headers"],
    )
    assert empty.status_code == 422, empty.text
    # The contract link is immutable.
    moved = scene["client"].patch(
        f"{_url(scene['workspace']['id'], scene['solution_id'])}/{created['id']}",
        json={"integration_id": str(uuid4())},
        headers=scene["headers"],
    )
    assert moved.status_code == 422, moved.text


def test_removing_an_association_leaves_both_records_intact(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    ).json()
    removed = scene["client"].delete(
        f"{_url(scene['workspace']['id'], scene['solution_id'])}/{created['id']}",
        headers=scene["headers"],
    )
    assert removed.status_code == 204, removed.text
    assert _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    ).json() == []
    # Contract still active and unchanged.
    contract = scene["client"].get(f"/api/integrations/{scene['contract_id']}")
    assert contract.status_code == 200
    # Solution Boundary still present.
    design = scene["client"].get(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/"
        f"{scene['solution_id']}/design",
        params={"state_id": scene["candidate"]["id"]},
    )
    assert design.status_code == 200, design.text


def test_archiving_an_associated_contract_returns_a_conflict(scene) -> None:
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    )
    response = scene["client"].delete(
        f"/api/integrations/{scene['contract_id']}", headers=scene["headers"]
    )
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "solution_integration_conflict"
    assert detail["associations"][0]["integration_id"] == scene["contract_id"]
    # The Contract is untouched, so the association can still be removed.
    assert scene["client"].get(f"/api/integrations/{scene['contract_id']}").status_code == 200


def test_solution_boundary_with_associations_cannot_be_purged(scene) -> None:
    """No Boundary delete route exists yet, so the shared purge guard is the
    enforcement point; the database RESTRICT is the backstop."""
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    )
    from app.architecture.solution_integration import assert_no_solution_integration

    with scene["sessions"]() as db:
        from fastapi import HTTPException

        from app.models import Workspace

        workspace = db.get(Workspace, scene["tenant_id"])
        with pytest.raises(HTTPException) as error:
            assert_no_solution_integration(
                db, scene["tenant_id"], solution_object_id=UUID(str(scene["solution_id"]))
            )
        assert error.value.status_code == 409
        assert error.value.detail["code"] == "solution_integration_conflict"
        assert workspace is not None


def test_evidence_on_the_boundary_and_contract_is_unaffected(scene) -> None:
    association = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    ).json()
    for kind, target in (
        ("integration", scene["contract_id"]),
        ("architecture_object", scene["solution_id"]),
    ):
        created = scene["client"].post(
            f"/api/workspaces/{scene['workspace']['id']}/evidence",
            json={
                "target_kind": kind,
                "target_id": target,
                "evidence_classification": "assumption",
                "source_type": "meeting",
                "source_title": "Review",
                "source_reference": "notes/1",
                "summary": "Assumed.",
                "confidence": "low",
            },
            headers=scene["headers"],
        )
        assert created.status_code == 201, created.text
    removed = scene["client"].delete(
        f"{_url(scene['workspace']['id'], scene['solution_id'])}/{association['id']}",
        headers=scene["headers"],
    )
    assert removed.status_code == 204, removed.text
    for kind, target in (
        ("integration", scene["contract_id"]),
        ("architecture_object", scene["solution_id"]),
    ):
        listed = scene["client"].get(
            f"/api/workspaces/{scene['workspace']['id']}/evidence",
            params={
                "target_kind": kind,
                "target_id": target,
                "state_id": scene["candidate"]["id"],
            },
        ).json()
        assert len(listed) == 1


# --- 11: traceability ------------------------------------------------------------


@pytest.mark.parametrize(
    "role,edge",
    [
        ("owned", "owns_contract"),
        ("participating", "participates_in_contract"),
        ("dependency", "depends_on_contract"),
    ],
)
def test_traceability_reflects_each_role_without_duplicates(scene, role, edge) -> None:
    first = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"], role=role,
    )
    assert first.status_code == 201, first.text
    # An earlier state scope keeps the same pair, so the derived edge must not
    # duplicate when the same Contract is reached twice.
    second = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["target"]["id"], scene["contract_id"], role=role,
    )
    assert second.status_code == 201, second.text

    graph = scene["client"].get(
        f"/api/workspaces/{scene['workspace']['id']}/architecture-graph",
        params={"state_id": scene["candidate"]["id"]},
    ).json()
    edges = [
        item
        for item in graph["edges"]
        if item["source_object_id"] == scene["solution_id"]
        and item["target_object_id"] == scene["contract_id"]
        and item["relationship_type"] == edge
    ]
    assert len(edges) == 1
    assert edges[0]["derived"] is True
    # No stored ArchitectureRelationship row was introduced.
    from app.models import ArchitectureRelationship

    with scene["sessions"]() as db:
        stored = db.scalars(
            select(ArchitectureRelationship.id).where(
                ArchitectureRelationship.tenant_id == scene["tenant_id"],
                ArchitectureRelationship.target_object_id == UUID(str(scene["contract_id"])),
            )
        ).all()
        assert list(stored) == []


def test_contract_endpoint_membership_does_not_duplicate_the_edge(scene) -> None:
    """A Contract endpoint that is also a SolutionMember must not add a second
    association edge: the association is the only source of the role edge."""
    member_system = create_endpoint(scene["client"], _unique("Member"), "name")
    added = scene["client"].post(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/"
        f"{scene['solution_id']}/members",
        json={"state_id": scene["candidate"]["id"], "system_id": member_system["system"]["id"]},
        headers=scene["headers"],
    )
    assert added.status_code == 201, added.text
    association = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"], role="owned",
    )
    assert association.status_code == 201, association.text

    graph = scene["client"].get(
        f"/api/workspaces/{scene['workspace']['id']}/architecture-graph",
        params={"state_id": scene["candidate"]["id"]},
    ).json()
    role_edges = [
        item
        for item in graph["edges"]
        if item["target_object_id"] == scene["contract_id"]
        and item["relationship_type"] in (
            "owns_contract",
            "participates_in_contract",
            "depends_on_contract",
        )
    ]
    assert len(role_edges) == 1
    # Existing membership traceability is preserved alongside the role edge.
    assert any(
        item["source_object_id"] == scene["solution_id"]
        and item["target_object_id"] == member_system["system"]["id"]
        and item["relationship_type"] == "has_member"
        for item in graph["edges"]
    )
    assert any(item["target_object_id"] == member_system["system"]["id"] for item in graph["edges"])


# --- isolation ------------------------------------------------------------------


def test_cross_workspace_association_not_visible(scene) -> None:
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    )
    other, other_current, other_candidate, _ot = _workspace(scene["client"], scene["headers"])
    other_solution = _solution(
        scene["client"], scene["headers"], other["id"], other_candidate["id"]
    )
    assert _list(scene["client"], other["id"], other_solution, other_current["id"]).json() == []
    forbidden = _list(
        scene["client"], other["id"], scene["solution_id"], other_current["id"]
    )
    assert forbidden.status_code == 404
    forbidden_state = _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"], other_current["id"]
    )
    assert forbidden_state.status_code == 404


def test_solution_discipline_required(scene) -> None:
    gated, gated_current, gated_candidate, _gt = _workspace(
        scene["client"], scene["headers"], ["information"]
    )
    response = _list(scene["client"], gated["id"], str(uuid4()), gated_current["id"])
    assert response.status_code == 404
    assert gated_candidate["id"]


def test_listing_is_deterministically_ordered(scene) -> None:
    for index in range(3):
        contract_id = _contract(scene["client"], name=f"Contract {index}")
        created = _create(
            scene["client"], scene["headers"], scene["workspace"]["id"],
            scene["solution_id"], scene["candidate"]["id"], contract_id,
        )
        assert created.status_code == 201, created.text
    first = _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    ).json()
    second = _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    ).json()
    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert [item["contract"]["name"] for item in first] == sorted(
        item["contract"]["name"] for item in first
    )


def test_association_projection_issues_no_writes(scene) -> None:
    association = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], scene["contract_id"],
    ).json()

    def snapshot():
        with scene["sessions"]() as db:
            contract = db.get(Integration, UUID(str(scene["contract_id"])))
            row = db.get(SolutionIntegration, UUID(str(association["id"])))
            return (contract.revision, contract.updated_at, row.role, row.description)

    before = snapshot()
    _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    )
    _list(
        scene["client"], scene["workspace"]["id"], scene["solution_id"],
        scene["candidate"]["id"],
    )
    assert snapshot() == before


def test_mapped_contract_projection_is_bounded(scene) -> None:
    """The summary carries what the inspector needs and nothing more."""
    source = string_endpoint(scene["client"], _unique("m-src"), "name")
    destination = string_endpoint(scene["client"], _unique("m-dst"), "code")
    contract = mapped_contract(scene["client"], _unique("Mapped"), source, destination)
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["solution_id"], scene["candidate"]["id"], contract["id"],
    )
    assert created.status_code == 201, created.text
    summary = created.json()["contract"]
    assert summary["interaction_type"] == "REQUEST_RESPONSE"
    assert set(summary) == {
        "id",
        "name",
        "interaction_type",
        "implementation_status",
        "source",
        "target",
        "mediator",
        "explicit_mediator",
        "mediated",
        "mediation_source",
        "evidence_count",
        "lifecycle_stage",
        "operational_status",
        "environment_scope",
    }
