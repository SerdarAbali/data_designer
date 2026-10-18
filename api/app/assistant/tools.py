"""Tool surface for the assistant: bounded reads, proposals, and status.

This is the authoritative backend dispatch registry. It maps a closed set of
namespaced tool names to the existing bounded read helpers and the existing
deterministic proposal helpers. There is no entry for approval, apply, undo,
SQL, ORM, shell, filesystem, generic HTTP, or arbitrary execution — those
capabilities do not exist on this surface by construction.

Every call is validated against a strict JSON Schema (``extra="forbid"``), size
capped, scoped to the conversation's workspace/disciplines/state, and returns a
bounded projection. Proposal tools never return the full change-set payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.assistant.decisions import derive_unresolved_details
from app.auth.dependencies import AuthenticatedUser
from app.helper_actions import end_to_end, reads, service
from app.helper_actions.context import resolve_context
from app.helper_actions.schemas import ReadRequest
from app.models import AssistantConversation, HelperChangeSet

MAX_TOOL_RESULT_BYTES = 16 * 1024
MAX_PROPOSAL_RESULT_BYTES = 2 * 1024
MAX_STATUS_RESULT_BYTES = 4 * 1024
MAX_TOOL_ARGUMENT_BYTES = 8 * 1024

#: Scope-like keys the model must never supply. Identity is resolved server-side
#: from the OpenCode session id only.
FORBIDDEN_SCOPE_KEYS = frozenset(
    {"state_id", "workspace_id", "tenant_id", "user_id", "permissions", "permission"}
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArgs(_Strict):
    pass


class LimitArgs(_Strict):
    limit: int = Field(default=25, ge=1, le=25)


class SearchArgs(_Strict):
    query: str | None = Field(default=None, max_length=200)
    kind: str | None = Field(default=None, max_length=60)
    limit: int = Field(default=25, ge=1, le=25)


class ObjectArgs(_Strict):
    object_id: UUID
    limit: int = Field(default=25, ge=1, le=25)


class TraceArgs(_Strict):
    object_id: UUID
    direction: Literal["both", "outgoing", "incoming"] = "both"
    depth: int = Field(default=1, ge=1, le=2)
    limit: int = Field(default=25, ge=1, le=25)


class CompareArgs(_Strict):
    baseline_state_id: UUID | None = None
    limit: int = Field(default=25, ge=1, le=25)


class SchemaArgs(_Strict):
    system_id: UUID | None = None
    object_id: UUID | None = None
    limit: int = Field(default=25, ge=1, le=25)


class ContractArgs(_Strict):
    contract_id: UUID


class ContractListArgs(_Strict):
    contract_id: UUID
    limit: int = Field(default=25, ge=1, le=25)


class ChangeSetArgs(_Strict):
    change_set_id: UUID


@dataclass(frozen=True)
class ReadToolSpec:
    name: str
    helper: str
    description: str
    args_model: type[BaseModel]
    discipline: str | None = None
    needs_state: bool = False


@dataclass(frozen=True)
class ProposalToolSpec:
    name: str
    helper: str
    description: str
    args_model: type[BaseModel]
    discipline: str | None
    composite: bool = False


READ_TOOL_SPECS: tuple[ReadToolSpec, ...] = (
    ReadToolSpec(
        name="architecture_get_workspace_context",
        helper="get_workspace_context",
        description="Read the workspace name, description, disciplines, and states. Read-only.",
        args_model=EmptyArgs,
    ),
    ReadToolSpec(
        name="architecture_get_enabled_disciplines",
        helper="get_enabled_disciplines",
        description="List the architecture disciplines enabled for this workspace. Read-only.",
        args_model=EmptyArgs,
    ),
    ReadToolSpec(
        name="architecture_get_architecture_state",
        helper="get_architecture_state",
        description="Read a bounded preview of the active architecture state. Read-only.",
        args_model=LimitArgs,
        needs_state=True,
    ),
    ReadToolSpec(
        name="architecture_search_canonical_objects",
        helper="search_canonical_objects",
        description="Search canonical architecture objects by name and optional kind. Read-only.",
        args_model=SearchArgs,
    ),
    ReadToolSpec(
        name="architecture_get_object_details",
        helper="get_object_details",
        description="Read a canonical object's details and its state membership. Read-only.",
        args_model=ObjectArgs,
    ),
    ReadToolSpec(
        name="architecture_get_object_relationships",
        helper="get_object_relationships",
        description="List stored typed relationships for a canonical object. Read-only.",
        args_model=ObjectArgs,
    ),
    ReadToolSpec(
        name="architecture_get_object_usages",
        helper="get_object_usages",
        description="List how an object is used in the active state, by relationship. Read-only.",
        args_model=ObjectArgs,
        needs_state=True,
    ),
    ReadToolSpec(
        name="architecture_trace_architecture_path",
        helper="trace_architecture_path",
        description="Trace bounded connectivity from an object in the active state. Read-only.",
        args_model=TraceArgs,
        needs_state=True,
    ),
    ReadToolSpec(
        name="architecture_compare_current_candidate",
        helper="compare_current_candidate",
        description="Compare the active candidate state against Current. Read-only.",
        args_model=CompareArgs,
        needs_state=True,
    ),
    ReadToolSpec(
        name="architecture_list_catalog_systems",
        helper="list_catalog_systems",
        description="List Catalog systems available to this workspace. Read-only.",
        args_model=LimitArgs,
    ),
    ReadToolSpec(
        name="architecture_inspect_catalog_schema",
        helper="inspect_catalog_schema",
        description="Inspect bounded Catalog fields for a system or object. Read-only.",
        args_model=SchemaArgs,
    ),
    ReadToolSpec(
        name="architecture_list_integration_contracts",
        helper="list_integration_contracts",
        description="List integration Contracts. Read-only.",
        args_model=LimitArgs,
        discipline="integration",
    ),
    ReadToolSpec(
        name="architecture_inspect_contract",
        helper="inspect_contract",
        description="Inspect one Contract's specification and scenario count. Read-only.",
        args_model=ContractArgs,
        discipline="integration",
    ),
    ReadToolSpec(
        name="architecture_inspect_mapping_coverage",
        helper="inspect_mapping_coverage",
        description="Inspect Contract mapping coverage counts. Read-only.",
        args_model=ContractArgs,
        discipline="integration",
    ),
    ReadToolSpec(
        name="architecture_inspect_scenarios_and_conformance",
        helper="inspect_scenarios_and_conformance",
        description="Inspect scenarios and conformance status for a Contract. Read-only.",
        args_model=ContractListArgs,
        discipline="integration",
    ),
)

# Ordered exactly as the approved plan lists them.
_PROPOSAL_HELPERS: tuple[tuple[str, str], ...] = (
    ("propose_strategy_chain", "enterprise"),
    ("propose_capability_support", "enterprise"),
    ("propose_process_support", "enterprise"),
    ("propose_enterprise_impact_resolution", "enterprise"),
    ("propose_information_entity", "information"),
    ("propose_information_model", "information"),
    ("propose_entity_relationship", "information"),
    ("propose_attribute_realization", "information"),
    ("propose_information_gap_resolution", "information"),
    ("propose_solution_structure", "solution"),
    ("propose_solution_component", "solution"),
    ("propose_interface_connection", "solution"),
    ("propose_repository_usage", "solution"),
    ("propose_deployment_allocation", "solution"),
    ("propose_trust_boundary_membership", "solution"),
    ("propose_solution_interaction", "solution"),
    ("propose_direct_integration", "integration"),
    ("propose_event_driven_integration", "integration"),
    ("propose_runtime_mediated_integration", "integration"),
    ("propose_file_transfer_integration", "integration"),
    ("propose_contract", "integration"),
    ("propose_field_mappings", "integration"),
    ("propose_transformations", "integration"),
    ("propose_resilience_configuration", "integration"),
    ("propose_scenarios", "integration"),
    ("propose_conformance_tests", "integration"),
    ("propose_system_facts", "any"),
    ("propose_contract_facts", "integration"),
    ("propose_contract_mediator", "integration"),
    ("propose_evidence", "any"),
    ("propose_solution_contract_association", "solution"),
    ("propose_solution_relationship", "solution"),
    (end_to_end.COMPOSITE_HELPER, "composite"),
)

PROPOSAL_TOOL_SPECS: tuple[ProposalToolSpec, ...] = tuple(
    ProposalToolSpec(
        name=f"architecture_{helper}",
        helper=helper,
        description=(
            f"Create a deterministic draft change-set proposal using the '{helper}' "
            "helper. Read-only against the architecture: it only writes helper "
            "change-set rows. Never approves, applies, or undoes."
        ),
        args_model=service.PROPOSAL_REQUEST_MODELS[helper],
        discipline=None if discipline in {"composite", "any"} else discipline,
        composite=discipline == "composite",
    )
    for helper, discipline in _PROPOSAL_HELPERS
)

STATUS_TOOL_NAMES: tuple[str, ...] = (
    "architecture_get_change_set",
    "architecture_get_change_set_status",
    "architecture_validate_change_set",
)

STATUS_TOOL_DESCRIPTIONS: dict[str, str] = {
    "architecture_get_change_set": "Read a bounded summary of a helper change set. Read-only.",
    "architecture_get_change_set_status": "Read a change set's status, hash, and issue counts.",
    "architecture_validate_change_set": (
        "Run the helper layer's deterministic validation for a change set. "
        "Never approves or applies it."
    ),
}

#: Names that must never exist on the model surface.
FORBIDDEN_TOOL_NAMES = frozenset(
    {
        "approve_change_set",
        "apply_change_set",
        "undo_change_set",
        "shell",
        "read",
        "write",
        "edit",
        "patch",
        "execute",
        "webfetch",
        "websearch",
        "mcp",
    }
)

READ_BY_NAME: dict[str, ReadToolSpec] = {spec.name: spec for spec in READ_TOOL_SPECS}
PROPOSAL_BY_NAME: dict[str, ProposalToolSpec] = {spec.name: spec for spec in PROPOSAL_TOOL_SPECS}


def read_tool_names() -> list[str]:
    return sorted(spec.name for spec in READ_TOOL_SPECS)


def proposal_tool_names() -> list[str]:
    return [spec.name for spec in PROPOSAL_TOOL_SPECS]


def all_tool_names() -> list[str]:
    return sorted([*read_tool_names(), *proposal_tool_names(), *STATUS_TOOL_NAMES])


def allowed_tool_names(disciplines: list[str], state_type: str = "current") -> list[str]:
    enabled = set(disciplines or [])
    names = [
        spec.name
        for spec in READ_TOOL_SPECS
        if spec.discipline is None or spec.discipline in enabled
    ]
    names.extend(STATUS_TOOL_NAMES)
    if state_type != "current":
        for spec in PROPOSAL_TOOL_SPECS:
            if spec.composite:
                if len(enabled) >= 2:
                    names.append(spec.name)
            elif spec.discipline is None or spec.discipline in enabled:
                names.append(spec.name)
    return sorted(set(names))


def _slim(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop pydantic's per-field ``title`` noise; keep structure and constraints."""
    if isinstance(schema, dict):
        schema.pop("title", None)
        for value in schema.values():
            _slim(value)
    elif isinstance(schema, list):
        for value in schema:
            _slim(value)
    return schema


def model_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for a model with the server-injected ``state_id`` removed."""
    schema = model.model_json_schema()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        properties.pop("state_id", None)
    required = schema.get("required")
    if isinstance(required, list) and "state_id" in required:
        required.remove("state_id")
    schema.setdefault("additionalProperties", False)
    return _slim(schema)


def plugin_manifest() -> list[dict[str, Any]]:
    """Every tool (all disciplines) with its schema, for plugin registration."""
    entries: list[dict[str, Any]] = []
    for spec in READ_TOOL_SPECS:
        entries.append(
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": _slim(spec.args_model.model_json_schema()),
            }
        )
    for spec in PROPOSAL_TOOL_SPECS:
        entries.append(
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": model_schema(spec.args_model),
            }
        )
    for name in STATUS_TOOL_NAMES:
        entries.append(
            {
                "name": name,
                "description": STATUS_TOOL_DESCRIPTIONS[name],
                "input_schema": ChangeSetArgs.model_json_schema(),
            }
        )
    return entries


def tool_manifest(disciplines: list[str], state_type: str = "current") -> list[dict[str, Any]]:
    names = set(allowed_tool_names(disciplines, state_type))
    return [entry for entry in plugin_manifest() if entry["name"] in names]


def _deny(code: str) -> dict[str, Any]:
    return {"status": "denied", "error_code": code, "result": {}}


def _bounded(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    encoded = json.dumps(payload, separators=(",", ":"), default=str)
    if len(encoded.encode("utf-8")) <= limit:
        return payload
    trimmed = dict(payload)
    trimmed["truncated"] = True
    for key in ("issues", "assumptions", "warnings", "operations", "unresolved_details"):
        if key in trimmed:
            trimmed[key] = trimmed[key][:5]
    encoded = json.dumps(trimmed, separators=(",", ":"), default=str)
    if len(encoded.encode("utf-8")) > limit:
        trimmed = {
            "truncated": True,
            "change_set_id": payload.get("change_set_id"),
            "status": payload.get("status"),
        }
    return trimmed


def arguments_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    """A bounded, redacted summary of tool arguments for persistence."""
    encoded = json.dumps(arguments, separators=(",", ":"), default=str)
    summary: dict[str, Any] = {"keys": sorted(str(key) for key in arguments), "bytes": len(encoded)}
    if len(encoded) <= 512:
        values: dict[str, Any] = {}
        for key, value in arguments.items():
            simple = value is None or isinstance(value, str | int | float | bool)
            values[str(key)] = value if simple else "[complex]"
        summary["values"] = values
    return summary


# -- read dispatch ---------------------------------------------------------


def dispatch_read_tool(
    db: Session,
    user: AuthenticatedUser,
    conversation: AssistantConversation,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    spec = READ_BY_NAME.get(tool_name)
    if spec is None:
        return _deny("unknown_tool")

    raw = json.dumps(arguments, separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) > MAX_TOOL_ARGUMENT_BYTES:
        return _deny("oversized_arguments")

    try:
        parsed = spec.args_model.model_validate(arguments)
    except ValidationError:
        return _deny("invalid_arguments")

    ctx = resolve_context(db, user, conversation.workspace_id)
    if spec.discipline is not None and spec.discipline not in ctx.disciplines:
        return _deny("tool_not_in_scope")

    request_kwargs = parsed.model_dump()
    if spec.needs_state:
        if conversation.active_state_id is None:
            return _deny("no_active_state")
        request_kwargs["state_id"] = conversation.active_state_id

    try:
        envelope = reads.run_read(ctx, spec.helper, ReadRequest(**request_kwargs))
    except Exception:  # noqa: BLE001 - upstream read failures become a safe code
        return {"status": "error", "error_code": "read_failed", "result": {}}

    return {
        "status": "ok",
        "error_code": None,
        "result": _bounded(envelope.model_dump(mode="json"), MAX_TOOL_RESULT_BYTES),
    }


# -- proposal dispatch -----------------------------------------------------


def _change_set_summary(change_set: HelperChangeSet) -> dict[str, Any]:
    return {
        "change_set_id": str(change_set.id),
        "helper": change_set.helper_name,
        "state_id": str(change_set.state_id) if change_set.state_id else None,
        "state_type": change_set.state_type,
        "status": change_set.status,
        "summary": (change_set.summary or "")[:500],
        "proposal_hash_prefix": (change_set.proposal_hash or "")[:12],
        "reused_count": len(change_set.reused_objects or []),
        "proposed_count": len(change_set.proposed_objects or []),
        "unresolved_count": len(change_set.unresolved_decisions or []),
        "assumptions": [str(item)[:300] for item in (change_set.assumptions or [])][:10],
        "warnings": [str(item)[:300] for item in (change_set.warnings or [])][:10],
        "ready_for_approval": (
            False
            if change_set.status in {"stale", "validation_failed", "draft"}
            else (change_set.validation_summary or {}).get("ready_for_approval")
        ),
    }


def dispatch_proposal_tool(
    db: Session,
    user: AuthenticatedUser,
    conversation: AssistantConversation,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    spec = PROPOSAL_BY_NAME.get(tool_name)
    if spec is None:
        return _deny("unknown_tool")

    if conversation.state_type == "current":
        return _deny("proposal_in_current")

    raw = json.dumps(arguments, separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) > MAX_TOOL_ARGUMENT_BYTES:
        return _deny("oversized_arguments")

    if any(key in arguments for key in FORBIDDEN_SCOPE_KEYS):
        return _deny("scope_override")

    ctx = resolve_context(db, user, conversation.workspace_id)
    if spec.composite:
        if len(ctx.disciplines) < 2:
            return _deny("tool_not_in_scope")
    elif spec.discipline is not None and spec.discipline not in ctx.disciplines:
        return _deny("tool_not_in_scope")

    if conversation.active_state_id is None:
        return _deny("no_active_state")

    payload = dict(arguments)
    payload["state_id"] = str(conversation.active_state_id)
    try:
        parsed = spec.args_model.model_validate(payload)
    except ValidationError:
        return _deny("invalid_arguments")

    try:
        change_set = service.run_proposal(ctx, spec.helper, parsed)
    except HTTPException as error:
        detail = error.detail
        code = detail.get("code") if isinstance(detail, dict) else "proposal_rejected"
        return _deny(str(code))

    operations = service.load_operations(ctx.db, change_set.id)
    change_set.unresolved_details = derive_unresolved_details(change_set, operations)
    ctx.db.commit()

    result = _bounded(_change_set_summary(change_set), MAX_PROPOSAL_RESULT_BYTES)
    result["unresolved_details_count"] = len(change_set.unresolved_details or [])
    return {"status": "ok", "error_code": None, "result": result}


# -- status dispatch -------------------------------------------------------


def dispatch_status_tool(
    db: Session,
    user: AuthenticatedUser,
    conversation: AssistantConversation,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name not in STATUS_TOOL_NAMES:
        return _deny("unknown_tool")

    raw = json.dumps(arguments, separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) > MAX_TOOL_ARGUMENT_BYTES:
        return _deny("oversized_arguments")

    try:
        parsed = ChangeSetArgs.model_validate(arguments)
    except ValidationError:
        return _deny("invalid_arguments")

    ctx = resolve_context(db, user, conversation.workspace_id)
    try:
        change_set = service.get_change_set(ctx, parsed.change_set_id)
    except HTTPException:
        return _deny("change_set_not_found")

    service.sync_staleness(ctx, change_set)

    if tool_name == "architecture_get_change_set":
        return {
            "status": "ok",
            "error_code": None,
            "result": _bounded(_change_set_summary(change_set), MAX_STATUS_RESULT_BYTES),
        }

    if tool_name == "architecture_validate_change_set":
        if service.sync_staleness(ctx, change_set):
            return {
                "status": "ok",
                "error_code": None,
                "result": _bounded(
                    {**_change_set_summary(change_set), "status": "stale"},
                    MAX_STATUS_RESULT_BYTES,
                ),
            }
        try:
            service.validate_change_set(ctx, change_set)
        except HTTPException as error:
            detail = error.detail
            code = detail.get("code") if isinstance(detail, dict) else "validation_rejected"
            return _deny(str(code))
        operations = service.load_operations(ctx.db, change_set.id)
        change_set.unresolved_details = derive_unresolved_details(change_set, operations)
        ctx.db.commit()

    operations = service.load_operations(ctx.db, change_set.id)
    counts: dict[str, int] = {}
    for operation in operations:
        counts[operation.validation_status] = counts.get(operation.validation_status, 0) + 1
    result = _change_set_summary(change_set)
    result["operation_counts"] = counts
    result["validation_summary"] = {
        key: value
        for key, value in (change_set.validation_summary or {}).items()
        if key != "issues"
    }
    result["issues"] = (change_set.validation_summary or {}).get("issues", [])[:10]
    return {"status": "ok", "error_code": None, "result": _bounded(result, MAX_STATUS_RESULT_BYTES)}


# -- unified dispatch ------------------------------------------------------


def dispatch_tool(
    db: Session,
    user: AuthenticatedUser,
    conversation: AssistantConversation,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name in READ_BY_NAME:
        return dispatch_read_tool(db, user, conversation, tool_name, arguments)
    if tool_name in PROPOSAL_BY_NAME:
        return dispatch_proposal_tool(db, user, conversation, tool_name, arguments)
    if tool_name in STATUS_TOOL_NAMES:
        return dispatch_status_tool(db, user, conversation, tool_name, arguments)
    return _deny("unknown_tool")
