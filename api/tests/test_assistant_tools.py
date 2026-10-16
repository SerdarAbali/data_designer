"""Read-only tool surface and scoping tests (Slice C)."""

from __future__ import annotations

from uuid import UUID

from app.assistant import tools
from app.auth.dependencies import AuthenticatedUser
from app.models import AssistantConversation
from tests.conftest import ALL_DISCIPLINES


def _create_conversation(env, *, state_id=None) -> str:
    response = env.client.post(
        f"/api/workspaces/{env.workspace_id}/assistant/conversations",
        json={"state_id": str(state_id) if state_id else None},
        headers=env.csrf(),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _user(env) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=env.user_id, tenant_id=env.tenant_id, email="assistant@example.test", tenant_name=""
    )


def test_manifest_file_matches_backend_tools() -> None:
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (repo_root / "assistant-runtime" / "assistant-tools.json").read_text(encoding="utf-8")
    )
    declared = {tool["name"] for tool in manifest["tools"]}
    assert declared == set(tools.manifest_tool_names())
    assert all(tool["codemode"] is False for tool in manifest["tools"])


def test_plugin_declares_exactly_the_backend_tools() -> None:
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    plugin = (
        repo_root
        / "assistant-runtime"
        / ".opencode"
        / "plugins"
        / "architecture-assistant"
        / "index.ts"
    ).read_text(encoding="utf-8")
    declared = set(re.findall(r'name: "(architecture_[a-z_]+)"', plugin))
    assert declared == set(tools.manifest_tool_names())
    assert "codemode: false" in plugin


def test_manifest_is_read_only_namespaced_and_strict() -> None:
    manifest = tools.tool_manifest(ALL_DISCIPLINES)
    assert manifest
    for entry in manifest:
        assert entry["name"].startswith("architecture_")
        assert entry["input_schema"]["additionalProperties"] is False


def test_no_proposal_apply_or_undo_tools_exist() -> None:
    names = set(tools.manifest_tool_names())
    for forbidden in tools.FORBIDDEN_TOOL_NAMES:
        assert forbidden not in names
    assert not any("propose" in name for name in names)
    assert not any("apply" in name or "undo" in name or "approve" in name for name in names)


def test_dynamic_discipline_scoping() -> None:
    without_integration = tools.allowed_tool_names(["enterprise", "information", "solution"])
    with_integration = tools.allowed_tool_names(ALL_DISCIPLINES)
    assert "architecture_inspect_contract" not in without_integration
    assert "architecture_inspect_contract" in with_integration
    assert "architecture_get_workspace_context" in without_integration


def test_dispatch_rejects_unknown_tool(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        outcome = tools.dispatch_read_tool(
            db, _user(assistant_env), conversation, "apply_change_set", {}
        )
    assert outcome["status"] == "denied"
    assert outcome["error_code"] == "unknown_tool"


def test_dispatch_rejects_unknown_arguments(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        outcome = tools.dispatch_read_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_get_object_details",
            {
                "object_id": str(assistant_env.object_id),
                "workspace_id": str(assistant_env.workspace_id),
            },
        )
    assert outcome["status"] == "denied"
    assert outcome["error_code"] == "invalid_arguments"


def test_dispatch_rejects_oversized_arguments(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        outcome = tools.dispatch_read_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_search_canonical_objects",
            {"query": "x" * 5000},
        )
    assert outcome["status"] == "denied"
    assert outcome["error_code"] == "oversized_arguments"


def test_dispatch_uses_authoritative_scope_not_model_arguments(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env, state_id=assistant_env.candidate_state_id)
    with assistant_env.sessions() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        outcome = tools.dispatch_read_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_get_object_details",
            {"object_id": str(assistant_env.object_id)},
        )
    assert outcome["status"] == "ok"
    assert outcome["result"]["workspace_id"] == str(assistant_env.workspace_id)


def test_dispatch_denies_state_required_tool_without_active_state(assistant_env) -> None:
    # A conversation with no resolvable state (state_id not provided and no current state
    # is impossible here, so simulate by clearing the active state directly).
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        conversation.active_state_id = None
        db.flush()
        outcome = tools.dispatch_read_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_get_object_usages",
            {"object_id": str(assistant_env.object_id)},
        )
    assert outcome["status"] == "denied"
    assert outcome["error_code"] == "no_active_state"


def test_dispatch_result_is_bounded(assistant_env) -> None:
    conversation_id = _create_conversation(assistant_env)
    with assistant_env.sessions() as db:
        conversation = db.get(AssistantConversation, UUID(conversation_id))
        outcome = tools.dispatch_read_tool(
            db,
            _user(assistant_env),
            conversation,
            "architecture_get_workspace_context",
            {},
        )
    assert outcome["status"] == "ok"
    import json

    assert len(json.dumps(outcome["result"])) <= tools.MAX_TOOL_RESULT_BYTES
