from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    ArchitectureStateMember,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    HelperAuditEvent,
    HelperChangeOperation,
    HelperChangeSet,
    Integration,
    Scenario,
    Tenant,
    User,
)

FULL = ["enterprise", "information", "solution", "integration"]


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
        tenant = Tenant(name=f"helper-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="helper@example.test",
                password_hash=hash_password("helper-test-password"),
            )
        )
    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "helper@example.test", "password": "helper-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": test_client.cookies["dd_csrf"]}


def _workspace(test_client, headers, disciplines=None, name=None):
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": name or f"Helper {uuid4().hex[:8]}", "disciplines": disciplines or FULL},
        headers=headers,
    ).json()
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    candidate = test_client.post(
        f"/api/workspaces/{workspace['id']}/states/{current['id']}/duplicate",
        json={"target_name": "Candidate Design"},
        headers=headers,
    ).json()
    return workspace, current, candidate


def _system(test_client, headers, name="CRM"):
    response = test_client.post(
        "/api/catalog/systems", json={"name": name, "kind": "application"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _capability(test_client, headers, workspace_id, state_id, system_id, name):
    response = test_client.post(
        f"/api/workspaces/{workspace_id}/architecture-objects",
        json={
            "kind": "business_capability",
            "state_id": state_id,
            "name": name,
            "related_system_id": system_id,
            "position": {"x": 10.0, "y": 10.0},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["object"]


def _read(test_client, headers, workspace_id, helper, body=None):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/helper-actions/reads/{helper}",
        json=body or {},
        headers=headers,
    )


def _propose(test_client, headers, workspace_id, body, helper="propose_fixture"):
    return test_client.post(
        f"/api/workspaces/{workspace_id}/helper-actions/proposals/{helper}",
        json=body,
        headers=headers,
    )


def _fixture_body(state_id, operations=None, summary="Fixture proposal"):
    return {
        "state_id": state_id,
        "summary": summary,
        "operations": operations or [],
    }


def _counts(sessions):
    with sessions() as db:
        return {
            "architecture_objects": db.scalar(select(func.count(ArchitectureObject.id))),
            "relationships": db.scalar(select(func.count(ArchitectureRelationship.id))),
            "state_members": db.scalar(select(func.count(ArchitectureStateMember.id))),
            "systems": db.scalar(select(func.count(CatalogSystem.id))),
            "catalog_objects": db.scalar(select(func.count(CatalogObject.id))),
            "catalog_fields": db.scalar(select(func.count(CatalogField.id))),
            "integrations": db.scalar(select(func.count(Integration.id))),
            "scenarios": db.scalar(select(func.count(Scenario.id))),
        }


def _user_id(sessions):
    with sessions() as db:
        return db.scalar(select(User.id))


def test_read_helper_requires_authentication(client):
    test_client, _ = client
    workspace, _current, _candidate = _workspace(test_client, csrf_headers(test_client))
    test_client.cookies.clear()
    response = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/reads/get_enabled_disciplines",
        json={},
    )
    assert response.status_code == 401


def test_unknown_field_is_rejected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, _candidate = _workspace(test_client, headers)
    response = _read(test_client, headers, workspace["id"], "get_workspace_context", {"bogus": 1})
    assert response.status_code == 422


def test_workspace_and_tenant_isolation(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace_a, _ca, _cand_a = _workspace(test_client, headers)
    workspace_b, current_b, _cand_b = _workspace(test_client, headers)
    # A state from workspace A cannot be read through workspace B.
    response = _read(
        test_client,
        headers,
        workspace_b["id"],
        "get_architecture_state",
        {"state_id": current_b["id"]},
    )
    assert response.status_code == 200
    foreign = _read(
        test_client,
        headers,
        workspace_a["id"],
        "get_architecture_state",
        {"state_id": current_b["id"]},
    )
    assert foreign.status_code == 404


def test_disabled_discipline_read_is_rejected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers, disciplines=["information"])
    response = _read(
        test_client,
        headers,
        workspace["id"],
        "list_integration_contracts",
        {"state_id": current["id"]},
    )
    assert response.status_code == 404
    assert "not enabled" in response.json()["detail"].lower()


def test_read_helpers_are_structured_and_deterministic(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, _candidate = _workspace(test_client, headers)
    first = _read(test_client, headers, workspace["id"], "get_workspace_context")
    second = _read(test_client, headers, workspace["id"], "get_workspace_context")
    assert first.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["helper"] == "get_workspace_context"
    assert body["workspace_id"] == workspace["id"]
    assert set(body["data"]["disciplines"]) == set(FULL)

    disciplines = _read(test_client, headers, workspace["id"], "get_enabled_disciplines").json()
    assert sorted(disciplines["data"]["disciplines"]) == sorted(FULL)


def test_current_state_is_readable(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace = test_client.post(
        "/api/workspaces",
        json={"name": f"Cur {uuid4().hex[:8]}", "disciplines": FULL},
        headers=headers,
    ).json()
    system = _system(test_client, headers)
    current = test_client.get(f"/api/workspaces/{workspace['id']}/states").json()[0]
    assert current["state_type"] == "current"

    state_read = _read(
        test_client, headers, workspace["id"], "get_architecture_state", {"state_id": current["id"]}
    )
    assert state_read.status_code == 200
    assert state_read.json()["data"]["state_type"] == "current"

    trace = _read(
        test_client,
        headers,
        workspace["id"],
        "trace_architecture_path",
        {"state_id": current["id"], "object_id": system["id"], "depth": 2},
    )
    assert trace.status_code == 200
    assert trace.json()["data"]["root"]["id"] == system["id"]


def test_search_is_bounded_and_reports_truncation(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    system = _system(test_client, headers)
    for index in range(3):
        _capability(
            test_client,
            headers,
            workspace["id"],
            candidate["id"],
            system["id"],
            f"Cap {index}",
        )

    response = _read(
        test_client,
        headers,
        workspace["id"],
        "search_canonical_objects",
        {"query": "Cap", "limit": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is True
    assert body["limit"] == 1
    assert len(body["data"]["objects"]) == 1
    assert body["counts"]["total"] == 3


def test_proposal_requires_csrf(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    response = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/proposals/propose_fixture",
        json=_fixture_body(candidate["id"]),
    )
    assert response.status_code == 403


def test_unknown_proposal_helper_is_rejected_and_audited(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        _fixture_body(candidate["id"]),
        helper="nope",
    )
    assert response.status_code == 404
    with sessions() as db:
        events = list(db.scalars(select(HelperAuditEvent.event_type)))
    assert "proposal_rejected" in events


def test_proposal_targeting_current_is_rejected_and_audited(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, _candidate = _workspace(test_client, headers)
    response = _propose(test_client, headers, workspace["id"], _fixture_body(current["id"]))
    assert response.status_code == 409
    with sessions() as db:
        events = list(db.scalars(select(HelperAuditEvent.event_type)))
    assert "proposal_rejected" in events


def test_proposal_creation_makes_no_domain_changes(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, current, candidate = _workspace(test_client, headers)
    system = _system(test_client, headers)
    _capability(test_client, headers, workspace["id"], candidate["id"], system["id"], "Cap")

    before = _counts(sessions)
    with sessions() as db:
        current_nodes_before = db.get(ArchitectureState, UUID(current["id"])).nodes

    response = _propose(
        test_client,
        headers,
        workspace["id"],
        _fixture_body(
            candidate["id"],
            operations=[
                {
                    "operation_id": "op-1",
                    "domain_action": "reuse_existing_object",
                    "target_type": "architecture_object",
                    "target_id": system["id"],
                    "proposed_value": {"note": "reuse"},
                }
            ],
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["proposal_hash"]
    assert body["reused_objects"][0]["target_id"] == system["id"]

    assert _counts(sessions) == before
    with sessions() as db:
        current_nodes_after = db.get(ArchitectureState, UUID(current["id"])).nodes
    assert current_nodes_after == current_nodes_before

    # The change set is retrievable, proving helper lifecycle persistence only.
    url = (
        f"/api/workspaces/{workspace['id']}"
        f"/helper-actions/change-sets/{body['id']}"
    )
    fetched = test_client.get(url, headers=headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["operations"]) == 1


def test_validation_detects_unknown_target_and_dependency(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)

    response = _propose(
        test_client,
        headers,
        workspace["id"],
        _fixture_body(
            candidate["id"],
            operations=[
                {
                    "operation_id": "op-1",
                    "domain_action": "reference_object",
                    "target_type": "architecture_object",
                    "target_id": str(uuid4()),
                },
                {
                    "operation_id": "op-2",
                    "domain_action": "reference_object",
                    "depends_on": ["missing-op"],
                },
            ],
        ),
    )
    assert response.status_code == 201, response.text
    change_set_id = response.json()["id"]

    validated = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{change_set_id}/validate",
        headers=headers,
    )
    assert validated.status_code == 200
    result = validated.json()
    assert result["status"] == "validation_failed"
    codes = {issue["code"] for issue in result["validation_summary"]["issues"]}
    assert "unknown_target" in codes
    assert "unknown_dependency" in codes


def test_validation_detects_dependency_cycle(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    response = _propose(
        test_client,
        headers,
        workspace["id"],
        _fixture_body(
            candidate["id"],
            operations=[
                {"operation_id": "a", "domain_action": "reference_object", "depends_on": ["b"]},
                {"operation_id": "b", "domain_action": "reference_object", "depends_on": ["a"]},
            ],
        ),
    )
    change_set_id = response.json()["id"]
    validated = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{change_set_id}/validate",
        headers=headers,
    )
    assert validated.json()["status"] == "validation_failed"
    codes = {issue["code"] for issue in validated.json()["validation_summary"]["issues"]}
    assert "dependency_cycle" in codes


def test_proposal_hash_is_deterministic(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    ops = [
        {"operation_id": "op-a", "domain_action": "reuse_existing_object"},
        {"operation_id": "op-b", "domain_action": "reference_object", "depends_on": ["op-a"]},
    ]
    first = _propose(test_client, headers, workspace["id"], _fixture_body(candidate["id"], ops))
    second = _propose(
        test_client, headers, workspace["id"], _fixture_body(candidate["id"], list(reversed(ops)))
    )
    assert first.json()["proposal_hash"] == second.json()["proposal_hash"]


def test_approval_requires_validation(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    created = _propose(test_client, headers, workspace["id"], _fixture_body(candidate["id"])).json()
    response = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/approve",
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_validated"


def test_approval_binds_to_hash_and_mutation_invalidates(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    created = _propose(
        test_client,
        headers,
        workspace["id"],
        _fixture_body(
            candidate["id"],
            [{"operation_id": "op-1", "domain_action": "reuse_existing_object"}],
        ),
    ).json()
    validated = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/validate",
        headers=headers,
    ).json()
    assert validated["status"] == "validated"
    approved = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/approve",
        headers=headers,
    ).json()
    assert approved["status"] == "approved"
    assert approved["approved_hash"] == approved["proposal_hash"]

    # Mutate the proposal out-of-band; this must invalidate validation + approval.
    with sessions() as db:
        op = db.scalar(
            select(HelperChangeOperation).where(
                HelperChangeOperation.change_set_id == UUID(created["id"])
            )
        )
        op.proposed_value = {"changed": True}
        db.commit()

    status_body = test_client.get(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/status",
        headers=headers,
    ).json()
    assert status_body["status"] == "stale"
    assert status_body["approved_by"] is None
    assert status_body["proposal_hash"] != status_body["current_hash"]

    retry = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/approve",
        headers=headers,
    )
    assert retry.status_code == 409


def test_self_approval_records_proposer_and_approver_independently(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    created = _propose(test_client, headers, workspace["id"], _fixture_body(candidate["id"])).json()
    test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/validate",
        headers=headers,
    )
    approved = test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/approve",
        headers=headers,
    ).json()
    user_id = str(_user_id(sessions))
    assert approved["proposed_by"] == user_id
    assert approved["approved_by"] == user_id
    assert approved["approved_at"] is not None

    with sessions() as db:
        event = db.scalar(
            select(HelperAuditEvent).where(
                HelperAuditEvent.change_set_id == UUID(created["id"]),
                HelperAuditEvent.event_type == "approved",
            )
        )
        assert event.summary["proposed_by"] == user_id
        assert event.summary["approved_by"] == user_id


def test_cross_workspace_references_are_rejected(client):
    test_client, _ = client
    headers = csrf_headers(test_client)
    workspace_a, _ca, candidate_a = _workspace(test_client, headers)
    system_a = _system(test_client, headers, name="CRM-A")
    capability_a = _capability(
        test_client, headers, workspace_a["id"], candidate_a["id"], system_a["id"], "Cap A"
    )
    workspace_b, _cb, candidate_b = _workspace(test_client, headers)

    # A state from workspace A is not visible through workspace B.
    foreign_state = _propose(
        test_client, headers, workspace_b["id"], _fixture_body(candidate_a["id"])
    )
    assert foreign_state.status_code == 404

    # A canonical object from another tenant fails validation in workspace B.
    proposal = _propose(
        test_client,
        headers,
        workspace_b["id"],
        _fixture_body(
            candidate_b["id"],
            [
                {
                    "operation_id": "op-1",
                    "domain_action": "reference_object",
                    "target_id": capability_a["id"],
                }
            ],
        ),
    ).json()
    validated = test_client.post(
        f"/api/workspaces/{workspace_b['id']}/helper-actions/change-sets/{proposal['id']}/validate",
        headers=headers,
    ).json()
    assert validated["status"] == "validation_failed"
    codes = {
        issue["code"] for issue in validated["validation_summary"]["issues"]
    }
    assert codes == {"unknown_target"}


def test_audit_events_are_appended_and_append_only(client):
    test_client, sessions = client
    headers = csrf_headers(test_client)
    workspace, _current, candidate = _workspace(test_client, headers)
    created = _propose(test_client, headers, workspace["id"], _fixture_body(candidate["id"])).json()
    test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/validate",
        headers=headers,
    )
    test_client.post(
        f"/api/workspaces/{workspace['id']}/helper-actions/change-sets/{created['id']}/approve",
        headers=headers,
    )

    with sessions() as db:
        event_types = [
            row
            for row in db.scalars(
                select(HelperAuditEvent.event_type)
                .where(HelperAuditEvent.change_set_id == UUID(created["id"]))
                .order_by(HelperAuditEvent.created_at, HelperAuditEvent.id)
            )
        ]
        assert event_types == ["change_set_created", "validation_passed", "approved"]
        assert db.scalar(select(func.count(HelperChangeSet.id))) == 1

        with pytest.raises(ValueError):
            event = db.scalars(select(HelperAuditEvent)).first()
            event.summary = {"tampered": True}
            db.commit()
        db.rollback()
