"""Add information modeler tables and registry reference columns.

Revision ID: 0012_information_modeler
Revises: 0011_import_provenance
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0012_information_modeler"
down_revision: str | None = "0011_import_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("fields") as batch_op:
        batch_op.create_unique_constraint("uq_fields_id_tenant", ["id", "tenant_id"])

    with op.batch_alter_table("scenarios") as batch_op:
        batch_op.create_unique_constraint("uq_scenarios_id_tenant", ["id", "tenant_id"])

    with op.batch_alter_table("information_objects") as batch_op:
        batch_op.alter_column("owner", existing_type=sa.String(length=160), nullable=True)
        batch_op.alter_column("authoritative_system_id", existing_type=sa.Uuid(), nullable=True)

    with op.batch_alter_table("architecture_objects") as batch_op:
        batch_op.add_column(sa.Column("catalog_object_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("catalog_field_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("integration_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("scenario_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_architecture_objects_catalog_object_tenant",
            "objects",
            ["catalog_object_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_architecture_objects_catalog_field_tenant",
            "fields",
            ["catalog_field_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_architecture_objects_integration_tenant",
            "integrations",
            ["integration_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_architecture_objects_scenario_tenant",
            "scenarios",
            ["scenario_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )

    op.create_index(
        "uq_architecture_objects_catalog_object",
        "architecture_objects",
        ["tenant_id", "catalog_object_id"],
        unique=True,
        postgresql_where=sa.text("catalog_object_id IS NOT NULL"),
        sqlite_where=sa.text("catalog_object_id IS NOT NULL"),
    )
    op.create_index(
        "uq_architecture_objects_catalog_field",
        "architecture_objects",
        ["tenant_id", "catalog_field_id"],
        unique=True,
        postgresql_where=sa.text("catalog_field_id IS NOT NULL"),
        sqlite_where=sa.text("catalog_field_id IS NOT NULL"),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_architecture_objects_single_reference",
            "architecture_objects",
            "(system_id IS NOT NULL)::int + (catalog_object_id IS NOT NULL)::int"
            " + (catalog_field_id IS NOT NULL)::int + (integration_id IS NOT NULL)::int"
            " + (scenario_id IS NOT NULL)::int <= 1",
        )

    op.create_table(
        "information_attributes",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_object_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("data_type", sa.String(length=100), nullable=False, server_default="string"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_key", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_identifier", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("definition", sa.String(length=2000), nullable=True),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_information_attributes_object_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_information_attributes_entity_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_in_state_id"],
            ["architecture_states.id"],
            name="fk_information_attributes_created_state",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "entity_object_id", "name", name="uq_information_attributes_entity_name"
        ),
    )
    op.create_index(
        "ix_information_attributes_entity",
        "information_attributes",
        ["tenant_id", "entity_object_id"],
    )

    op.create_table(
        "architecture_relationships",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source_object_id", sa.Uuid(), nullable=False),
        sa.Column("target_object_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=60), nullable=False),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_architecture_relationships_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_relationships_source_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_relationships_target_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_in_state_id"],
            ["architecture_states.id"],
            name="fk_architecture_relationships_created_state",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "source_object_id",
            "target_object_id",
            "relationship_type",
            name="uq_architecture_relationships_edge",
        ),
        sa.CheckConstraint(
            "source_object_id <> target_object_id",
            name="ck_architecture_relationships_distinct_ends",
        ),
    )
    op.create_index(
        "ix_architecture_relationships_source",
        "architecture_relationships",
        ["tenant_id", "source_object_id"],
    )
    op.create_index(
        "ix_architecture_relationships_target",
        "architecture_relationships",
        ["tenant_id", "target_object_id"],
    )

    op.create_table(
        "architecture_state_members",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("membership", sa.String(length=16), nullable=False, server_default="included"),
        sa.Column("property_overrides", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_architecture_state_members_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_architecture_state_members_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["architecture_states.id"],
            name="fk_architecture_state_members_state",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_state_members_object_tenant",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "state_id", "object_id", name="uq_architecture_state_members_state_object"
        ),
        sa.CheckConstraint(
            "membership IN ('included', 'excluded')",
            name="ck_architecture_state_members_membership",
        ),
    )
    op.create_index(
        "ix_architecture_state_members_state",
        "architecture_state_members",
        ["tenant_id", "state_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_architecture_state_members_state", table_name="architecture_state_members")
    op.drop_table("architecture_state_members")
    op.drop_index(
        "ix_architecture_relationships_target", table_name="architecture_relationships"
    )
    op.drop_index(
        "ix_architecture_relationships_source", table_name="architecture_relationships"
    )
    op.drop_table("architecture_relationships")
    op.drop_index("ix_information_attributes_entity", table_name="information_attributes")
    op.drop_table("information_attributes")

    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "ck_architecture_objects_single_reference",
            "architecture_objects",
            type_="check",
        )

    op.drop_index("uq_architecture_objects_catalog_field", table_name="architecture_objects")
    op.drop_index("uq_architecture_objects_catalog_object", table_name="architecture_objects")

    with op.batch_alter_table("architecture_objects") as batch_op:
        batch_op.drop_constraint(
            "fk_architecture_objects_scenario_tenant", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_architecture_objects_integration_tenant", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_architecture_objects_catalog_field_tenant", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_architecture_objects_catalog_object_tenant", type_="foreignkey"
        )
        batch_op.drop_column("scenario_id")
        batch_op.drop_column("integration_id")
        batch_op.drop_column("catalog_field_id")
        batch_op.drop_column("catalog_object_id")

    with op.batch_alter_table("information_objects") as batch_op:
        batch_op.alter_column("owner", existing_type=sa.String(length=160), nullable=False)
        batch_op.alter_column("authoritative_system_id", existing_type=sa.Uuid(), nullable=False)

    with op.batch_alter_table("scenarios") as batch_op:
        batch_op.drop_constraint("uq_scenarios_id_tenant", type_="unique")

    with op.batch_alter_table("fields") as batch_op:
        batch_op.drop_constraint("uq_fields_id_tenant", type_="unique")
