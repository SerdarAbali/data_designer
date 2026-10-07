"""Add indexes for architecture analysis and dependency lookup."""

from alembic import op

revision = "0004_architecture_indexes"
down_revision = "0003_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_integration_field_refs_target",
        "integration_field_refs",
        ["tenant_id", "direction", "object_id", "field_id", "integration_id"],
    )
    op.create_index(
        "ix_integration_dependencies_upstream",
        "integration_dependencies",
        ["tenant_id", "upstream_integration_id", "downstream_integration_id"],
    )
    op.create_index(
        "ix_integration_dependencies_downstream",
        "integration_dependencies",
        ["tenant_id", "downstream_integration_id", "upstream_integration_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_dependencies_downstream",
        table_name="integration_dependencies",
    )
    op.drop_index(
        "ix_integration_dependencies_upstream",
        table_name="integration_dependencies",
    )
    op.drop_index(
        "ix_integration_field_refs_target",
        table_name="integration_field_refs",
    )
