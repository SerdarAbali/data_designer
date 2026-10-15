from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    event,
    insert,
    text,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db import Base
from app.models.catalog import CatalogSystem, utc_now


class ArchitectureObject(Base):
    __tablename__ = "architecture_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["system_id", "tenant_id"],
            ["systems.id", "systems.tenant_id"],
            name="fk_architecture_objects_system_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_architecture_objects_id_tenant"),
        Index(
            "uq_architecture_objects_system",
            "tenant_id",
            "system_id",
            unique=True,
            postgresql_where=text("system_id IS NOT NULL"),
            sqlite_where=text("system_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    system_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class _TypedArchitectureObject:
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    @declared_attr.directive
    def __table_args__(cls):
        return (
            ForeignKeyConstraint(
                ["object_id", "tenant_id"],
                ["architecture_objects.id", "architecture_objects.tenant_id"],
                ondelete="CASCADE",
            ),
        )


class BusinessRequirement(_TypedArchitectureObject, Base):
    __tablename__ = "business_requirements"


class BusinessCapability(_TypedArchitectureObject, Base):
    __tablename__ = "business_capabilities"


class InformationObject(_TypedArchitectureObject, Base):
    __tablename__ = "information_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["authoritative_system_id", "tenant_id"],
            ["systems.id", "systems.tenant_id"],
            name="fk_information_objects_authoritative_system_tenant",
            ondelete="RESTRICT",
        ),
    )

    owner: Mapped[str] = mapped_column(String(160), nullable=False)
    authoritative_system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class SolutionBoundary(_TypedArchitectureObject, Base):
    __tablename__ = "solution_boundaries"


class SolutionComponent(_TypedArchitectureObject, Base):
    __tablename__ = "solution_components"


class ArchitectureInterface(_TypedArchitectureObject, Base):
    __tablename__ = "architecture_interfaces"


@event.listens_for(CatalogSystem, "after_insert")
def register_system_architecture_object(mapper, connection, system: CatalogSystem) -> None:
    connection.execute(
        insert(ArchitectureObject.__table__).values(
            id=system.id,
            tenant_id=system.tenant_id,
            kind="system",
            system_id=system.id,
        )
    )
