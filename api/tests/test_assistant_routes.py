"""Assistant conversation, streaming, cancellation, and internal-dispatch tests."""

from __future__ import annotations

from uuid import UUID, uuid4

from app import main
from app.assistant import routes
from app.assistant.probe import RuntimeState
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    AssistantConversation,
    AssistantMessage,
    AssistantToolCall,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    HelperAuditEvent,
    HelperChangeOperation,
    HelperChangeSet,
)


def _create_conversation(env, *, state_id=None) -> str:
    response = env.client.post(
        f"/api/workspaces/{env.workspace_id}/assistant/conversations",
        json={"state_id": str(state_id) if state_id else str(env.candidate_state_id)},
        headers=env.csrf(),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _send_message(env, conversation_id: str, text: str = "Explain this candidate") -> str:
    response = env.client.post(
        f"/api/workspaces/{env.workspace_id}/assistant/conversations/{conversation_id}/messages",
        json={"content": text},
        headers=env.csrf(),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_owner_can_toggle_workspace_opt_in(assistant_env) -> None:
    response = assistant_env.client.put(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/settings",
        json={"assistant_enabled": False},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 200
    assert response.json()["assistant_enabled"] is False


def test_non_owner_cannot_toggle_workspace_opt_in(assistant_env) -> None:
    other_id = uuid4()
    main.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=other_id,
        tenant_id=assistant_env.tenant_id,
        email="other@example.test",
        tenant_name="Other",
    )
    try:
        response = assistant_env.client.put(
            f"/api/workspaces/{assistant_env.workspace_id}/assistant/settings",
            json={"assistant_enabled": False},
            headers=assistant_env.csrf(),
        )
    finally:
        main.app.dependency_overrides[get_current_user] = None
        del main.app.dependency_overrides[get_current_user]
    assert response.status_code == 403


def test_readiness_gating_blocks_creation(assistant_env) -> None:
    assistant_env.status._state = RuntimeState.UNAVAILABLE
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 503
    assert "runtime_unreachable" in response.text


def test_disabled_workspace_blocks_creation(assistant_env) -> None:
    with assistant_env.sessions.begin() as db:
        from app.models import Workspace

        workspace = db.get(Workspace, assistant_env.workspace_id)
        workspace.assistant_enabled = False
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 403


def test_conversation_isolation_by_user(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    main.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(),
        tenant_id=assistant_env.tenant_id,
        email="intruder@example.test",
        tenant_name="Intruder",
    )
    try:
        response = assistant_env.client.get(
            f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/{conversation_id}"
        )
    finally:
        del main.app.dependency_overrides[get_current_user]
    assert response.status_code == 404


def test_conversation_isolation_by_workspace(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    response = assistant_env.client.get(
        f"/api/workspaces/{uuid4()}/assistant/conversations/{conversation_id}"
    )
    assert response.status_code == 404


def test_message_turn_persists_transcript_and_tool_activity(assistant_env) -> None:
    assistant_env.runtime._tools = [
        {
            "name": "architecture_get_workspace_context",
            "call_id": "call_1",
            "status": "completed",
            "input": {},
            "output": "{}",
        }
    ]
    conversation_id = _create_conversation(assistant_env)
    _send_message(assistant_env, conversation_id)

    detail = assistant_env.client.get(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/{conversation_id}"
    ).json()
    roles = [message["role"] for message in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "Here is what I found."
    assert len(detail["tool_calls"]) == 1
    assert detail["tool_calls"][0]["tool_name"] == "architecture_get_workspace_context"


def test_sse_stream_delivers_durable_events(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    _send_message(assistant_env, conversation_id)

    chunks: list[str] = []
    for chunk in routes.event_stream(conversation_id, 0, max_idle_seconds=1.0):
        chunks.append(chunk)
        if len(chunks) >= 6:
            break
    assert chunks
    assert all(chunk.startswith("id:") or chunk.startswith(":") for chunk in chunks)
    assert any(
        "assistant.delta" in chunk or "assistant.message.completed" in chunk for chunk in chunks
    )


def test_cancel_interrupts_and_disposes_nothing(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions.begin() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        conversation.opencode_session_id = "ses_fake_1"
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/{conversation_id}/cancel",
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 200
    assert assistant_env.runtime.interrupted == ["ses_fake_1"]


def test_delete_removes_transcript_and_disposes_session(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    _send_message(assistant_env, conversation_id)
    with assistant_env.sessions.begin() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        session_id = conversation.opencode_session_id
    assert session_id

    response = assistant_env.client.delete(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/{conversation_id}",
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 204
    assert session_id in assistant_env.runtime.deleted
    with assistant_env.sessions() as db:
        assert db.get(AssistantConversation, UUID(conversation_id)) is None
        assert db.query(AssistantMessage).count() == 0
        assert db.query(AssistantToolCall).count() == 0


def test_retry_reschedules_last_user_message(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    message_id = _send_message(assistant_env, conversation_id)
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/"
        f"{conversation_id}/messages/{message_id}/retry",
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 202


def test_internal_dispatch_requires_service_token(assistant_env) -> None:
    payload = {
        "opencode_session_id": "ses_unknown",
        "call_id": "call_1",
        "tool": "architecture_get_workspace_context",
        "arguments": {},
    }
    missing = assistant_env.client.post("/internal/assistant/call", json=payload)
    assert missing.status_code == 403
    wrong = assistant_env.client.post(
        "/internal/assistant/call",
        json=payload,
        headers={"X-Assistant-Service-Token": "wrong"},
    )
    assert wrong.status_code == 403


def test_internal_dispatch_denies_unknown_session(assistant_env) -> None:
    response = assistant_env.client.post(
        "/internal/assistant/call",
        json={
            "opencode_session_id": "ses_unknown",
            "call_id": "call_1",
            "tool": "architecture_get_workspace_context",
            "arguments": {},
        },
        headers={"X-Assistant-Service-Token": assistant_env.extra["service_token"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    assert response.json()["error_code"] == "unknown_session"


def test_internal_scope_and_call_dispatch_read_tool(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions.begin() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        conversation.opencode_session_id = "ses_scope_1"
    headers = {"X-Assistant-Service-Token": assistant_env.extra["service_token"]}

    scope = assistant_env.client.get(
        "/internal/assistant/scope?session=ses_scope_1", headers=headers
    )
    assert scope.status_code == 200
    assert scope.json()["status"] == "ok"
    assert "architecture_get_workspace_context" in scope.json()["tools"]

    denied_scope = assistant_env.client.get(
        "/internal/assistant/scope?session=ses_missing", headers=headers
    )
    assert denied_scope.json() == {"status": "denied", "tools": []}

    call = assistant_env.client.post(
        "/internal/assistant/call",
        json={
            "opencode_session_id": "ses_scope_1",
            "call_id": "call_1",
            "tool": "architecture_get_workspace_context",
            "arguments": {},
        },
        headers=headers,
    )
    assert call.status_code == 200
    assert call.json()["status"] == "ok"


def test_internal_scope_checks_do_not_exhaust_the_tool_budget(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions.begin() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        conversation.opencode_session_id = "ses_budget_1"
    headers = {"X-Assistant-Service-Token": assistant_env.extra["service_token"]}

    for index in range(25):
        # Interleave the per-request scope hook with the actual tool call, the
        # shape of a normal multi-step turn. The old shared 20/min budget raised
        # here; the separated budgets must not.
        scope = assistant_env.client.get(
            "/internal/assistant/scope?session=ses_budget_1", headers=headers
        )
        assert scope.status_code == 200
        assert scope.json()["status"] == "ok"

        call = assistant_env.client.post(
            "/internal/assistant/call",
            json={
                "opencode_session_id": "ses_budget_1",
                "call_id": f"call_budget_{index}",
                "tool": "architecture_get_workspace_context",
                "arguments": {},
            },
            headers=headers,
        )
        assert call.status_code == 200
        assert call.json()["status"] == "ok"


def test_responses_never_leak_credentials_or_internal_url(assistant_env) -> None:
    assistant_env.runtime._tools = []
    conversation_id = _create_conversation(assistant_env)
    _send_message(assistant_env, conversation_id)
    for response in (
        assistant_env.client.get(
            f"/api/workspaces/{assistant_env.workspace_id}/assistant/status"
        ),
        assistant_env.client.get(
            f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/{conversation_id}"
        ),
        assistant_env.client.get(
            f"/api/workspaces/{assistant_env.workspace_id}/assistant/tools/manifest"
        ),
    ):
        text = response.text.lower()
        assert "test-service-token" not in text
        assert "opencode.test" not in text
        assert "password" not in text


def test_zero_architecture_domain_changes(assistant_env) -> None:
    def counts(db):
        return (
            db.query(ArchitectureObject).count(),
            db.query(ArchitectureState).count(),
            db.query(ArchitectureRelationship).count(),
            db.query(CatalogSystem).count(),
            db.query(CatalogObject).count(),
            db.query(CatalogField).count(),
            db.query(HelperChangeSet).count(),
            db.query(HelperChangeOperation).count(),
            db.query(HelperAuditEvent).count(),
        )

    with assistant_env.sessions() as db:
        before = counts(db)

    conversation_id = _create_conversation(assistant_env)
    _send_message(assistant_env, conversation_id, "Explain and trace Customer to Billing")

    with assistant_env.sessions() as db:
        after = counts(db)
    assert before == after
