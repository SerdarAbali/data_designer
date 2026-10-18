from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
    insert,
    text,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db import Base
from app.models.catalog import CatalogSystem, json_type, utc_now


class ArchitectureObject(Base):
    __tablename__ = "architecture_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["system_id", "tenant_id"],
            ["systems.id", "systems.tenant_id"],
            name="fk_architecture_objects_system_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["catalog_object_id", "tenant_id"],
            ["objects.id", "objects.tenant_id"],
            name="fk_architecture_objects_catalog_object_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["catalog_field_id", "tenant_id"],
            ["fields.id", "fields.tenant_id"],
            name="fk_architecture_objects_catalog_field_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_architecture_objects_integration_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["scenario_id", "tenant_id"],
            ["scenarios.id", "scenarios.tenant_id"],
            name="fk_architecture_objects_scenario_tenant",
            ondelete="CASCADE",
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
        Index(
            "uq_architecture_objects_catalog_object",
            "tenant_id",
            "catalog_object_id",
            unique=True,
            postgresql_where=text("catalog_object_id IS NOT NULL"),
            sqlite_where=text("catalog_object_id IS NOT NULL"),
        ),
        Index(
            "uq_architecture_objects_catalog_field",
            "tenant_id",
            "catalog_field_id",
            unique=True,
            postgresql_where=text("catalog_field_id IS NOT NULL"),
            sqlite_where=text("catalog_field_id IS NOT NULL"),
        ),
        CheckConstraint(
            "(system_id IS NOT NULL)::int + (catalog_object_id IS NOT NULL)::int"
            " + (catalog_field_id IS NOT NULL)::int + (integration_id IS NOT NULL)::int"
            " + (scenario_id IS NOT NULL)::int <= 1",
            name="ck_architecture_objects_single_reference",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    system_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    catalog_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    catalog_field_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    integration_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    scenario_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
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
        Index(
            "uq_information_objects_external_id",
            "tenant_id",
            "external_identifier",
            unique=True,
            postgresql_where=text("external_identifier IS NOT NULL"),
            sqlite_where=text("external_identifier IS NOT NULL"),
        ),
    )

    owner: Mapped[str | None] = mapped_column(String(160))
    steward: Mapped[str | None] = mapped_column(String(160))
    authoritative_system_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    external_identifier: Mapped[str | None] = mapped_column(String(255))
    classification: Mapped[str | None] = mapped_column(String(100))
    sensitivity: Mapped[str | None] = mapped_column(String(40))


class SolutionBoundary(_TypedArchitectureObject, Base):
    __tablename__ = "solution_boundaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("object_id", "tenant_id", name="uq_solution_boundaries_object_tenant"),
        Index(
            "uq_solution_boundaries_external_id",
            "tenant_id",
            "external_identifier",
            unique=True,
            postgresql_where=text("external_identifier IS NOT NULL"),
            sqlite_where=text("external_identifier IS NOT NULL"),
        ),
    )

    owner: Mapped[str | None] = mapped_column(String(160))
    external_identifier: Mapped[str | None] = mapped_column(String(255))


class SolutionComponent(_TypedArchitectureObject, Base):
    __tablename__ = "solution_components"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("object_id", "tenant_id", name="uq_solution_components_object_tenant"),
        ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_solution_components_solution_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_solution_components_solution", "tenant_id", "solution_object_id"),
    )

    solution_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    parent_component_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    responsibility: Mapped[str | None] = mapped_column(String(2000))
    component_type: Mapped[str | None] = mapped_column(String(60))
    technology: Mapped[str | None] = mapped_column(String(160))
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )


class ArchitectureInterface(_TypedArchitectureObject, Base):
    __tablename__ = "architecture_interfaces"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("object_id", "tenant_id", name="uq_architecture_interfaces_object_tenant"),
        ForeignKeyConstraint(
            ["component_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_interfaces_component_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_architecture_interfaces_component", "tenant_id", "component_object_id"),
    )

    component_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="provided")
    interface_kind: Mapped[str | None] = mapped_column(String(16))
    protocol: Mapped[str | None] = mapped_column(String(60))
    technology: Mapped[str | None] = mapped_column(String(160))
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )


class InterfaceOperation(Base):
    """Canonical operation/event exposed by a solution interface (child record)."""

    __tablename__ = "interface_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_interface_operations_object_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["interface_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_interface_operations_interface_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "interface_object_id", "name", name="uq_interface_operations_interface_name"
        ),
        Index("ix_interface_operations_interface", "tenant_id", "interface_object_id"),
    )

    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    interface_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    operation_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="operation")
    request_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    response_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DataRepository(Base):
    """Canonical data store referenced by a solution (child record)."""

    __tablename__ = "data_repositories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_data_repositories_object_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_data_repositories_solution_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_data_repositories_solution", "tenant_id", "solution_object_id"),
    )

    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    solution_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    owner: Mapped[str | None] = mapped_column(String(160))
    repository_type: Mapped[str | None] = mapped_column(String(40))
    technology: Mapped[str | None] = mapped_column(String(160))
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DeploymentNode(Base):
    """Canonical deployment/hosting target for solution components (child record)."""

    __tablename__ = "deployment_nodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_deployment_nodes_object_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_deployment_nodes_solution_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_deployment_nodes_solution", "tenant_id", "solution_object_id"),
    )

    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    solution_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    technology: Mapped[str | None] = mapped_column(String(160))
    environment: Mapped[str | None] = mapped_column(String(40))
    hosting: Mapped[str | None] = mapped_column(String(40))
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TrustBoundary(Base):
    """Canonical trust/security boundary crossed by solution interfaces (child record)."""

    __tablename__ = "trust_boundaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_trust_boundaries_object_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_trust_boundaries_solution_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_trust_boundaries_solution", "tenant_id", "solution_object_id"),
    )

    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    solution_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    security_level: Mapped[str | None] = mapped_column(String(40))
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SolutionIntegration(Base):
    """An authoritative association between a Solution Boundary and a Contract.

    Contract ownership cannot be inferred from source/target system membership:
    an external participating system may sit outside ``SolutionMember`` while its
    Contract still belongs to the solution. This association is therefore an
    explicit, state-aware statement with an approved ``role``.

    ``created_in_state_id`` null means canonically applicable; otherwise the
    association was introduced for one Candidate/Target state.
    """

    __tablename__ = "solution_integrations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_solution_integrations_solution_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_solution_integrations_integration_tenant",
            ondelete="RESTRICT",
        ),
        # One association per (solution, contract) inside a state scope. Two
        # partial indexes are needed because NULL is never equal to NULL in a
        # unique constraint, so a plain unique would allow duplicate canonical
        # rows on both PostgreSQL and SQLite.
        Index(
            "uq_solution_integrations_canonical",
            "tenant_id",
            "solution_object_id",
            "integration_id",
            unique=True,
            postgresql_where=text("created_in_state_id IS NULL"),
            sqlite_where=text("created_in_state_id IS NULL"),
        ),
        Index(
            "uq_solution_integrations_state",
            "tenant_id",
            "solution_object_id",
            "integration_id",
            "created_in_state_id",
            unique=True,
            postgresql_where=text("created_in_state_id IS NOT NULL"),
            sqlite_where=text("created_in_state_id IS NOT NULL"),
        ),
        Index(
            "ix_solution_integrations_solution", "tenant_id", "solution_object_id"
        ),
        Index("ix_solution_integrations_integration", "tenant_id", "integration_id"),
        CheckConstraint(
            "role IN ('owned', 'participating', 'dependency')",
            name="ck_solution_integrations_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    solution_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="owned")
    description: Mapped[str | None] = mapped_column(String(500))
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SolutionMember(Base):
    """Canonical membership of a catalog system in a solution boundary."""

    __tablename__ = "solution_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_solution_members_solution_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["system_id", "tenant_id"],
            ["systems.id", "systems.tenant_id"],
            name="fk_solution_members_system_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("solution_object_id", "system_id", name="uq_solution_members_pair"),
        UniqueConstraint("id", "tenant_id", name="uq_solution_members_id_tenant"),
        Index("ix_solution_members_solution", "tenant_id", "solution_object_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    solution_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InformationAttribute(Base):
    """Canonical attribute (column/field) belonging to an information entity."""

    __tablename__ = "information_attributes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_information_attributes_object_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["entity_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_information_attributes_entity_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("entity_object_id", "name", name="uq_information_attributes_entity_name"),
        Index("ix_information_attributes_entity", "tenant_id", "entity_object_id"),
    )

    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entity_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False, default="string")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_identifier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    definition: Mapped[str | None] = mapped_column(String(2000))
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ArchitectureRelationship(Base):
    """Typed edge between two architecture registry objects (both ends resolved)."""

    __tablename__ = "architecture_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_relationships_source_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["target_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_relationships_target_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "source_object_id",
            "target_object_id",
            "relationship_type",
            name="uq_architecture_relationships_edge",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_architecture_relationships_id_tenant"),
        Index("ix_architecture_relationships_source", "tenant_id", "source_object_id"),
        Index("ix_architecture_relationships_target", "tenant_id", "target_object_id"),
        Index("ix_architecture_relationships_type", "tenant_id", "relationship_type"),
        CheckConstraint(
            "source_object_id <> target_object_id",
            name="ck_architecture_relationships_distinct_ends",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    source_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(60), nullable=False)
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ArchitectureStateMember(Base):
    """Per-state membership / scalar override for a canonical child record."""

    __tablename__ = "architecture_state_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_state_members_object_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "state_id", "object_id", name="uq_architecture_state_members_state_object"
        ),
        Index("ix_architecture_state_members_state", "tenant_id", "state_id"),
        CheckConstraint(
            "membership IN ('included', 'excluded')",
            name="ck_architecture_state_members_membership",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    state_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("architecture_states.id", ondelete="CASCADE"),
        nullable=False,
    )
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    membership: Mapped[str] = mapped_column(String(16), nullable=False, default="included")
    property_overrides: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class BusinessGoal(_TypedArchitectureObject, Base):
    """Strategic goal with a measurable outcome and target horizon."""

    __tablename__ = "business_goals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        Index("ix_business_goals_tenant", "tenant_id"),
    )

    owner: Mapped[str | None] = mapped_column(String(160))
    outcome_metric: Mapped[str | None] = mapped_column(String(500))
    horizon: Mapped[str | None] = mapped_column(String(60))
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class BusinessProcess(_TypedArchitectureObject, Base):
    """Business process or value stream."""

    __tablename__ = "business_processes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        Index("ix_business_processes_tenant", "tenant_id"),
    )

    owner: Mapped[str | None] = mapped_column(String(160))
    process_type: Mapped[str | None] = mapped_column(String(40))
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ArchitecturePrinciple(_TypedArchitectureObject, Base):
    """Architecture principle, constraint, quality attribute, or risk."""

    __tablename__ = "architecture_principles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        Index("ix_architecture_principles_tenant", "tenant_id"),
    )

    principle_type: Mapped[str | None] = mapped_column(String(40))
    rationale: Mapped[str | None] = mapped_column(String(2000))
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OrganizationRole(_TypedArchitectureObject, Base):
    """Organizational unit or responsible role."""

    __tablename__ = "organization_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
        Index("ix_organization_roles_tenant", "tenant_id"),
    )

    role_type: Mapped[str | None] = mapped_column(String(40))
    properties: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


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
