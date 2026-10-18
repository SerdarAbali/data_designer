from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.catalog import json_type, utc_now

#: The closed baseline vocabulary. It is meaningful only on a Current state;
#: Candidate and Target states store NULL.
BASELINE_DRAFT = "draft"
BASELINE_LOCKED = "locked"
BASELINE_STATUSES: tuple[str, ...] = (BASELINE_DRAFT, BASELINE_LOCKED)


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        Index(
            "uq_workspaces_active_tenant_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disciplines: Mapped[list[str]] = mapped_column(
        json_type,
        nullable=False,
        default=lambda: ["enterprise", "information", "solution", "integration"],
    )
    demo_preset: Mapped[str | None] = mapped_column(String(40), nullable=True)
    demo_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    demo_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    demo_assets: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    assistant_enabled: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ArchitectureState(Base):
    __tablename__ = "architecture_states"
    __table_args__ = (
        Index(
            "uq_architecture_states_active_name",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        # A NULL value makes this expression NULL rather than false, and a check
        # constraint only rejects false, so Candidate and Target rows are free to
        # store no baseline status at all.
        CheckConstraint(
            "baseline_status IN ('draft', 'locked')",
            name="ck_architecture_states_baseline_status",
        ),
        Index(
            "ix_architecture_states_workspace_type",
            "workspace_id",
            "state_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    state_type: Mapped[str] = mapped_column(String(32), nullable=False, default="current")
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # The Current baseline lifecycle. ``draft`` is an editable capture phase;
    # ``locked`` is the read-only, irreversible baseline. Candidate and Target
    # states leave this NULL because it carries no meaning for them.
    baseline_status: Mapped[str | None] = mapped_column(String(16))
    # Server-controlled lock metadata. Never accepted from a client.
    baseline_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    baseline_locked_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    nodes: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    relationships: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
