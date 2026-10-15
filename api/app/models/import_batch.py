"""Import batch and per-row provenance records."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
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


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_import_batches_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_import_batches_workspace",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('applied', 'undone', 'undo_blocked')",
            name="ck_import_batches_status",
        ),
        Index("ix_import_batches_workspace", "tenant_id", "workspace_id", "imported_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    import_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="applied")
    counts: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRowResult(Base):
    __tablename__ = "import_row_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_import_row_results_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name="fk_import_row_results_batch",
            ondelete="CASCADE",
        ),
        UniqueConstraint("batch_id", "row_number", name="uq_import_row_results_row"),
        Index("ix_import_row_results_target", "tenant_id", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(json_type)
    after: Mapped[dict | None] = mapped_column(json_type)
