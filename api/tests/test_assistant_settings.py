"""Owner-only settings, privacy enforcement, limits, and internal hardening tests."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from app import main
from app.assistant import limits
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.models import AssistantConversation, Workspace


def _settings_url(env) -> str:
    return f"/api/workspaces/{env.workspace_id}/assistant/settings"


def _model_url(env) -> str:
    return f"/api/workspaces/{env.workspace_id}/assistant/settings/model"


def _as_non_owner(env) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(),
        tenant_id=env.tenant_id,
        email="member@example.test",
        tenant_name="Member",
    )


def _restore(env) -> None:
    main.app.dependency_overrides.pop(get_current_user, None)


def test_settings_owner_vs_non_owner(assistant_env) -> None:
    owner = assistant_env.client.get(_settings_url(assistant_env)).json()
    assert owner["is_owner"] is True
    assert owner["workspace_enabled"] is True
    assert owner["retention_days"] == 30
    assert owner["fallback_enabled"] is False
    assert owner["credential_status"] == "missing"

    _as_non_owner(assistant_env)
    try:
        member = assistant_env.client.get(_settings_url(assistant_env)).json()
    finally:
        _restore(assistant_env)
    assert member["is_owner"] is False
    # Non-owners see availability only, never provider configuration.
    assert "provider" not in member
    assert "max_input_tokens" not in member
    assert member["credential_status"] == "missing"


def test_only_owner_can_update_model_settings(assistant_env) -> None:
    _as_non_owner(assistant_env)
    try:
        response = assistant_env.client.put(
            _model_url(assistant_env),
            json={"provider": "openai"},
            headers=assistant_env.csrf(),
        )
    finally:
        _restore(assistant_env)
    assert response.status_code == 403


def test_owner_can_update_and_settings_never_expose_credentials(assistant_env) -> None:
    response = assistant_env.client.put(
        _model_url(assistant_env),
        json={
            "provider": "openai",
            "model_id": "gpt-x",
            "reasoning_effort": "high",
            "max_input_tokens": 20000,
            "max_output_tokens": 2000,
            "timeout_seconds": 120,
            "step_limit": 8,
            "retention_days": 45,
            "privacy_classification": "internal",
            "trains_on_data": False,
            "approved_for_sensitive": True,
        },
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "openai"
    assert body["retention_days"] == 45
    assert body["step_limit"] == 8
    text = json.dumps(body).lower()
    for forbidden in ("api_key", "apikey", "password", "secret", "bearer"):
        assert forbidden not in text


def test_training_provider_blocks_sensitive_workspace(assistant_env) -> None:
    assistant_env.client.put(
        _model_url(assistant_env),
        json={
            "provider": "openai",
            "model_id": "gpt-x",
            "privacy_classification": "confidential",
            "trains_on_data": True,
            "approved_for_sensitive": True,
        },
        headers=assistant_env.csrf(),
    )
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 403
    assert "provider_trains_on_data" in response.text


def test_unapproved_provider_blocks_sensitive_workspace(assistant_env) -> None:
    assistant_env.client.put(
        _model_url(assistant_env),
        json={
            "provider": "openai",
            "model_id": "gpt-x",
            "privacy_classification": "restricted",
            "trains_on_data": False,
            "approved_for_sensitive": False,
        },
        headers=assistant_env.csrf(),
    )
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 403
    assert "provider_not_approved_for_sensitive" in response.text


def test_fallback_not_allowed_for_sensitive(assistant_env) -> None:
    assistant_env.client.put(
        _model_url(assistant_env),
        json={
            "privacy_classification": "confidential",
            "approved_for_sensitive": True,
            "fallback_enabled": True,
            "fallback_provider": "other",
            "fallback_model_id": "m",
        },
        headers=assistant_env.csrf(),
    )
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 403
    assert "fallback_not_allowed_for_sensitive" in response.text


def test_runtime_session_uses_configured_model(assistant_env) -> None:
    assistant_env.client.put(
        _model_url(assistant_env),
        json={"provider": "openai", "model_id": "gpt-x"},
        headers=assistant_env.csrf(),
    )
    conversation = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={"state_id": str(assistant_env.candidate_state_id)},
        headers=assistant_env.csrf(),
    ).json()
    assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/"
        f"{conversation['id']}/messages",
        json={"content": "hello"},
        headers=assistant_env.csrf(),
    )
    session_id = next(iter(assistant_env.runtime.sessions))
    assert assistant_env.runtime.sessions[session_id]["body"]["model"] == {
        "providerID": "openai",
        "id": "gpt-x",
    }


def test_provider_change_disposes_sessions(assistant_env) -> None:
    conversation = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={"state_id": str(assistant_env.candidate_state_id)},
        headers=assistant_env.csrf(),
    ).json()
    assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/"
        f"{conversation['id']}/messages",
        json={"content": "hello"},
        headers=assistant_env.csrf(),
    )
    with assistant_env.sessions() as db:
        row = db.get(AssistantConversation, UUID(conversation["id"]))
        assert row.opencode_session_id

    assistant_env.client.put(
        _model_url(assistant_env),
        json={"provider": "openai", "model_id": "gpt-y"},
        headers=assistant_env.csrf(),
    )
    with assistant_env.sessions() as db:
        row = db.get(AssistantConversation, UUID(conversation["id"]))
        assert row.opencode_session_id is None
        # Conversation history is preserved.
        assert row.message_count >= 1


def test_conversation_concurrency_limit(assistant_env) -> None:
    conversation = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={"state_id": str(assistant_env.candidate_state_id)},
        headers=assistant_env.csrf(),
    ).json()
    limits.limiter.acquire(
        conversation_id=conversation["id"],
        user_id=str(assistant_env.user_id),
        workspace_id=str(assistant_env.workspace_id),
    )
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations/"
        f"{conversation['id']}/messages",
        json={"content": "hello"},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 429
    assert "conversation_busy" in response.text


def test_internal_dispatch_hardening(assistant_env) -> None:
    token = assistant_env.extra["service_token"]
    headers = {"X-Assistant-Service-Token": token}

    ok = assistant_env.client.get("/internal/assistant/manifest", headers=headers)
    assert ok.status_code == 200
    assert ok.headers.get("x-assistant-correlation-id", "").startswith("cor_")

    wrong_type = assistant_env.client.post(
        "/internal/assistant/call",
        content=json.dumps({"opencode_session_id": "s", "call_id": "c", "tool": "t"}),
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert wrong_type.status_code == 415

    oversized = assistant_env.client.post(
        "/internal/assistant/call",
        content=b"{}",
        headers={**headers, "Content-Type": "application/json", "Content-Length": "99999999"},
    )
    assert oversized.status_code == 413

    # Rotation: a previous token is accepted, an unrelated token is not.
    from app.assistant.settings import AssistantSettings

    assistant_env.extra["rotate"] = True
    main.app.dependency_overrides.pop(get_current_user, None)
    import app.assistant.routes as routes_module

    original = routes_module.get_assistant_settings

    def rotated():
        return AssistantSettings(
            tool_service_token="new-token", tool_service_token_previous="old-token"
        )

    routes_module.get_assistant_settings = rotated
    try:
        previous = assistant_env.client.get(
            "/internal/assistant/manifest", headers={"X-Assistant-Service-Token": "old-token"}
        )
        assert previous.status_code == 200
        unrelated = assistant_env.client.get(
            "/internal/assistant/manifest", headers={"X-Assistant-Service-Token": "nope"}
        )
        assert unrelated.status_code == 403
    finally:
        routes_module.get_assistant_settings = original


def test_disabled_workspace_makes_no_provider_request(assistant_env) -> None:
    with assistant_env.sessions.begin() as db:
        workspace = db.get(Workspace, assistant_env.workspace_id)
        workspace.assistant_enabled = False
    assistant_env.runtime.created = 0
    response = assistant_env.client.post(
        f"/api/workspaces/{assistant_env.workspace_id}/assistant/conversations",
        json={},
        headers=assistant_env.csrf(),
    )
    assert response.status_code == 403
    assert assistant_env.runtime.created == 0
