"""Solution Landscape (Slice 6).

Risk-based coverage: the read-only projection, typed Solution relationships,
state scoping, and the bounded query behaviour.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select

from app.models import ArchitectureRelationship, SolutionIntegration
from tests.baseline_support import lock_baseline
from tests.test_integrations import client as client_fixture
from tests.test_integrations import create_endpoint, create_integration, csrf_headers
from tests.test_scenarios import string_endpoint

client = client_fixture

FULL = ["enterprise", "information", "solution", "integration"]


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _workspace(test_client, headers, disciplines=None):
    response = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Landscape"), "disciplines": list(disciplines or FULL)},
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


def _solution(test_client, headers, workspace_id, state_id, name=None, owner=None) -> str:
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions",
        json={
            "state_id": state_id,
            "name": name or _unique("Solution"),
            "owner": owner,
            "position": {"x": 0.0, "y": 0.0},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["solution"]["solution_object_id"]


def _add_member(test_client, headers, workspace_id, solution_id, state_id, system_id):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions/{solution_id}/members",
        json={"state_id": state_id, "system_id": system_id},
        headers=headers,
    )


def _contract(test_client, name=None) -> str:
    source = string_endpoint(test_client, _unique("src"), "name")
    destination = string_endpoint(test_client, _unique("dst"), "code")
    response = create_integration(
        test_client, source, destination, name=name or _unique("Contract")
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _associate(
    test_client, headers, workspace_id, solution_id, state_id, contract_id, role="owned"
):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions/{solution_id}/contracts",
        json={"state_id": state_id, "integration_id": contract_id, "role": role},
        headers=headers,
    )


def _landscape(test_client, workspace_id, state_id):
    response = test_client.get(
        f"/api/workspaces/{workspace_id}/solution/landscape", params={"state_id": state_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _node(landscape, solution_id):
    return next(
        item for item in landscape["solutions"] if item["solution_object_id"] == solution_id
    )


def _relate(
    test_client, headers, workspace_id, source_id, target_id, state_id, rel="depends_on", **extra
):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/solution/relationships",
        json={
            "state_id": state_id,
            "source_object_id": source_id,
            "target_object_id": target_id,
            "relationship_type": rel,
            **extra,
        },
        headers=headers,
    )


@pytest.fixture()
def scene(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate, target = _workspace(test_client, headers)
    alpha = _solution(test_client, headers, workspace["id"], candidate["id"], "Alpha", "Owner A")
    beta = _solution(test_client, headers, workspace["id"], candidate["id"], "Beta")
    return {
        "client": test_client,
        "sessions": sessions,
        "headers": headers,
        "workspace": workspace,
        "current": current,
        "candidate": candidate,
        "target": target,
        "alpha": alpha,
        "beta": beta,
        "tenant_id": UUID(str(workspace["id"])),
    }


# --- 1: projection -------------------------------------------------------------


def test_landscape_returns_multiple_solutions_with_deterministic_summaries(scene) -> None:
    member = create_endpoint(scene["client"], _unique("Member"), "name")
    added = _add_member(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["candidate"]["id"], member["system"]["id"],
    )
    assert added.status_code == 201, added.text
    external = create_endpoint(scene["client"], _unique("External"), "name")
    placed = scene["client"].post(
        f"/api/workspaces/{scene['workspace']['id']}/states/{scene['candidate']['id']}/include-objects",
        json={"system_ids": [external["system"]["id"]]},
        headers=scene["headers"],
    )
    assert placed.status_code in (200, 201), placed.text

    first = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    second = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert [item["solution_object_id"] for item in first["solutions"]] == [
        item["solution_object_id"] for item in second["solutions"]
    ]
    assert [item["name"] for item in first["solutions"]] == ["Alpha", "Beta"]
    alpha = _node(first, scene["alpha"])
    assert alpha["owner"] == "Owner A"
    assert alpha["member_count"] == 1
    assert alpha["members"][0]["system_id"] == member["system"]["id"]
    assert alpha["component_count"] == 0
    assert alpha["evidence_count"] == 0
    assert alpha["lifecycle_stage"] is None and alpha["operational_status"] is None
    assert alpha["contract_counts"] == {
        "owned": 0,
        "participating": 0,
        "dependency": 0,
        "total": 0,
    }
    # External participation reuses the Solution Context semantics: a system on
    # the canvas that is not a member of *this* boundary.
    external_ids = {item["system_id"] for item in alpha["external_systems"]}
    assert external["system"]["id"] in external_ids
    assert member["system"]["id"] not in external_ids
    assert alpha["external_system_count"] == len(external_ids)
    assert all(item["external"] for item in alpha["external_systems"])
    beta = _node(first, scene["beta"])
    assert beta["owner"] is None
    assert member["system"]["id"] in {item["system_id"] for item in beta["external_systems"]}


def test_landscape_contract_role_counts_come_only_from_associations(scene) -> None:
    """Endpoint membership must never imply ownership."""
    member = create_endpoint(scene["client"], _unique("NotOwner"), "name")
    _add_member(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["candidate"]["id"], member["system"]["id"],
    )
    first_contract = _contract(scene["client"])
    # The Contract uses a member system as an endpoint, but is not associated.
    unowned = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert _node(unowned, scene["alpha"])["contract_counts"]["total"] == 0

    second_contract = _contract(scene["client"])
    third_contract = _contract(scene["client"])
    for solution_id, contract_id, role in (
        (scene["alpha"], first_contract, "owned"),
        (scene["alpha"], second_contract, "participating"),
        (scene["beta"], third_contract, "dependency"),
    ):
        created = _associate(
            scene["client"], scene["headers"], scene["workspace"]["id"],
            solution_id, scene["candidate"]["id"], contract_id, role,
        )
        assert created.status_code == 201, created.text

    landscape = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    alpha = _node(landscape, scene["alpha"])
    beta = _node(landscape, scene["beta"])
    assert alpha["contract_counts"] == {
        "owned": 1,
        "participating": 1,
        "dependency": 0,
        "total": 2,
    }
    assert beta["contract_counts"]["dependency"] == 1
    assert {item["role"] for item in alpha["contracts"]} == {"owned", "participating"}
    # The bounded summary carries no Contract internals.
    for forbidden in ("specification", "phases", "scenarios", "producer_interface"):
        assert forbidden not in alpha["contracts"][0]


def test_landscape_surfaces_an_archived_contract_association(scene) -> None:
    contract = _contract(scene["client"])
    _associate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["candidate"]["id"], contract,
    )
    # Archiving is blocked while associated (Slice 5), so archive before the
    # association exists and then associate directly to simulate legacy data.
    with scene["sessions"].begin() as db:
        from app.models import Integration

        row = db.get(Integration, UUID(str(contract)))
        row.deleted_at = row.updated_at

    landscape = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    alpha = _node(landscape, scene["alpha"])
    entry = alpha["contracts"][0]
    assert entry["available"] is False
    assert entry["contract_id"] == contract
    assert entry["implementation_status"] is None
    codes = {warning["code"] for warning in landscape["warnings"]}
    assert "archived_contract_association" in codes
    warning = next(
        item for item in landscape["warnings"] if item["code"] == "archived_contract_association"
    )
    assert warning["solution_object_id"] == scene["alpha"]
    assert warning["integration_id"] == contract


# --- 2-4: state behaviour -------------------------------------------------------


def test_candidate_only_solution_and_relationship_isolation(scene) -> None:
    created = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"],
    )
    assert created.status_code == 201, created.text
    assert created.json()["state_applicability"] == "state"

    candidate = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert [item["relationship_type"] for item in candidate["relationships"]] == ["depends_on"]
    assert _node(candidate, scene["alpha"])["relationships_out"] == 1
    assert _node(candidate, scene["beta"])["relationships_in"] == 1

    # Another state sees neither the relationship nor a Candidate-only solution.
    target = _landscape(scene["client"], scene["workspace"]["id"], scene["target"]["id"])
    assert target["relationships"] == []
    late = _solution(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["candidate"]["id"], "Candidate only",
    )
    again = _landscape(scene["client"], scene["workspace"]["id"], scene["target"]["id"])
    assert late not in [item["solution_object_id"] for item in again["solutions"]]
    in_candidate = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert late in [item["solution_object_id"] for item in in_candidate["solutions"]]


def test_current_relationship_write_rejected(scene) -> None:
    lock_baseline(
        scene["client"], scene["workspace"]["id"], scene["current"]["id"], scene["headers"]
    )
    created = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["current"]["id"],
    )
    assert created.status_code == 409, created.text
    assert created.json()["detail"]["code"] == "current_baseline_locked"
    # Current is still readable.
    assert _landscape(scene["client"], scene["workspace"]["id"], scene["current"]["id"])[
        "editable"
    ] is False


def test_candidate_and_target_are_editable(scene) -> None:
    for state in (scene["candidate"], scene["target"]):
        landscape = _landscape(scene["client"], scene["workspace"]["id"], state["id"])
        assert landscape["editable"] is True


# --- 5-7: relationships ---------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "depends_on",
        "uses",
        "provides_to",
        "replaces",
        "transitions_to",
        "shares_information_with",
    ],
)
def test_each_approved_relationship_type_round_trips(scene, rel) -> None:
    created = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"], rel=rel,
        description="Why this exists.",
    )
    assert created.status_code == 201, created.text
    assert created.json()["relationship_type"] == rel
    assert created.json()["description"] == "Why this exists."
    assert created.json()["source_object_id"] == scene["alpha"]
    assert created.json()["target_object_id"] == scene["beta"]

    landscape = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    edge = landscape["relationships"][0]
    assert edge["id"] == created.json()["id"]
    assert edge["description"] == "Why this exists."
    assert edge["source_object_id"] == scene["alpha"]
    assert edge["target_object_id"] == scene["beta"]

    removed = scene["client"].delete(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/"
        f"{created.json()['id']}",
        params={"state_id": scene["candidate"]["id"]},
        headers=scene["headers"],
    )
    assert removed.status_code == 204, removed.text
    # Both Solution Boundaries are untouched.
    after = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert after["relationships"] == []
    assert {item["solution_object_id"] for item in after["solutions"]} == {
        scene["alpha"],
        scene["beta"],
    }


def test_invalid_relationship_type_rejected(scene) -> None:
    response = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"], rel="depends_upon",
    )
    assert response.status_code == 422, response.text


def test_self_relationship_rejected(scene) -> None:
    response = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["alpha"], scene["candidate"]["id"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "self_relationship"


def test_non_solution_endpoint_rejected(scene) -> None:
    component = create_endpoint(scene["client"], _unique("Component"), "name")
    response = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], component["object"]["id"], scene["candidate"]["id"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "not_a_solution"


def test_cross_tenant_endpoint_rejected(scene) -> None:
    other, _oc, other_candidate, _ot = _workspace(scene["client"], scene["headers"])
    foreign = _solution(
        scene["client"], scene["headers"], other["id"], other_candidate["id"], "Foreign"
    )
    response = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], foreign, scene["candidate"]["id"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "not_a_solution"


def test_duplicate_relationship_rejected(scene) -> None:
    first = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"],
    )
    assert first.status_code == 201, first.text
    duplicate = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"],
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "duplicate_solution_relationship"
    # A different vocabulary value is a different relationship.
    other = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"], rel="uses",
    )
    assert other.status_code == 201, other.text
    # The reverse direction is also distinct.
    reverse = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["beta"], scene["alpha"], scene["candidate"]["id"],
    )
    assert reverse.status_code == 201, reverse.text


def test_relationship_update_and_canonical_protection(scene) -> None:
    created = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"], description="First",
    ).json()
    updated = scene["client"].patch(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{created['id']}",
        params={"state_id": scene["candidate"]["id"]},
        json={"relationship_type": "uses", "description": "Now uses."},
        headers=scene["headers"],
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["relationship_type"] == "uses"
    assert updated.json()["description"] == "Now uses."
    empty = scene["client"].patch(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{created['id']}",
        params={"state_id": scene["candidate"]["id"]},
        json={},
        headers=scene["headers"],
    )
    assert empty.status_code == 422, empty.text
    # Endpoints cannot be re-pointed.
    moved = scene["client"].patch(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{created['id']}",
        params={"state_id": scene["candidate"]["id"]},
        json={"source_object_id": scene["beta"]},
        headers=scene["headers"],
    )
    assert moved.status_code == 422, moved.text

    # A canonical relationship belongs to the Current baseline and is protected.
    with scene["sessions"].begin() as db:
        db.add(
            ArchitectureRelationship(
                tenant_id=scene["tenant_id"],
                source_object_id=UUID(str(scene["alpha"])),
                target_object_id=UUID(str(scene["beta"])),
                relationship_type="replaces",
                properties={"description": "Canonical"},
                created_in_state_id=None,
            )
        )
    canonical = next(
        item
        for item in _landscape(
            scene["client"], scene["workspace"]["id"], scene["candidate"]["id"]
        )["relationships"]
        if item["relationship_type"] == "replaces"
    )
    blocked_update = scene["client"].patch(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{canonical['id']}",
        params={"state_id": scene["candidate"]["id"]},
        json={"description": "Changed"},
        headers=scene["headers"],
    )
    assert blocked_update.status_code == 409, blocked_update.text
    assert blocked_update.json()["detail"]["code"] == "canonical_relationship_readonly"
    blocked_delete = scene["client"].delete(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{canonical['id']}",
        params={"state_id": scene["candidate"]["id"]},
        headers=scene["headers"],
    )
    assert blocked_delete.status_code == 409, blocked_delete.text


def test_evidence_blocks_relationship_deletion(scene) -> None:
    created = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"],
    ).json()
    attached = scene["client"].post(
        f"/api/workspaces/{scene['workspace']['id']}/evidence",
        json={
            "target_kind": "architecture_relationship",
            "target_id": created["id"],
            "evidence_classification": "assumption",
            "source_type": "meeting",
            "source_title": "Design review",
            "source_reference": "notes/1",
            "summary": "Assumed the dependency.",
            "confidence": "medium",
        },
        headers=scene["headers"],
    )
    assert attached.status_code == 201, attached.text
    landscape = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert landscape["relationships"][0]["evidence_count"] == 1
    refused = scene["client"].delete(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{created['id']}",
        params={"state_id": scene["candidate"]["id"]},
        headers=scene["headers"],
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "evidence_blocks_delete"
    # Deleting the evidence first lets the relationship go.
    removed = scene["client"].delete(
        f"/api/workspaces/{scene['workspace']['id']}/evidence/{attached.json()['id']}",
        headers=scene["headers"],
    )
    assert removed.status_code == 204, removed.text
    assert scene["client"].delete(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{created['id']}",
        params={"state_id": scene["candidate"]["id"]},
        headers=scene["headers"],
    ).status_code == 204


def test_relationship_from_another_state_is_not_reachable(scene) -> None:
    created = _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"],
    ).json()
    response = scene["client"].delete(
        f"/api/workspaces/{scene['workspace']['id']}/solution/relationships/{created['id']}",
        params={"state_id": scene["target"]["id"]},
        headers=scene["headers"],
    )
    assert response.status_code == 404, response.text


# --- 8: bounded queries --------------------------------------------------------


def _select_count(sessions, action) -> int:
    engine = sessions().get_bind()
    counter = {"count": 0}

    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith("SELECT"):
            counter["count"] += 1

    event.listen(engine, "before_cursor_execute", record)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return counter["count"]


def test_landscape_projection_uses_bounded_bulk_queries(scene) -> None:
    contract = _contract(scene["client"])
    _associate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["candidate"]["id"], contract,
    )
    one = _select_count(
        scene["sessions"],
        lambda: _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"]),
    )
    for index in range(3):
        extra = _solution(
            scene["client"], scene["headers"], scene["workspace"]["id"],
            scene["candidate"]["id"], f"Extra {index}",
        )
        member = create_endpoint(scene["client"], _unique(f"Member {index}"), "name")
        _add_member(
            scene["client"], scene["headers"], scene["workspace"]["id"],
            extra, scene["candidate"]["id"], member["system"]["id"],
        )
        _associate(
            scene["client"], scene["headers"], scene["workspace"]["id"],
            extra, scene["candidate"]["id"], contract, role="dependency",
        )
    many = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert len(many["solutions"]) == 5
    three = _select_count(
        scene["sessions"],
        lambda: _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"]),
    )
    # The projection is bulk-loaded: adding Solutions adds no queries.
    assert three == one


# --- isolation and empty states -------------------------------------------------


def test_empty_landscape_is_not_an_error(scene) -> None:
    empty, _ec, empty_candidate, _et = _workspace(scene["client"], scene["headers"])
    landscape = _landscape(scene["client"], empty["id"], empty_candidate["id"])
    assert landscape["solutions"] == []
    assert landscape["relationships"] == []
    assert landscape["warnings"] == []
    assert landscape["editable"] is True


def test_solution_with_no_relationships_or_contracts(scene) -> None:
    landscape = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    alpha = _node(landscape, scene["alpha"])
    assert alpha["relationships_in"] == 0
    assert alpha["relationships_out"] == 0
    assert alpha["contracts"] == []
    assert alpha["contract_counts"]["total"] == 0


def test_landscape_requires_the_solution_discipline(scene) -> None:
    gated, _gc, gated_candidate, _gt = _workspace(
        scene["client"], scene["headers"], ["information"]
    )
    response = scene["client"].get(
        f"/api/workspaces/{gated['id']}/solution/landscape",
        params={"state_id": gated_candidate["id"]},
    )
    assert response.status_code == 404


def test_landscape_rejects_a_state_from_another_workspace(scene) -> None:
    other, other_current, _oc, _ot = _workspace(scene["client"], scene["headers"])
    response = scene["client"].get(
        f"/api/workspaces/{other['id']}/solution/landscape",
        params={"state_id": scene["candidate"]["id"]},
    )
    assert response.status_code == 404
    assert other_current["id"]


def test_landscape_issues_no_writes(scene) -> None:
    _relate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["beta"], scene["candidate"]["id"],
    )

    def snapshot():
        with scene["sessions"]() as db:
            rows = db.scalars(
                select(ArchitectureRelationship).where(
                    ArchitectureRelationship.tenant_id == scene["tenant_id"]
                )
            ).all()
            return [(row.id, row.relationship_type, dict(row.properties or {})) for row in rows]

    before = snapshot()
    _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert snapshot() == before


def test_association_is_kept_out_of_unrelated_solutions(scene) -> None:
    contract = _contract(scene["client"])
    _associate(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        scene["alpha"], scene["candidate"]["id"], contract,
    )
    landscape = _landscape(scene["client"], scene["workspace"]["id"], scene["candidate"]["id"])
    assert _node(landscape, scene["beta"])["contract_counts"]["total"] == 0
    with scene["sessions"]() as db:
        assert db.scalar(select(SolutionIntegration.id).limit(1)) is not None
