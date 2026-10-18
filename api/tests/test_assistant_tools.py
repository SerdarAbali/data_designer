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
    assert declared == set(tools.all_tool_names())
    assert all(tool["codemode"] is False for tool in manifest["tools"])
    assert all("schema" in tool for tool in manifest["tools"])


def test_plugin_loads_the_generated_manifest_and_is_fail_closed() -> None:
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
    assert "assistant-tools.json" in plugin
    assert "codemode: false" in plugin
    assert "return []" in plugin  # fail closed when the manifest is unreadable


def test_manifest_is_read_only_namespaced_and_strict() -> None:
    manifest = tools.tool_manifest(ALL_DISCIPLINES, "candidate")
    assert manifest
    for entry in manifest:
        assert entry["name"].startswith("architecture_")
        assert entry["input_schema"]["additionalProperties"] is False


def test_no_approve_apply_or_undo_tools_exist() -> None:
    names = set(tools.all_tool_names())
    for forbidden in ("approve_change_set", "apply_change_set", "undo_change_set"):
        assert forbidden not in names
        assert f"architecture_{forbidden}" not in names
    assert not any("approve" in name or "apply" in name or "undo" in name for name in names)
    # Proposal and status tools are the point of this slice.
    assert any("propose" in name for name in names)
    assert "architecture_validate_change_set" in names


def test_dynamic_discipline_scoping() -> None:
    without_integration = tools.allowed_tool_names(["enterprise", "information", "solution"])
    with_integration = tools.allowed_tool_names(ALL_DISCIPLINES)
    assert "architecture_inspect_contract" not in without_integration
    assert "architecture_inspect_contract" in with_integration
    assert "architecture_get_workspace_context" in without_integration


SHARED_READ_TOOLS = {
    "architecture_get_workspace_context",
    "architecture_get_enabled_disciplines",
    "architecture_get_architecture_state",
    "architecture_search_canonical_objects",
    "architecture_get_object_details",
    "architecture_get_object_relationships",
    "architecture_get_object_usages",
    "architecture_trace_architecture_path",
    "architecture_compare_current_candidate",
    "architecture_list_catalog_systems",
    "architecture_inspect_catalog_schema",
}


def test_tool_scope_for_each_discipline_combination() -> None:
    integration_only = set(tools.allowed_tool_names(["integration"], "candidate"))
    solution_only = set(tools.allowed_tool_names(["solution"], "candidate"))
    solution_integration = set(tools.allowed_tool_names(["solution", "integration"], "candidate"))
    enterprise_only = set(tools.allowed_tool_names(["enterprise"], "candidate"))
    information_only = set(tools.allowed_tool_names(["information"], "candidate"))
    full = set(tools.allowed_tool_names(ALL_DISCIPLINES, "candidate"))

    # Shared read surface is always present.
    for scope in (
        integration_only,
        solution_only,
        solution_integration,
        enterprise_only,
        information_only,
        full,
    ):
        assert SHARED_READ_TOOLS <= scope

    # Integration only: contract, mapping and scenario tools, no solution tools.
    for name in (
        "architecture_inspect_contract",
        "architecture_inspect_mapping_coverage",
        "architecture_inspect_scenarios_and_conformance",
        "architecture_propose_contract",
        "architecture_propose_field_mappings",
        "architecture_propose_transformations",
        "architecture_propose_scenarios",
        "architecture_propose_conformance_tests",
    ):
        assert name in integration_only
    assert "architecture_propose_solution_structure" not in integration_only
    assert "architecture_propose_information_entity" not in integration_only

    # Solution only: solution tools plus shared Catalog, no contract tools.
    assert "architecture_propose_solution_structure" in solution_only
    assert "architecture_propose_solution_component" in solution_only
    assert "architecture_list_catalog_systems" in solution_only
    assert "architecture_inspect_catalog_schema" in solution_only
    assert "architecture_inspect_contract" not in solution_only
    assert "architecture_propose_contract" not in solution_only

    # Solution + Integration: union of both scopes plus the composite helper.
    assert "architecture_propose_solution_structure" in solution_integration
    assert "architecture_propose_contract" in solution_integration
    assert (solution_only | integration_only) <= solution_integration
    assert "architecture_propose_end_to_end_architecture" in solution_integration

    # Enterprise and Information follow the same rule.
    assert "architecture_propose_strategy_chain" in enterprise_only
    assert "architecture_propose_solution_structure" not in enterprise_only
    assert "architecture_propose_information_entity" in information_only
    assert "architecture_propose_contract" not in information_only

    # Full Architecture exposes the complete candidate toolset.
    assert full == set(tools.all_tool_names())


def test_tool_manifest_matches_scope_for_every_combination() -> None:
    for disciplines in (
        ["integration"],
        ["solution"],
        ["solution", "integration"],
        ["enterprise"],
        ["information"],
        ALL_DISCIPLINES,
    ):
        manifest = tools.tool_manifest(disciplines, "candidate")
        assert {entry["name"] for entry in manifest} == set(
            tools.allowed_tool_names(disciplines, "candidate")
        )


def test_current_state_is_read_only_for_every_combination() -> None:
    for disciplines in (
        ["integration"],
        ["solution"],
        ["solution", "integration"],
        ["enterprise"],
        ["information"],
        ALL_DISCIPLINES,
    ):
        names = set(tools.allowed_tool_names(disciplines, "current"))
        assert not any("propose" in name for name in names)
        assert SHARED_READ_TOOLS <= names


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
            {"query": "x" * 20000},
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
