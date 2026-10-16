"""Read-only architecture tool surface for the assistant.

This is the authoritative backend dispatch registry. It maps a closed set of
namespaced tool names to the existing bounded read helpers. There is no entry for
proposal, validation, approval, apply, undo, SQL, ORM, shell, filesystem, generic
HTTP, or arbitrary execution — those capabilities do not exist on this surface by
construction.

Every call is validated against a strict JSON Schema (``extra="forbid"``), size
capped, scoped to the conversation's workspace/disciplines/state, and returns a
bounded, truncation-annotated projection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser
from app.helper_actions import reads
from app.helper_actions.context import resolve_context
from app.helper_actions.schemas import ReadRequest
from app.models import AssistantConversation

MAX_TOOL_RESULT_BYTES = 16 * 1024
MAX_TOOL_ARGUMENT_BYTES = 4 * 1024


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


@dataclass(frozen=True)
class ReadToolSpec:
    name: str
    helper: str
    description: str
    args_model: type[BaseModel]
    discipline: str | None = None
    needs_state: bool = False


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

READ_TOOL_SPECS_BY_NAME: dict[str, ReadToolSpec] = {spec.name: spec for spec in READ_TOOL_SPECS}

#: Names that must never exist on the model surface.
FORBIDDEN_TOOL_NAMES = frozenset(
    {
        "approve_change_set",
        "apply_change_set",
        "undo_change_set",
        "validate_change_set",
        "propose_end_to_end_architecture",
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


def allowed_tool_names(disciplines: list[str]) -> list[str]:
    enabled = set(disciplines or [])
    return sorted(
        spec.name
        for spec in READ_TOOL_SPECS
        if spec.discipline is None or spec.discipline in enabled
    )


def tool_manifest(disciplines: list[str]) -> list[dict[str, Any]]:
    names = set(allowed_tool_names(disciplines))
    entries: list[dict[str, Any]] = []
    for spec in READ_TOOL_SPECS:
        if spec.name not in names:
            continue
        schema = spec.args_model.model_json_schema()
        schema.setdefault("additionalProperties", False)
        entries.append(
            {"name": spec.name, "description": spec.description, "input_schema": schema}
        )
    return entries


def manifest_tool_names() -> list[str]:
    return sorted(spec.name for spec in READ_TOOL_SPECS)


def _deny(code: str) -> dict[str, Any]:
    return {"status": "denied", "error_code": code, "result": {}}


def _bounded_result(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload, separators=(",", ":"), default=str)
    if len(encoded.encode("utf-8")) <= MAX_TOOL_RESULT_BYTES:
        return payload
    trimmed = dict(payload)
    trimmed["truncated"] = True
    trimmed["notes"] = list(trimmed.get("notes") or []) + [
        "Result exceeded the assistant size limit and was trimmed."
    ]
    trimmed["data"] = {"_trimmed": True, "counts": payload.get("counts", {})}
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


def dispatch_read_tool(
    db: Session,
    user: AuthenticatedUser,
    conversation: AssistantConversation,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Authoritative dispatch for one read tool call. Never raises to the caller."""
    spec = READ_TOOL_SPECS_BY_NAME.get(tool_name)
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

    read_request = ReadRequest(**request_kwargs)
    try:
        envelope = reads.run_read(ctx, spec.helper, read_request)
    except Exception:  # noqa: BLE001 - upstream read failures become a safe code
        return {"status": "error", "error_code": "read_failed", "result": {}}

    return {
        "status": "ok",
        "error_code": None,
        "result": _bounded_result(envelope.model_dump(mode="json")),
    }
