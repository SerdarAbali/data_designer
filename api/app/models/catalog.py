from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

json_type = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(UTC)


class CatalogSystem(Base):
    __tablename__ = "systems"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_systems_id_tenant"),
        Index(
            "uq_systems_active_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[dict | None] = mapped_column(json_type)
    binding_state: Mapped[str] = mapped_column(String(100), nullable=False, default="unbound")
    extra_metadata: Mapped[dict] = mapped_column(
        "metadata", json_type, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogObject(Base):
    __tablename__ = "objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["system_id", "tenant_id"],
            ["systems.id", "systems.tenant_id"],
            ondelete="RESTRICT",
            name="fk_objects_system_tenant",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_objects_id_tenant"),
        UniqueConstraint("id", "system_id", "tenant_id", name="uq_objects_id_system_tenant"),
        Index(
            "uq_objects_active_name",
            "system_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    external_identifier: Mapped[str | None] = mapped_column(String(255))
    origin: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    extra_metadata: Mapped[dict] = mapped_column(
        "metadata", json_type, nullable=False, default=dict
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogField(Base):
    __tablename__ = "fields"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["objects.id", "objects.tenant_id"],
            ondelete="RESTRICT",
            name="fk_fields_object_tenant",
        ),
        UniqueConstraint("id", "object_id", "tenant_id", name="uq_fields_id_object_tenant"),
        Index(
            "uq_fields_active_name",
            "object_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    required: Mapped[bool] = mapped_column(nullable=False, default=False)
    nullable: Mapped[bool] = mapped_column(nullable=False, default=True)
    default_value: Mapped[object | None] = mapped_column(json_type)
    external_identifier: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    origin: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    extra_metadata: Mapped[dict] = mapped_column(
        "metadata", json_type, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
