from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.integration import json_type, utc_now


class Scenario(Base):
    """Design-time scenario; references contracts by ID and never stores their definitions."""

    __tablename__ = "scenarios"
    __table_args__ = (
        ForeignKeyConstraint(
            ["scope_integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_scenarios_scope_integration",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_scenarios_active_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_scenarios_scope", "tenant_id", "scope_integration_id"),
        CheckConstraint(
            "category IN ('happy_path', 'alternative', 'error')",
            name="ck_scenarios_category",
        ),
        CheckConstraint(
            "jsonb_typeof(document) = 'object'",
            name="ck_scenarios_document_object",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("revision >= 1", name="ck_scenarios_revision_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    scope_integration_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="happy_path")
    description: Mapped[str | None] = mapped_column(String(2000))
    document: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
