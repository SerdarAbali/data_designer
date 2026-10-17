"""Strict request/response schemas for the Architecture Assistant API.

Every request model forbids unknown fields and is bounded. Responses never carry
OpenCode credentials, the internal runtime URL, provider secrets, raw upstream
payloads, or unrestricted architecture graphs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

WorkbenchView = Literal[
    "canvas",
    "catalog",
    "enterprise",
    "information",
    "solution",
    "integration",
    "scenarios",
    "unknown",
]


class WorkspaceAssistantSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_enabled: bool


PrivacyClassification = Literal["public", "internal", "confidential", "restricted"]
ReasoningEffort = Literal["low", "medium", "high"]


class AssistantSettingsUpdate(BaseModel):
    """Owner-only provider/model settings. Never carries a credential."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, max_length=80)
    model_id: str | None = Field(default=None, max_length=120)
    model_variant: str | None = Field(default=None, max_length=40)
    reasoning_effort: ReasoningEffort | None = None
    max_input_tokens: int | None = Field(default=None, ge=1000, le=200000)
    max_output_tokens: int | None = Field(default=None, ge=256, le=32000)
    timeout_seconds: int | None = Field(default=None, ge=30, le=600)
    step_limit: int | None = Field(default=None, ge=1, le=24)
    retention_days: int | None = Field(default=None, ge=1, le=90)
    privacy_classification: PrivacyClassification | None = None
    trains_on_data: bool | None = None
    approved_for_sensitive: bool | None = None
    fallback_provider: str | None = Field(default=None, max_length=80)
    fallback_model_id: str | None = Field(default=None, max_length=120)
    fallback_enabled: bool | None = None


class AssistantSettingsResponse(BaseModel):
    workspace_enabled: bool
    is_owner: bool
    provider: str | None = None
    model_id: str | None = None
    model_variant: str | None = None
    reasoning_effort: str | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    timeout_seconds: int | None = None
    step_limit: int | None = None
    retention_days: int | None = None
    privacy_classification: str | None = None
    trains_on_data: bool | None = None
    approved_for_sensitive: bool | None = None
    fallback_provider: str | None = None
    fallback_model_id: str | None = None
    fallback_enabled: bool | None = None
    credential_status: str | None = None
    credential_last_verified_at: datetime | None = None
    privacy_allowed: bool | None = None
    privacy_reason: str | None = None


class AssistantStatusResponse(BaseModel):
    assistant_enabled: bool
    runtime_status: str
    expected_opencode_version: str
    observed_opencode_version: str | None = None
    probe_checked_at: datetime
    reason_code: str
    correlation_id: str
    workspace_enabled: bool | None = None
    is_owner: bool | None = None


class ScopeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: UUID | None = None
    discipline: str | None = Field(default=None, max_length=32)
    workbench_view: WorkbenchView | None = None
    selection_ids: list[UUID] = Field(default_factory=list, max_length=10)


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    state_id: UUID | None = None
    discipline: str | None = Field(default=None, max_length=32)
    workbench_view: WorkbenchView | None = None
    selection_ids: list[UUID] = Field(default_factory=list, max_length=10)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)


class ToolCallSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    call_id: str
    tool_name: str
    status: str
    error_code: str | None = None
    duration_ms: int | None = None
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    role: str
    content: str
    status: str
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    status: str
    state_id: UUID | None = None
    state_type: str | None = None
    discipline: str | None = None
    workbench_view: str | None = None
    message_count: int
    tool_call_count: int
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageResponse] = Field(default_factory=list)
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)


class ToolManifestEntry(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolManifestResponse(BaseModel):
    tools: list[ToolManifestEntry]
    scope: dict[str, Any] = Field(default_factory=dict)


class InternalToolCallRequest(BaseModel):
    """Plugin → backend dispatch. Identity comes from the OpenCode session id."""

    model_config = ConfigDict(extra="forbid")

    opencode_session_id: str = Field(min_length=1, max_length=120)
    call_id: str = Field(min_length=1, max_length=120)
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class InternalToolCallResponse(BaseModel):
    status: Literal["ok", "denied", "error"]
    error_code: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class InternalScopeResponse(BaseModel):
    status: Literal["ok", "denied"]
    tools: list[str] = Field(default_factory=list)


ProposalEventAction = Literal[
    "approval_started",
    "approved",
    "approval_failed",
    "apply_started",
    "applied",
    "apply_failed",
    "undo_started",
    "undone",
    "undo_conflict",
]


class ProposalEventRequest(BaseModel):
    """A bounded application event for a user-driven proposal action.

    The browser reports the action; the backend derives the bounded summary from
    the authoritative helper change set. Full operations and payloads are never
    stored here.
    """

    model_config = ConfigDict(extra="forbid")

    change_set_id: UUID
    action: ProposalEventAction
    reason_code: str | None = Field(default=None, max_length=40, pattern=r"^[a-z0-9_]+$")
