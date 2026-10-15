"""Add solution designer tables and component/interface columns.

Revision ID: 0013_solution_designer
Revises: 0012_information_modeler
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0013_solution_designer"
down_revision: str | None = "0012_information_modeler"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("solution_members") as batch_op:
        batch_op.add_column(sa.Column("created_in_state_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_solution_members_created_state",
            "architecture_states",
            ["created_in_state_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("solution_components") as batch_op:
        batch_op.add_column(sa.Column("solution_object_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("parent_component_object_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("responsibility", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("component_type", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("technology", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("created_in_state_id", sa.Uuid(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_solution_components_object_tenant", ["object_id", "tenant_id"]
        )
        batch_op.create_foreign_key(
            "fk_solution_components_solution_tenant",
            "solution_boundaries",
            ["solution_object_id", "tenant_id"],
            ["object_id", "tenant_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_solution_components_created_state",
            "architecture_states",
            ["created_in_state_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_solution_components_solution",
        "solution_components",
        ["tenant_id", "solution_object_id"],
    )

    with op.batch_alter_table("architecture_interfaces") as batch_op:
        batch_op.add_column(sa.Column("component_object_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "direction",
                sa.String(length=16),
                nullable=False,
                server_default="provided",
            )
        )
        batch_op.add_column(sa.Column("interface_kind", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("protocol", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("technology", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("created_in_state_id", sa.Uuid(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_architecture_interfaces_object_tenant", ["object_id", "tenant_id"]
        )
        batch_op.create_foreign_key(
            "fk_architecture_interfaces_component_tenant",
            "architecture_objects",
            ["component_object_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_architecture_interfaces_created_state",
            "architecture_states",
            ["created_in_state_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_architecture_interfaces_component",
        "architecture_interfaces",
        ["tenant_id", "component_object_id"],
    )

    op.create_table(
        "interface_operations",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("interface_object_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column(
            "operation_kind", sa.String(length=16), nullable=False, server_default="operation"
        ),
        sa.Column("request_object_id", sa.Uuid(), nullable=True),
        sa.Column("response_object_id", sa.Uuid(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_interface_operations_object_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interface_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_interface_operations_interface_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_in_state_id"],
            ["architecture_states.id"],
            name="fk_interface_operations_created_state",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "interface_object_id", "name", name="uq_interface_operations_interface_name"
        ),
    )
    op.create_index(
        "ix_interface_operations_interface",
        "interface_operations",
        ["tenant_id", "interface_object_id"],
    )

    op.create_table(
        "data_repositories",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("solution_object_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("owner", sa.String(length=160), nullable=True),
        sa.Column("repository_type", sa.String(length=40), nullable=True),
        sa.Column("technology", sa.String(length=160), nullable=True),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_data_repositories_object_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_data_repositories_solution_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_in_state_id"],
            ["architecture_states.id"],
            name="fk_data_repositories_created_state",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_data_repositories_solution",
        "data_repositories",
        ["tenant_id", "solution_object_id"],
    )

    op.create_table(
        "deployment_nodes",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("solution_object_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("technology", sa.String(length=160), nullable=True),
        sa.Column("environment", sa.String(length=40), nullable=True),
        sa.Column("hosting", sa.String(length=40), nullable=True),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_deployment_nodes_object_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_deployment_nodes_solution_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_in_state_id"],
            ["architecture_states.id"],
            name="fk_deployment_nodes_created_state",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_deployment_nodes_solution",
        "deployment_nodes",
        ["tenant_id", "solution_object_id"],
    )

    op.create_table(
        "trust_boundaries",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("solution_object_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("security_level", sa.String(length=40), nullable=True),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_trust_boundaries_object_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_trust_boundaries_solution_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_in_state_id"],
            ["architecture_states.id"],
            name="fk_trust_boundaries_created_state",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_trust_boundaries_solution",
        "trust_boundaries",
        ["tenant_id", "solution_object_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trust_boundaries_solution", table_name="trust_boundaries")
    op.drop_table("trust_boundaries")
    op.drop_index("ix_deployment_nodes_solution", table_name="deployment_nodes")
    op.drop_table("deployment_nodes")
    op.drop_index("ix_data_repositories_solution", table_name="data_repositories")
    op.drop_table("data_repositories")
    op.drop_index("ix_interface_operations_interface", table_name="interface_operations")
    op.drop_table("interface_operations")

    op.drop_index(
        "ix_architecture_interfaces_component", table_name="architecture_interfaces"
    )
    with op.batch_alter_table("architecture_interfaces") as batch_op:
        batch_op.drop_constraint(
            "fk_architecture_interfaces_created_state", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_architecture_interfaces_component_tenant", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "uq_architecture_interfaces_object_tenant", type_="unique"
        )
        batch_op.drop_column("created_in_state_id")
        batch_op.drop_column("technology")
        batch_op.drop_column("protocol")
        batch_op.drop_column("interface_kind")
        batch_op.drop_column("direction")
        batch_op.drop_column("component_object_id")

    op.drop_index("ix_solution_components_solution", table_name="solution_components")
    with op.batch_alter_table("solution_components") as batch_op:
        batch_op.drop_constraint("fk_solution_components_created_state", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_solution_components_solution_tenant", type_="foreignkey"
        )
        batch_op.drop_constraint("uq_solution_components_object_tenant", type_="unique")
        batch_op.drop_column("created_in_state_id")
        batch_op.drop_column("technology")
        batch_op.drop_column("component_type")
        batch_op.drop_column("responsibility")
        batch_op.drop_column("parent_component_object_id")
        batch_op.drop_column("solution_object_id")

    with op.batch_alter_table("solution_members") as batch_op:
        batch_op.drop_constraint("fk_solution_members_created_state", type_="foreignkey")
        batch_op.drop_column("created_in_state_id")
