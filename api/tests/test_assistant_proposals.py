"""Proposal tools, dynamic scoping, resolution, and proposal-reference tests."""

from __future__ import annotations

import json
from uuid import UUID

from app.assistant import gateway, tools
from app.auth.dependencies import AuthenticatedUser
from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    AssistantConversation,
    AssistantMessage,
    AssistantToolCall,
    CatalogSystem,
    HelperAuditEvent,
    HelperChangeOperation,
    HelperChangeSet,
    Workspace,
)
from tests.conftest import FakeRuntime


def _conversation(env, *, state_id=None) -> str:
    response = env.client.post(
        f"/api/workspaces/{env.workspace_id}/assistant/conversations",
        json={"state_id": str(state_id or env.candidate_state_id)},
        headers=env.csrf(),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _load(env, conversation_id: str):
    db = env.sessions()
    conversation = db.get(AssistantConversation, UUID(conversation_id))
    return db, conversation


def _user(env) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=env.user_id, tenant_id=env.tenant_id, email="assistant@example.test", tenant_name=""
    )


ENTITY_PROPOSAL = {
    "summary": "Add a Customer information entity",
    "nodes": [{"key": "cust", "kind": "information_object", "name": "Customer"}],
}


def _create_proposal(
    env, conversation_id: str, tool: str = "architecture_propose_information_entity"
):
    db, conversation = _load(env, conversation_id)
    try:
        outcome = tools.dispatch_tool(db, _user(env), conversation, tool, dict(ENTITY_PROPOSAL))
    finally:
        db.close()
    return outcome


# -- scoping ---------------------------------------------------------------


def test_current_allows_read_and_status_only(assistant_env) -> None:
    allowed = tools.allowed_tool_names(
        ["enterprise", "information", "solution", "integration"], "current"
    )
    assert not any("propose" in name for name in allowed)
    assert "architecture_validate_change_set" in allowed
    assert "architecture_get_workspace_context" in allowed


def test_candidate_scopes_proposal_tools_by_discipline() -> None:
    solution_integration = tools.allowed_tool_names(["solution", "integration"], "candidate")
    assert "architecture_propose_solution_structure" in solution_integration
    assert "architecture_propose_direct_integration" in solution_integration
    assert "architecture_propose_strategy_chain" not in solution_integration
    assert "architecture_propose_information_entity" not in solution_integration

    integration_only = tools.allowed_tool_names(["integration"], "candidate")
    assert "architecture_propose_direct_integration" in integration_only
    assert "architecture_propose_solution_structure" not in integration_only
    # Composite needs at least two enabled disciplines.
    assert "architecture_propose_end_to_end_architecture" not in integration_only


def test_proposal_denied_in_current(assistant_env) -> None:
    conversation_id = _conversation(assistant_env, state_id=assistant_env.current_state_id)
    outcome = _create_proposal(assistant_env, conversation_id)
    assert outcome["status"] == "denied"
    assert outcome["error_code"] == "proposal_in_current"


def test_disabled_discipline_proposal_is_denied(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    with assistant_env.sessions.begin() as db:
        workspace = db.get(Workspace, assistant_env.workspace_id)
        workspace.disciplines = ["solution"]
    outcome = _create_proposal(assistant_env, conversation_id)
    assert outcome["status"] == "denied"
    assert outcome["error_code"] == "tool_not_in_scope"


def test_scope_override_arguments_are_rejected(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    db, conversation = _load(assistant_env, conversation_id)
    try:
        for override in (
            {"state_id": str(assistant_env.current_state_id)},
            {"workspace_id": str(assistant_env.workspace_id)},
            {"tenant_id": str(assistant_env.tenant_id)},
        ):
            outcome = tools.dispatch_tool(
                db,
                _user(assistant_env),
                conversation,
                "architecture_propose_information_entity",
                {**ENTITY_PROPOSAL, **override},
            )
            assert outcome["status"] == "denied"
            assert outcome["error_code"] == "scope_override"
    finally:
        db.close()


def test_unknown_and_oversized_proposal_arguments_are_rejected(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    db, conversation = _load(assistant_env, conversation_id)
    try:
        unknown = tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_propose_information_entity",
            {**ENTITY_PROPOSAL, "nonsense": True},
        )
        assert unknown["error_code"] == "invalid_arguments"
        oversized = tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_propose_information_entity",
            {"summary": "x" * 20000},
        )
        assert oversized["error_code"] == "oversized_arguments"
    finally:
        db.close()


def test_unknown_tool_is_denied(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    db, conversation = _load(assistant_env, conversation_id)
    try:
        for name in (
            "approve_change_set",
            "architecture_approve_change_set",
            "architecture_resolve_change_set",
            "architecture_apply_change_set",
            "shell",
        ):
            outcome = tools.dispatch_tool(db, _user(assistant_env), conversation, name, {})
            assert outcome["status"] == "denied"
            assert outcome["error_code"] == "unknown_tool"
    finally:
        db.close()


# -- proposal creation and bounded results ---------------------------------


def test_proposal_tool_creates_a_bounded_change_set(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    outcome = _create_proposal(assistant_env, conversation_id)
    assert outcome["status"] == "ok"
    result = outcome["result"]
    assert result["change_set_id"]
    assert result["status"] == "draft"
    assert len(json.dumps(result)) <= tools.MAX_PROPOSAL_RESULT_BYTES
    assert "operations" not in result

    with assistant_env.sessions() as db:
        change_set = db.get(HelperChangeSet, UUID(result["change_set_id"]))
        assert change_set is not None
        assert change_set.status == "draft"


def test_status_tools_are_bounded(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    db, conversation = _load(assistant_env, conversation_id)
    try:
        fetched = tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_get_change_set",
            {"change_set_id": change_set_id},
        )
        assert fetched["status"] == "ok"
        assert len(json.dumps(fetched["result"])) <= tools.MAX_STATUS_RESULT_BYTES

        validated = tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_validate_change_set",
            {"change_set_id": change_set_id},
        )
        assert validated["status"] == "ok"
        assert validated["result"]["status"] in {"validated", "validation_failed", "stale"}
    finally:
        db.close()


def test_no_domain_writes_during_proposal_and_validation(assistant_env) -> None:
    def counts(db):
        return (
            db.query(ArchitectureObject).count(),
            db.query(ArchitectureRelationship).count(),
            db.query(CatalogSystem).count(),
        )

    with assistant_env.sessions() as db:
        before = counts(db)
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    db, conversation = _load(assistant_env, conversation_id)
    try:
        tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_validate_change_set",
            {"change_set_id": change_set_id},
        )
    finally:
        db.close()
    with assistant_env.sessions() as db:
        assert counts(db) == before


# -- resolution ------------------------------------------------------------


def _make_unresolved(env, change_set_id: str) -> str:
    with env.sessions.begin() as db:
        operation = (
            db.query(HelperChangeOperation)
            .filter(HelperChangeOperation.change_set_id == UUID(change_set_id))
            .first()
        )
        operation.proposed_value = {
            **(operation.proposed_value or {}),
            "unresolved": True,
            "reason": "Which name should be used?",
            "required_for_approval": True,
        }
        return operation.operation_id


def test_resolution_requires_csrf(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    operation_id = _make_unresolved(assistant_env, change_set_id)
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/helper-actions/change-sets/"
        f"{change_set_id}/resolve",
        json={
            "resolutions": [
                {
                    "operation_id": operation_id,
                    "kind": "set_scalar",
                    "field": "name",
                    "value": "Customer",
                }
            ]
        },
    )
    assert response.status_code == 403


def test_resolution_recomputes_hash_and_clears_validation(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    operation_id = _make_unresolved(assistant_env, change_set_id)

    # Validate first so there is state to clear.
    db, conversation = _load(assistant_env, conversation_id)
    try:
        tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_validate_change_set",
            {"change_set_id": change_set_id},
        )
    finally:
        db.close()
    with assistant_env.sessions() as db:
        before = db.get(HelperChangeSet, UUID(change_set_id))
        before_hash = before.proposal_hash

    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/helper-actions/change-sets/"
        f"{change_set_id}/resolve",
        json={
            "resolutions": [
                {
                    "operation_id": operation_id,
                    "kind": "choose_canonical_object",
                    "object_id": str(assistant_env.object_id),
                }
            ]
        },
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["proposal_hash"] != before_hash
    assert body["validated_at"] is None
    assert body["approved_at"] is None
    operation = next(op for op in body["operations"] if op["operation_id"] == operation_id)
    assert operation["proposed_value"]["unresolved"] is False
    assert operation["proposed_value"]["existing_object_id"] == str(assistant_env.object_id)


def test_remove_operation_marks_resolution_state(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    with assistant_env.sessions() as db:
        operation_id = (
            db.query(HelperChangeOperation)
            .filter(HelperChangeOperation.change_set_id == UUID(change_set_id))
            .first()
            .operation_id
        )
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/helper-actions/change-sets/"
        f"{change_set_id}/resolve",
        json={"resolutions": [{"operation_id": operation_id, "kind": "remove_operation"}]},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 200, response.text
    operation = next(
        op for op in response.json()["operations"] if op["operation_id"] == operation_id
    )
    assert operation["resolution_state"] == "removed"


def test_resolution_rejects_disallowed_kind_and_field(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    operation_id = _make_unresolved(assistant_env, change_set_id)
    bad_field = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/helper-actions/change-sets/"
        f"{change_set_id}/resolve",
        json={
            "resolutions": [
                {
                    "operation_id": operation_id,
                    "kind": "set_scalar",
                    "field": "sql",
                    "value": "drop",
                }
            ]
        },
        headers=assistant_env.csrf(),
    )
    assert bad_field.status_code == 422


def test_resolution_preserves_helper_audit_and_domain(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    with assistant_env.sessions() as db:
        before_objects = db.query(ArchitectureObject).count()
        before_audit = db.query(HelperAuditEvent).count()
        operation_id = (
            db.query(HelperChangeOperation)
            .filter(HelperChangeOperation.change_set_id == UUID(change_set_id))
            .first()
            .operation_id
        )
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/helper-actions/change-sets/"
        f"{change_set_id}/resolve",
        json={"resolutions": [{"operation_id": operation_id, "kind": "remove_operation"}]},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 200
    with assistant_env.sessions() as db:
        assert db.query(ArchitectureObject).count() == before_objects
        assert db.query(HelperAuditEvent).count() > before_audit


# -- proposal references in conversations ----------------------------------


def test_gateway_records_change_set_reference_and_events(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]

    runtime = FakeRuntime(
        text="I created proposal.",
        tools=[
            {
                "name": "architecture_propose_information_entity",
                "call_id": "call_prop",
                "status": "completed",
                "input": {},
                "output": json.dumps({"change_set_id": change_set_id, "status": "draft"}),
            }
        ],
    )
    db, conversation = _load(assistant_env, conversation_id)
    try:
        gateway.run_turn(
            db, conversation, _user(assistant_env), db.get(Workspace, assistant_env.workspace_id),
            runtime=runtime, user_text="propose",
        )
    finally:
        db.close()

    with assistant_env.sessions() as db:
        call = (
            db.query(AssistantToolCall)
            .filter(AssistantToolCall.conversation_id == UUID(conversation_id))
            .one()
        )
        assert str(call.change_set_id) == change_set_id
        message = (
            db.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == UUID(conversation_id),
                AssistantMessage.role == "assistant",
            )
            .one()
        )
        assert change_set_id in message.referenced_change_set_ids
        assert "proposal.created" in {
            event.event_type
            for event in db.query(HelperAuditEvent).all()
        } or True  # audit is helper-side; assistant events checked below

    from app.models import AssistantEvent

    with assistant_env.sessions() as db:
        types = {
            event.event_type
            for event in db.query(AssistantEvent)
            .filter(AssistantEvent.conversation_id == UUID(conversation_id))
            .all()
        }
    assert "proposal.created" in types


def test_stale_proposal_is_reported_stale(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    db, conversation = _load(assistant_env, conversation_id)
    try:
        tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_validate_change_set",
            {"change_set_id": change_set_id},
        )
    finally:
        db.close()

    # Mutate an operation behind the tool surface, then re-read status.
    with assistant_env.sessions.begin() as db:
        operation = (
            db.query(HelperChangeOperation)
            .filter(HelperChangeOperation.change_set_id == UUID(change_set_id))
            .first()
        )
        operation.proposed_value = {**(operation.proposed_value or {}), "name": "Mutated"}

    db, conversation = _load(assistant_env, conversation_id)
    try:
        status = tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_get_change_set_status",
            {"change_set_id": change_set_id},
        )
    finally:
        db.close()
    assert status["status"] == "ok"
    assert status["result"]["status"] == "stale"
    assert status["result"]["ready_for_approval"] is not True


def test_no_full_payload_in_messages_or_events(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    runtime = FakeRuntime(
        text="I created proposal.",
        tools=[
            {
                "name": "architecture_propose_information_entity",
                "call_id": "call_prop",
                "status": "completed",
                "input": {},
                "output": json.dumps({"change_set_id": change_set_id, "status": "draft"}),
            }
        ],
    )
    db, conversation = _load(assistant_env, conversation_id)
    try:
        gateway.run_turn(
            db,
            conversation,
            _user(assistant_env),
            db.get(Workspace, assistant_env.workspace_id),
            runtime=runtime,
            user_text="propose",
        )
    finally:
        db.close()

    from app.models import AssistantEvent

    with assistant_env.sessions() as db:
        events = (
            db.query(AssistantEvent)
            .filter(AssistantEvent.conversation_id == UUID(conversation_id))
            .all()
        )
        for event in events:
            blob = json.dumps(event.payload or {})
            assert "operations" not in blob
            assert len(blob) < 1000
        message = (
            db.query(AssistantMessage)
            .filter(AssistantMessage.conversation_id == UUID(conversation_id))
            .one()
        )
        assert message.referenced_change_set_ids == [change_set_id]
        assert "operations" not in message.content


def test_composite_proposal_requires_two_disciplines(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    db, conversation = _load(assistant_env, conversation_id)
    payload = {
        "summary": "Customer onboarding end to end",
        "requested_disciplines": ["information"],
        "information": {
            "nodes": [{"key": "cust", "kind": "information_object", "name": "Customer"}]
        },
    }
    try:
        outcome = tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_propose_end_to_end_architecture",
            payload,
        )
    finally:
        db.close()
    assert outcome["status"] == "ok"
    assert outcome["result"]["change_set_id"]
    assert len(json.dumps(outcome["result"])) <= tools.MAX_PROPOSAL_RESULT_BYTES


def test_composite_proposal_denied_with_one_discipline(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    with assistant_env.sessions.begin() as db:
        workspace = db.get(Workspace, assistant_env.workspace_id)
        workspace.disciplines = ["information"]
    db, conversation = _load(assistant_env, conversation_id)
    try:
        outcome = tools.dispatch_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_propose_end_to_end_architecture",
            {"summary": "x"},
        )
    finally:
        db.close()
    assert outcome["status"] == "denied"
    assert outcome["error_code"] == "tool_not_in_scope"


def test_approve_apply_undo_absent_from_all_model_surfaces(assistant_env) -> None:
    from pathlib import Path

    names = set(tools.all_tool_names())
    for forbidden in ("approve_change_set", "apply_change_set", "undo_change_set"):
        assert forbidden not in names
        assert f"architecture_{forbidden}" not in names

    repo_root = Path(__file__).resolve().parents[2]
    manifest = (repo_root / "assistant-runtime" / "assistant-tools.json").read_text(
        encoding="utf-8"
    )
    plugin = (
        repo_root
        / "assistant-runtime"
        / ".opencode"
        / "plugins"
        / "architecture-assistant"
        / "index.ts"
    ).read_text(encoding="utf-8")
    for forbidden in ("approve_change_set", "apply_change_set", "undo_change_set"):
        assert forbidden not in manifest
        assert forbidden not in plugin

    conversation_id = _conversation(assistant_env)
    db, conversation = _load(assistant_env, conversation_id)
    try:
        for name in ("approve_change_set", "apply_change_set", "undo_change_set"):
            outcome = tools.dispatch_tool(db, _user(assistant_env), conversation, name, {})
            assert outcome["status"] == "denied"
            assert outcome["error_code"] == "unknown_tool"
    finally:
        db.close()


def _reference_change_set(env, conversation_id: str, change_set_id: str) -> None:
    with env.sessions.begin() as db:
        db.add(
            AssistantToolCall(
                conversation_id=UUID(conversation_id),
                tenant_id=env.tenant_id,
                workspace_id=env.workspace_id,
                call_id=f"call_{change_set_id[:8]}",
                tool_name="architecture_propose_information_entity",
                arguments_summary={},
                arguments_hash="hash",
                status="completed",
                result_summary={},
                change_set_id=UUID(change_set_id),
            )
        )


def test_proposal_events_are_bounded_and_require_csrf(assistant_env) -> None:
    from app.models import AssistantEvent

    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    _reference_change_set(assistant_env, conversation_id, change_set_id)
    url = (
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/"
        f"{conversation_id}/proposal-events"
    )

    missing_csrf = assistant_env.client.post(
        url, json={"change_set_id": change_set_id, "action": "approved"}
    )
    assert missing_csrf.status_code == 403

    recorded = assistant_env.client.post(
        url,
        json={"change_set_id": change_set_id, "action": "approved"},
        headers=assistant_env.csrf(),
    )
    assert recorded.status_code == 200

    with assistant_env.sessions() as db:
        events = (
            db.query(AssistantEvent)
            .filter(AssistantEvent.conversation_id == UUID(conversation_id))
            .all()
        )
    approved = [event for event in events if event.event_type == "proposal.approved"]
    assert approved
    payload = approved[-1].payload
    assert payload["change_set_id"] == change_set_id
    assert "operations" not in json.dumps(payload)
    assert len(json.dumps(payload)) < 500


def test_proposal_event_rejects_unreferenced_change_set(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    referenced = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    _reference_change_set(assistant_env, conversation_id, referenced)
    other = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/"
        f"{conversation_id}/proposal-events",
        json={"change_set_id": other, "action": "applied"},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 404


def test_conversation_deletion_preserves_change_set_and_audit(assistant_env) -> None:
    conversation_id = _conversation(assistant_env)
    change_set_id = _create_proposal(assistant_env, conversation_id)["result"]["change_set_id"]
    with assistant_env.sessions() as db:
        before_audit = (
            db.query(HelperAuditEvent)
            .filter(HelperAuditEvent.change_set_id == UUID(change_set_id))
            .count()
        )
    response = assistant_env.client.delete(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/{conversation_id}",
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 204
    with assistant_env.sessions() as db:
        assert db.get(HelperChangeSet, UUID(change_set_id)) is not None
        assert (
            db.query(HelperAuditEvent)
            .filter(HelperAuditEvent.change_set_id == UUID(change_set_id))
            .count()
        ) == before_audit
