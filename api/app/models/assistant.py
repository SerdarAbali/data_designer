"""Assistant persistence: conversations, messages, tool calls, and events.

These tables back the read-only Architecture Assistant (Slice C). They store
conversation state only. Nothing here is an architecture-domain record: the
assistant may read the architecture and explain it, but it can never write
architecture objects, state memberships, relationships, Catalog records,
Contracts, scenarios, or tests.

Application transcripts are authoritative. The OpenCode session id is stored as a
disposable execution cache reference and is never a system of record.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.catalog import json_type, utc_now

CONVERSATION_STATUSES = ("active", "cancelling", "archived", "deleted")
MESSAGE_ROLES = ("user", "assistant", "notice")
MESSAGE_STATUSES = ("pending", "streaming", "complete", "failed", "cancelled")
TOOL_CALL_STATUSES = ("pending", "running", "completed", "denied", "error")

#: Privacy classifications. ``confidential`` and ``restricted`` are sensitive.
PRIVACY_CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
SENSITIVE_CLASSIFICATIONS = ("confidential", "restricted")
CREDENTIAL_STATUSES = ("configured", "missing", "invalid")


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (
        Index("ix_assistant_conversations_scope", "tenant_id", "workspace_id", "user_id"),
        Index("ix_assistant_conversations_state", "tenant_id", "active_state_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New conversation")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    active_state_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    state_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workbench_view: Mapped[str | None] = mapped_column(String(32), nullable=True)
    selection_ids: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    opencode_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    opencode_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_assistant_messages_sequence"),
        Index("ix_assistant_messages_conversation", "conversation_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="complete")
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    referenced_change_set_ids: Mapped[list] = mapped_column(
        json_type, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AssistantToolCall(Base):
    """A bounded summary of one model tool call. Never stores full payloads."""

    __tablename__ = "assistant_tool_calls"
    __table_args__ = (
        UniqueConstraint("conversation_id", "call_id", name="uq_assistant_tool_calls_call_id"),
        Index("ix_assistant_tool_calls_conversation", "conversation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    call_id: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    arguments_summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    change_set_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssistantEvent(Base):
    """Durable, sequenced SSE event. Bounded and redacted before it is stored."""

    __tablename__ = "assistant_events"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_assistant_events_sequence"),
        Index("ix_assistant_events_conversation", "conversation_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AssistantModelSettings(Base):
    """Tenant-scoped provider/model configuration (owner-only).

    This table never stores provider credentials: it records only non-secret
    configuration plus the credential *status* observed server-side. Secrets live
    exclusively in server-side environment/secret material.
    """

    __tablename__ = "assistant_model_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_assistant_model_settings_tenant"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_variant: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reasoning_effort: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    max_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=16000)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4000)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    step_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    privacy_classification: Mapped[str] = mapped_column(
        String(20), nullable=False, default="internal"
    )
    trains_on_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_for_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fallback_model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fallback_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credential_status: Mapped[str] = mapped_column(String(20), nullable=False, default="missing")
    credential_last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
