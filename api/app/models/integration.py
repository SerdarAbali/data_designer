from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_object_id", "source_system_id", "tenant_id"],
            ["objects.id", "objects.system_id", "objects.tenant_id"],
            name="fk_integrations_source_object",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_object_id", "target_system_id", "tenant_id"],
            ["objects.id", "objects.system_id", "objects.tenant_id"],
            name="fk_integrations_target_object",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["error_response_object_id", "target_system_id", "tenant_id"],
            ["objects.id", "objects.system_id", "objects.tenant_id"],
            name="fk_integrations_error_response_object",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_integrations_id_tenant"),
        Index(
            "uq_integrations_active_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "jsonb_typeof(graph) = 'object'",
            name="ck_integrations_graph_object",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "jsonb_typeof(response_graph) = 'object'",
            name="ck_integrations_response_graph_object",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "jsonb_typeof(error_response_graph) = 'object'",
            name="ck_integrations_error_response_graph_object",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "interaction_type IN ('ONE_WAY', 'REQUEST_RESPONSE', 'ASYNC_CALLBACK')",
            name="ck_integrations_interaction_type",
        ),
        CheckConstraint(
            "jsonb_typeof(trigger_config) = 'object'",
            name="ck_integrations_trigger_config_object",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "jsonb_typeof(sample_rows) = 'array'",
            name="ck_integrations_sample_rows_array",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("revision >= 1", name="ck_integrations_revision_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    source_system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    trigger_config: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    graph: Mapped[dict] = mapped_column(json_type, nullable=False, default=lambda: {
        "version": 1,
        "nodes": [],
        "edges": [],
    })
    response_graph: Mapped[dict] = mapped_column(json_type, nullable=False, default=lambda: {
        "version": 1,
        "nodes": [],
        "edges": [],
    })
    error_response_graph: Mapped[dict] = mapped_column(
        json_type,
        nullable=False,
        default=lambda: {"version": 1, "nodes": [], "edges": []},
    )
    error_response_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    interaction_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ONE_WAY"
    )
    sample_rows: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationFieldRef(Base):
    __tablename__ = "integration_field_refs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_integration_field_refs_integration",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["field_id", "object_id", "tenant_id"],
            ["fields.id", "fields.object_id", "fields.tenant_id"],
            name="fk_integration_field_refs_field",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "integration_id", "field_id", "direction",
            name="uq_integration_field_refs_field_direction",
        ),
        Index(
            "ix_integration_field_refs_target",
            "tenant_id",
            "direction",
            "object_id",
            "field_id",
            "integration_id",
        ),
        CheckConstraint(
            "direction IN ('source', 'target', 'response_source', 'response_target', "
            "'error_response_source', 'error_response_target')",
            name="ck_field_ref_direction",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    field_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(24), nullable=False)


class IntegrationDependency(Base):
    __tablename__ = "integration_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["upstream_integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_integration_dependencies_upstream",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["downstream_integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_integration_dependencies_downstream",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "upstream_integration_id",
            "downstream_integration_id",
            name="uq_integration_dependency",
        ),
        Index(
            "ix_integration_dependencies_upstream",
            "tenant_id",
            "upstream_integration_id",
            "downstream_integration_id",
        ),
        Index(
            "ix_integration_dependencies_downstream",
            "tenant_id",
            "downstream_integration_id",
            "upstream_integration_id",
        ),
        CheckConstraint(
            "upstream_integration_id != downstream_integration_id",
            name="ck_integration_dependency_not_self",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    upstream_integration_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    downstream_integration_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
