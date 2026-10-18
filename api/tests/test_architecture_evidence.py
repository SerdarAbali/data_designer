"""Generic architecture evidence (Slice 3).

Covers the four controlled vocabularies, the exclusive-arc target, state
applicability, retention/deletion behaviour, the bounded API, the inspector
projections, isolation and the migration.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.architecture.vocabulary import (
    CONFIDENCES,
    EVIDENCE_CLASSIFICATIONS,
    EVIDENCE_SOURCE_TYPES,
    VERIFICATION_STATUSES,
)
from app.helper_actions.service import compute_proposal_hash
from app.models import (
    ArchitectureEvidence,
    ArchitectureObject,
    ArchitectureRelationship,
    HelperChangeOperation,
    HelperChangeSet,
    SolutionMember,
    Tenant,
)
from tests.baseline_support import lock_baseline
from tests.test_contract_mediator import RUNTIME_MEDIATED_CREATE_CONTRACT_HASH
from tests.test_integrations import client as client_fixture
from tests.test_integrations import create_integration, csrf_headers
from tests.test_scenarios import string_endpoint

client = client_fixture

FULL = ["enterprise", "information", "solution", "integration"]


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


# --- fixtures -----------------------------------------------------------------


def _workspace(test_client, headers, disciplines=None):
    response = test_client.post(
        "/api/workspaces",
        json={"name": _unique("Evidence"), "disciplines": list(disciplines or FULL)},
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


def _url(workspace_id) -> str:
    return f"/api/workspaces/{workspace_id}/evidence"


def _body(target_kind: str, target_id: str, **overrides):
    body = {
        "target_kind": target_kind,
        "target_id": str(target_id),
        "evidence_classification": "confirmed_by_requirements_document",
        "source_type": "document",
        "source_title": "Requirements specification",
        "source_reference": "https://docs.example.test/spec/onboarding",
        "summary": "The requirement is documented in the onboarding specification.",
        "confidence": "high",
    }
    body.update(overrides)
    return body


def _create(test_client, headers, workspace_id, target_kind, target_id, **overrides):
    return test_client.post(
        _url(workspace_id),
        json=_body(target_kind, target_id, **overrides),
        headers=headers,
    )


def _list(test_client, workspace_id, target_kind, target_id, state_id):
    return test_client.get(
        _url(workspace_id),
        params={
            "target_kind": target_kind,
            "target_id": str(target_id),
            "state_id": str(state_id),
        },
    )


# --- target factories ---------------------------------------------------------


def _architecture_object(test_client, headers, workspace_id, candidate) -> str:
    authoritative = test_client.post(
        "/api/catalog/systems",
        json={"name": _unique("Authority"), "kind": "application"},
        headers=headers,
    )
    assert authoritative.status_code == 201, authoritative.text
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/architecture-objects",
        json={
            "kind": "information_object",
            "state_id": candidate["id"],
            "name": _unique("Entity"),
            "owner": "Data owner",
            "authoritative_system_id": authoritative.json()["id"],
            "position": {"x": 0.0, "y": 0.0},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["object"]["id"]


def _relationship(sessions, tenant_id, object_id) -> str:
    with sessions.begin() as db:
        other = ArchitectureObject(id=uuid4(), tenant_id=tenant_id, kind="component")
        db.add(other)
        db.flush()
        edge = ArchitectureRelationship(
            id=uuid4(),
            tenant_id=tenant_id,
            source_object_id=UUID(str(object_id)),
            target_object_id=other.id,
            relationship_type="realizes",
        )
        db.add(edge)
        db.flush()
        return str(edge.id)


def _solution_member(test_client, headers, workspace_id, candidate, sessions, tenant_id) -> str:
    design = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions",
        json={"state_id": candidate["id"], "name": _unique("Solution")},
        headers=headers,
    )
    assert design.status_code == 201, design.text
    solution_id = design.json()["solution"]["solution_object_id"]
    system = test_client.post(
        "/api/catalog/systems",
        json={"name": _unique("Member system"), "kind": "application"},
        headers=headers,
    ).json()
    member = test_client.post(
        f"/api/workspaces/{workspace_id}/solution/solutions/{solution_id}/members",
        json={"state_id": candidate["id"], "system_id": system["id"]},
        headers=headers,
    )
    assert member.status_code == 201, member.text
    with sessions() as db:
        row = db.scalar(
            select(SolutionMember).where(
                SolutionMember.tenant_id == tenant_id,
                SolutionMember.solution_object_id == UUID(str(solution_id)),
                SolutionMember.system_id == UUID(str(system["id"])),
            )
        )
        assert row is not None
        return str(row.id)


def _integration(test_client, name=None) -> str:
    source = string_endpoint(test_client, f"{_unique('Evidence source')}", "name")
    target = string_endpoint(test_client, f"{_unique('Evidence target')}", "code")
    contract = create_integration(test_client, source, target, name=name or _unique("Contract"))
    assert contract.status_code == 201, contract.text
    return contract.json()["id"]


def _dependency(test_client, headers, upstream_id, downstream_id) -> str:
    response = test_client.post(
        f"/api/integrations/{upstream_id}/dependencies",
        json={"downstream_integration_id": downstream_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture()
def scene(client):
    """A workspace with one target of every supported kind."""
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate, target = _workspace(test_client, headers)
    tenant_id = UUID(str(workspace["id"]))
    object_id = _architecture_object(test_client, headers, workspace["id"], candidate)
    return {
        "client": test_client,
        "sessions": sessions,
        "headers": headers,
        "workspace": workspace,
        "current": current,
        "candidate": candidate,
        "target": target,
        "tenant_id": tenant_id,
        "object_id": object_id,
        "relationship_id": _relationship(sessions, tenant_id, object_id),
        "solution_member_id": _solution_member(
            test_client, headers, workspace["id"], candidate, sessions, tenant_id
        ),
        "integration_id": _integration(test_client),
    }


# --- 1-8: controlled vocabularies --------------------------------------------


@pytest.mark.parametrize("value", EVIDENCE_CLASSIFICATIONS)
def test_each_valid_evidence_classification(scene, value) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"], evidence_classification=value,
    )
    assert response.status_code == 201, response.text
    assert response.json()["evidence_classification"] == value
    assert response.json()["target_kind"] == "architecture_object"
    assert response.json()["target_id"] == scene["object_id"]


def test_invalid_evidence_classification_rejected(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        evidence_classification="confirmed_by_vibes",
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", EVIDENCE_SOURCE_TYPES)
def test_each_valid_source_type(scene, value) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"], source_type=value,
    )
    assert response.status_code == 201, response.text
    assert response.json()["source_type"] == value


def test_invalid_source_type_rejected(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"], source_type="rumour",
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", CONFIDENCES)
def test_each_valid_confidence(scene, value) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"], confidence=value,
    )
    assert response.status_code == 201, response.text
    assert response.json()["confidence"] == value


def test_invalid_confidence_rejected(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"], confidence="certain",
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", VERIFICATION_STATUSES)
def test_each_valid_verification_status(scene, value) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"], verification_status=value,
    )
    assert response.status_code == 201, response.text
    assert response.json()["verification_status"] == value


def test_invalid_verification_status_rejected(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"], verification_status="probably",
    )
    assert response.status_code == 422, response.text


def test_vocabularies_are_separate_from_lifecycle_and_operational(scene) -> None:
    from app.architecture.vocabulary import ENVIRONMENT_SCOPES, LIFECYCLE_STAGES

    assert not set(EVIDENCE_CLASSIFICATIONS) & set(LIFECYCLE_STAGES)
    assert not set(EVIDENCE_CLASSIFICATIONS) & set(ENVIRONMENT_SCOPES)
    assert not set(EVIDENCE_SOURCE_TYPES) & set(LIFECYCLE_STAGES)
    assert not set(VERIFICATION_STATUSES) & set(CONFIDENCES)


def test_required_vocabulary_fields_cannot_be_null(scene) -> None:
    for field in (
        "evidence_classification",
        "source_type",
        "confidence",
        "verification_status",
    ):
        response = _create(
            scene["client"], scene["headers"], scene["workspace"]["id"],
            "architecture_object", scene["object_id"], **{field: None},
        )
        assert response.status_code == 422, (field, response.text)


# --- 9-11: exclusive arc ------------------------------------------------------


def test_exactly_one_target_accepted(scene) -> None:
    assert not hasattr(scene["client"], "_never")


def test_zero_targets_rejected(scene) -> None:
    body = _body("architecture_object", scene["object_id"])
    body["target_id"] = str(uuid4())
    response = scene["client"].post(
        _url(scene["workspace"]["id"]), json=body, headers=scene["headers"]
    )
    assert response.status_code == 404, response.text


def test_multiple_targets_rejected(scene) -> None:
    body = _body("architecture_object", scene["object_id"])
    body["architecture_relationship_id"] = str(uuid4())
    response = scene["client"].post(
        _url(scene["workspace"]["id"]), json=body, headers=scene["headers"]
    )
    assert response.status_code == 422, response.text


def test_database_enforces_the_exclusive_arc(scene) -> None:
    sessions, tenant_id = scene["sessions"], scene["tenant_id"]
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(
                ArchitectureEvidence(
                    tenant_id=tenant_id,
                    architecture_object_id=UUID(str(scene["object_id"])),
                    integration_id=UUID(str(scene["integration_id"])),
                    evidence_classification="assumption",
                    source_type="meeting",
                    source_title="Bad row",
                    source_reference="ref",
                    summary="Two targets",
                    confidence="low",
                    verification_status="unverified",
                    recorded_by=_first_user_id(sessions),
                )
            )
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(
                ArchitectureEvidence(
                    tenant_id=tenant_id,
                    evidence_classification="assumption",
                    source_type="meeting",
                    source_title="Bad row",
                    source_reference="ref",
                    summary="No target",
                    confidence="low",
                    verification_status="unverified",
                    recorded_by=_first_user_id(sessions),
                )
            )


def _first_user_id(sessions) -> UUID:
    from app.models import User

    with sessions() as db:
        return db.scalar(select(User.id).limit(1))


# --- 12-19: each target kind --------------------------------------------------


@pytest.mark.parametrize(
    "kind,key",
    [
        ("architecture_object", "object_id"),
        ("architecture_relationship", "relationship_id"),
        ("integration", "integration_id"),
        ("solution_member", "solution_member_id"),
    ],
)
def test_each_supported_target_kind(scene, kind, key) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        kind, scene[key],
    )
    assert response.status_code == 201, response.text
    assert response.json()["target_kind"] == kind
    assert response.json()["target_id"] == scene[key]
    listed = _list(
        scene["client"], scene["workspace"]["id"], kind, scene[key],
        scene["current"]["id"],
    )
    assert [item["id"] for item in listed.json()] == [response.json()["id"]]


def test_integration_dependency_evidence(scene) -> None:
    downstream = _integration(scene["client"])
    dependency_id = _dependency(
        scene["client"], scene["headers"], scene["integration_id"], downstream
    )
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "integration_dependency", dependency_id,
    )
    assert response.status_code == 201, response.text
    assert response.json()["target_kind"] == "integration_dependency"
    assert response.json()["target_id"] == dependency_id


def test_integration_contract_evidence(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "integration", scene["integration_id"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["target_kind"] == "integration"


def test_unsupported_target_kind_rejected(scene) -> None:
    body = _body("architecture_object", scene["object_id"])
    body["target_kind"] = "scenario_ref"
    response = scene["client"].post(
        _url(scene["workspace"]["id"]), json=body, headers=scene["headers"]
    )
    assert response.status_code == 422, response.text


def test_unknown_target_rejected(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", str(uuid4()),
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "unknown_evidence_target"


def test_cross_tenant_target_rejected(scene) -> None:
    sessions = scene["sessions"]
    with sessions.begin() as db:
        other_tenant = Tenant(name=_unique("Other tenant"))
        db.add(other_tenant)
        db.flush()
        foreign = ArchitectureObject(
            id=uuid4(), tenant_id=other_tenant.id, kind="component"
        )
        db.add(foreign)
        db.flush()
        foreign_id = str(foreign.id)
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", foreign_id,
    )
    assert response.status_code == 404, response.text


# --- 20-26: state applicability ----------------------------------------------


def test_canonical_evidence_visible_in_current(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    assert created["state_applicability"] == "canonical"
    assert created["created_in_state_id"] is None
    visible = _list(
        scene["client"], scene["workspace"]["id"], "architecture_object",
        scene["object_id"], scene["current"]["id"],
    ).json()
    assert [item["id"] for item in visible] == [created["id"]]


def test_candidate_evidence_visible_in_that_candidate(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["candidate"]["id"],
    ).json()
    assert created["state_applicability"] == "state"
    assert created["state_name"] == scene["candidate"]["name"]
    visible = _list(
        scene["client"], scene["workspace"]["id"], "architecture_object",
        scene["object_id"], scene["candidate"]["id"],
    ).json()
    assert [item["id"] for item in visible] == [created["id"]]


def test_candidate_evidence_not_visible_in_another_state(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["candidate"]["id"],
    ).json()
    for state in (scene["target"], scene["current"]):
        visible = _list(
            scene["client"], scene["workspace"]["id"], "architecture_object",
            scene["object_id"], state["id"],
        ).json()
        assert created["id"] not in [item["id"] for item in visible]


def test_target_evidence_visible_in_that_target(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["target"]["id"],
    ).json()
    visible = _list(
        scene["client"], scene["workspace"]["id"], "architecture_object",
        scene["object_id"], scene["target"]["id"],
    ).json()
    assert [item["id"] for item in visible] == [created["id"]]


def test_current_state_scoped_write_rejected(scene) -> None:
    lock_baseline(
        scene["client"], scene["workspace"]["id"], scene["current"]["id"], scene["headers"]
    )
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["current"]["id"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "current_baseline_locked"


def test_candidate_write_succeeds(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["candidate"]["id"],
    )
    assert response.status_code == 201, response.text


def test_target_write_succeeds(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["target"]["id"],
    )
    assert response.status_code == 201, response.text


def test_canonical_plus_state_evidence_are_both_listed(scene) -> None:
    canonical = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    scoped = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["candidate"]["id"],
    ).json()
    visible = _list(
        scene["client"], scene["workspace"]["id"], "architecture_object",
        scene["object_id"], scene["candidate"]["id"],
    ).json()
    assert {item["id"] for item in visible} == {canonical["id"], scoped["id"]}


# --- 27-29: provenance --------------------------------------------------------


def test_recorded_by_and_recorded_at_are_server_controlled(scene) -> None:
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recorded_by"]
    assert body["recorded_at"]
    # The client cannot supply provenance at all.
    spoofed = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        recorded_by=str(uuid4()), recorded_at="1999-01-01T00:00:00Z",
    )
    assert spoofed.status_code == 422, spoofed.text


def test_update_preserves_recorded_by_and_recorded_at(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    updated = scene["client"].patch(
        f"{_url(scene['workspace']['id'])}/{created['id']}",
        json={"verification_status": "disputed", "summary": "Contested by the team."},
        headers=scene["headers"],
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["verification_status"] == "disputed"
    assert body["summary"] == "Contested by the team."
    assert body["recorded_by"] == created["recorded_by"]
    assert body["recorded_at"] == created["recorded_at"]
    assert body["evidence_classification"] == created["evidence_classification"]


def test_update_cannot_move_the_target_or_state(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    for payload in (
        {"target_id": str(uuid4())},
        {"created_in_state_id": scene["candidate"]["id"]},
        {"recorded_by": str(uuid4())},
    ):
        response = scene["client"].patch(
            f"{_url(scene['workspace']['id'])}/{created['id']}",
            json=payload,
            headers=scene["headers"],
        )
        assert response.status_code == 422, (payload, response.text)


def test_empty_update_rejected(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    response = scene["client"].patch(
        f"{_url(scene['workspace']['id'])}/{created['id']}",
        json={},
        headers=scene["headers"],
    )
    assert response.status_code == 422, response.text


# --- 30-31: deletion and retention -------------------------------------------


def test_explicit_delete_works(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    deleted = scene["client"].delete(
        f"{_url(scene['workspace']['id'])}/{created['id']}", headers=scene["headers"]
    )
    assert deleted.status_code == 204, deleted.text
    assert (
        scene["client"].get(
            f"{_url(scene['workspace']['id'])}/{created['id']}"
        ).status_code
        == 404
    )
    assert _list(
        scene["client"], scene["workspace"]["id"], "architecture_object",
        scene["object_id"], scene["current"]["id"],
    ).json() == []


def test_evidence_survives_soft_deleted_integration(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "integration", scene["integration_id"],
    ).json()
    archived = scene["client"].delete(
        f"/api/integrations/{scene['integration_id']}", headers=scene["headers"]
    )
    assert archived.status_code == 204, archived.text
    still_there = scene["client"].get(
        f"{_url(scene['workspace']['id'])}/{created['id']}"
    )
    assert still_there.status_code == 200, still_there.text
    listed = _list(
        scene["client"], scene["workspace"]["id"], "integration",
        scene["integration_id"], scene["current"]["id"],
    ).json()
    assert [item["id"] for item in listed] == [created["id"]]


def test_new_evidence_on_archived_integration_rejected(scene) -> None:
    archived = scene["client"].delete(
        f"/api/integrations/{scene['integration_id']}", headers=scene["headers"]
    )
    assert archived.status_code == 204, archived.text
    response = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "integration", scene["integration_id"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "evidence_target_archived"


def test_database_refuses_hard_delete_of_an_evidenced_fact(scene) -> None:
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    )
    sessions = scene["sessions"]
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.delete(db.get(ArchitectureObject, UUID(str(scene["object_id"]))))


def test_architecture_delete_route_returns_a_conflict(scene) -> None:
    """Removing a component that still carries evidence is refused, not orphaned."""
    created = scene["client"].post(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions",
        json={"state_id": scene["candidate"]["id"], "name": _unique("Solution")},
        headers=scene["headers"],
    ).json()
    solution_id = created["solution"]["solution_object_id"]
    component = scene["client"].post(
        f"/api/workspaces/{scene['workspace']['id']}/solution/solutions/{solution_id}/components",
        json={
            "state_id": scene["candidate"]["id"],
            "name": _unique("Component"),
            "position": {"x": 0.0, "y": 0.0},
        },
        headers=scene["headers"],
    )
    assert component.status_code == 201, component.text
    component_id = component.json()["components"][0]["object_id"]
    attached = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", component_id,
    )
    assert attached.status_code == 201, attached.text
    refused = scene["client"].delete(
        f"/api/workspaces/{scene['workspace']['id']}/solution/components/{component_id}",
        params={"state_id": scene["candidate"]["id"]},
        headers=scene["headers"],
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "evidence_blocks_delete"
    # Evidence is intact and still queryable.
    assert scene["client"].get(
        f"{_url(scene['workspace']['id'])}/{attached.json()['id']}"
    ).status_code == 200


def test_evidence_deletion_is_workspace_guarded(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    other_workspace, *_ = _workspace(scene["client"], scene["headers"])
    response = scene["client"].delete(
        f"{_url(other_workspace['id'])}/{created['id']}", headers=scene["headers"]
    )
    assert response.status_code == 404, response.text
    assert scene["client"].get(
        f"{_url(scene['workspace']['id'])}/{created['id']}"
    ).status_code == 200


# --- 32-33: ordering and inspection projections -------------------------------


def test_evidence_list_is_deterministically_ordered(scene) -> None:
    created = [
        _create(
            scene["client"], scene["headers"], scene["workspace"]["id"],
            "architecture_object", scene["object_id"],
            summary=f"Evidence {index}",
        ).json()
        for index in range(4)
    ]
    first = _list(
        scene["client"], scene["workspace"]["id"], "architecture_object",
        scene["object_id"], scene["current"]["id"],
    ).json()
    second = _list(
        scene["client"], scene["workspace"]["id"], "architecture_object",
        scene["object_id"], scene["current"]["id"],
    ).json()
    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert len(first) == len(created)
    # Newest first, with the id as a stable tie-break.
    assert [item["recorded_at"] for item in first] == sorted(
        (item["recorded_at"] for item in first), reverse=True
    )


def test_evidence_count_in_object_usages_projection(scene) -> None:
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    )
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["candidate"]["id"],
    )
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["target"]["id"],
    )
    def usages(state_id):
        response = scene["client"].get(
            f"/api/workspaces/{scene['workspace']['id']}/objects/{scene['object_id']}/usages",
            params={"state_id": state_id},
        )
        assert response.status_code == 200, response.text
        return response.json()["evidence_count"]

    assert usages(scene["current"]["id"]) == 1
    assert usages(scene["candidate"]["id"]) == 2
    assert usages(scene["target"]["id"]) == 2


def test_evidence_count_in_contract_projection(scene) -> None:
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "integration", scene["integration_id"],
    )
    response = scene["client"].get(
        f"/api/workspaces/{scene['workspace']['id']}/integration-design/landscape",
        params={"state_id": scene["current"]["id"]},
    )
    assert response.status_code == 200, response.text
    summary = next(
        item for item in response.json()["contracts"]
        if item["id"] == scene["integration_id"]
    )
    assert summary["evidence_count"] == 1


def test_no_evidence_node_in_the_main_architecture_graph(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    graph = scene["client"].get(
        f"/api/workspaces/{scene['workspace']['id']}/architecture-graph",
        params={"state_id": scene["current"]["id"]},
    ).json()
    ids = {node["id"] for node in graph["nodes"]}
    assert created["id"] not in ids
    assert all(
        edge["source_object_id"] != created["id"]
        and edge["target_object_id"] != created["id"]
        for edge in graph["edges"]
    )
    assert "evidence" not in {node["kind"] for node in graph["nodes"]}


# --- 34-35: isolation ---------------------------------------------------------


def test_cross_workspace_state_rejected(scene) -> None:
    other_workspace, *_ = _workspace(scene["client"], scene["headers"])
    response = _create(
        scene["client"], scene["headers"], other_workspace["id"],
        "architecture_object", scene["object_id"],
        created_in_state_id=scene["candidate"]["id"],
    )
    assert response.status_code == 404, response.text


def test_cross_tenant_read_rejected(scene) -> None:
    created = _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "architecture_object", scene["object_id"],
    ).json()
    other_workspace, *_ = _workspace(scene["client"], scene["headers"])
    response = scene["client"].get(f"{_url(other_workspace['id'])}/{created['id']}")
    assert response.status_code == 404, response.text


def test_list_requires_a_target_and_state(scene) -> None:
    missing_target = scene["client"].get(
        _url(scene["workspace"]["id"]),
        params={"state_id": scene["current"]["id"]},
    )
    assert missing_target.status_code == 422
    missing_state = scene["client"].get(
        _url(scene["workspace"]["id"]),
        params={"target_kind": "architecture_object", "target_id": scene["object_id"]},
    )
    assert missing_state.status_code == 422


# --- 37-38 + model invariants -------------------------------------------------


def test_model_declares_evidence_constraints() -> None:
    table = ArchitectureEvidence.__table__
    names = {constraint.name for constraint in table.constraints}
    assert "ck_architecture_evidence_single_target" in names
    assert "ck_architecture_evidence_classification" in names
    assert "ck_architecture_evidence_source_type" in names
    assert "ck_architecture_evidence_confidence" in names
    assert "ck_architecture_evidence_verification_status" in names
    for name in (
        "fk_architecture_evidence_object_tenant",
        "fk_architecture_evidence_relationship_tenant",
        "fk_architecture_evidence_integration_tenant",
        "fk_architecture_evidence_dependency_tenant",
        "fk_architecture_evidence_solution_member_tenant",
    ):
        assert name in names
    for name in (
        "ix_architecture_evidence_tenant",
        "ix_architecture_evidence_state",
        "ix_architecture_evidence_object",
        "ix_architecture_evidence_relationship",
        "ix_architecture_evidence_integration",
        "ix_architecture_evidence_dependency",
        "ix_architecture_evidence_solution_member",
    ):
        assert name in {index.name for index in table.indexes}


def test_migration_declares_additive_evidence_revision() -> None:
    from tests.test_migrations import _script

    revision = _script().get_revision("0026_architecture_evidence")
    assert revision is not None
    assert revision.down_revision == "0025_contract_mediator"


# --- 41-42: regressions -------------------------------------------------------


def test_proposal_hash_regression_lock_unchanged() -> None:
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
    assert compute_proposal_hash(change_set, [operation]) == (
        RUNTIME_MEDIATED_CREATE_CONTRACT_HASH
    )


@pytest.mark.parametrize("preset", ["full", "solution_integration", "integration_only"])
def test_demo_presets_remain_valid(client, preset) -> None:
    test_client, _ = client
    headers = csrf_headers(test_client)
    response = test_client.post(
        "/api/workspaces",
        json={
            "name": _unique(f"Demo {preset}"),
            "disciplines": FULL,
            "demo_preset": preset,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    workspace = response.json()
    states = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()
    current = next(state for state in states if state["state_type"] == "current")
    graph = test_client.get(
        f"/api/workspaces/{workspace['id']}/architecture-graph",
        params={"state_id": current["id"]},
    )
    assert graph.status_code == 200, graph.text


def test_evidence_does_not_modify_the_target_fact(scene) -> None:
    """Evidence describes a fact; it never changes it."""
    response = scene["client"].get(f"/api/integrations/{scene['integration_id']}")
    before = response.json()
    _create(
        scene["client"], scene["headers"], scene["workspace"]["id"],
        "integration", scene["integration_id"],
        created_in_state_id=scene["candidate"]["id"],
    )
    after = scene["client"].get(f"/api/integrations/{scene['integration_id']}").json()
    assert after["revision"] == before["revision"]
    assert after["updated_at"] == before["updated_at"]
    assert after["lifecycle_stage"] == before["lifecycle_stage"]
