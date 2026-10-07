"""Create integrations, graph field references, and dependencies.

Revision ID: 0003_integrations
Revises: 0002_catalog
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_integrations"
down_revision: str | None = "0002_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source_system_id", sa.Uuid(), nullable=False),
        sa.Column("source_object_id", sa.Uuid(), nullable=False),
        sa.Column("target_system_id", sa.Uuid(), nullable=False),
        sa.Column("target_object_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("trigger_config", json_type, nullable=False),
        sa.Column("graph", json_type, nullable=False),
        sa.Column("sample_rows", json_type, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("revision >= 1", name="ck_integrations_revision_positive"),
        sa.CheckConstraint(
            "jsonb_typeof(graph) = 'object'", name="ck_integrations_graph_object"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(trigger_config) = 'object'",
            name="ck_integrations_trigger_config_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sample_rows) = 'array'",
            name="ck_integrations_sample_rows_array",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_integrations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_object_id", "source_system_id", "tenant_id"],
            ["objects.id", "objects.system_id", "objects.tenant_id"],
            name="fk_integrations_source_object",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_object_id", "target_system_id", "tenant_id"],
            ["objects.id", "objects.system_id", "objects.tenant_id"],
            name="fk_integrations_target_object",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_integrations_id_tenant"),
    )
    op.create_index(
        "uq_integrations_active_name",
        "integrations",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "integration_field_refs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("field_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "direction IN ('source', 'target')", name="ck_field_ref_direction"
        ),
        sa.ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_integration_field_refs_integration",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["field_id", "object_id", "tenant_id"],
            ["fields.id", "fields.object_id", "fields.tenant_id"],
            name="fk_integration_field_refs_field",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_id",
            "field_id",
            "direction",
            name="uq_integration_field_refs_field_direction",
        ),
    )
    op.create_table(
        "integration_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("upstream_integration_id", sa.Uuid(), nullable=False),
        sa.Column("downstream_integration_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "upstream_integration_id != downstream_integration_id",
            name="ck_integration_dependency_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["upstream_integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_integration_dependencies_upstream",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["downstream_integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_integration_dependencies_downstream",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "upstream_integration_id",
            "downstream_integration_id",
            name="uq_integration_dependency",
        ),
    )


def downgrade() -> None:
    op.drop_table("integration_dependencies")
    op.drop_table("integration_field_refs")
    op.drop_index("uq_integrations_active_name", table_name="integrations")
    op.drop_table("integrations")
