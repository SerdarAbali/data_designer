"""Helper-action persistence: change sets, operations, and append-only audit rows.

These tables back the deterministic architecture helper-action layer (Slice 1).
They store helper lifecycle data only. Nothing here is an architecture-domain
record: proposals never create or modify architecture objects, state
memberships, relationships, Catalog records, Contracts, scenarios, or tests.

Audit events are append-only. ORM-level guards reject updates and deletes so the
application can never rewrite history through the normal session.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.catalog import json_type, utc_now

# Explicit lifecycle states. ``applied`` and ``undone`` are reserved for later
# slices; Slice 1 only ever moves through ``approved``.
CHANGE_SET_STATUSES = (
    "draft",
    "validation_failed",
    "validated",
    "approved",
    "stale",
    "applied",
    "undone",
    "failed",
)


class HelperChangeSet(Base):
    """A deterministic, reviewable proposal. Persists no domain changes."""

    __tablename__ = "helper_change_sets"
    __table_args__ = (
        Index("ix_helper_change_sets_workspace", "tenant_id", "workspace_id"),
        Index("ix_helper_change_sets_state", "tenant_id", "state_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("architecture_states.id", ondelete="SET NULL"),
        nullable=True,
    )
    state_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    helper_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    input_summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    assumptions: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    unresolved_decisions: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    reused_objects: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    proposed_objects: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    expected_traceability: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    validation_summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    unresolved_details: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    proposal_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    apply_summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    undo_summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class HelperChangeOperation(Base):
    """One typed proposed operation inside a change set.

    ``domain_action`` and ``target_type`` are closed, validated string values;
    they are never executable code, function names, or ORM/SQL payloads.
    """

    __tablename__ = "helper_change_operations"
    __table_args__ = (
        UniqueConstraint(
            "change_set_id", "operation_id", name="uq_helper_change_operations_operation_id"
        ),
        Index("ix_helper_change_operations_change_set", "change_set_id", "ordinal"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    change_set_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("helper_change_sets.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    domain_action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    temporary_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    before_value: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    proposed_value: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    depends_on: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    validation_issues: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Apply/undo ownership (Slice 4). ``ownership`` records exactly what this
    # change set wrote so undo can remove only change-set-owned rows.
    applied_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    apply_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    ownership: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    post_fingerprint: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    undo_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    undo_conflict: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    resolution_state: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class HelperAuditEvent(Base):
    """Append-only audit event. Never stores secrets or full uploaded files."""

    __tablename__ = "helper_audit_events"
    __table_args__ = (
        Index("ix_helper_audit_events_change_set", "tenant_id", "change_set_id"),
        Index("ix_helper_audit_events_workspace", "tenant_id", "workspace_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    change_set_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("helper_change_sets.id", ondelete="CASCADE"), nullable=True
    )
    state_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    affected_object_ids: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    affected_contract_ids: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


def _deny_audit_mutation(mapper, connection, target) -> None:  # noqa: ARG001
    raise ValueError("Helper audit events are append-only and cannot be modified or deleted")


event.listen(HelperAuditEvent, "before_update", _deny_audit_mutation)
event.listen(HelperAuditEvent, "before_delete", _deny_audit_mutation)
