"""Add workspace support with multi-tenant sessions and soft-deletion.

Revision ID: 0008_workspaces
Revises: 0007_scenarios
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_workspaces"
down_revision: str | None = "0007_scenarios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("description", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_tenants_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.add_column(sa.Column("active_tenant_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_auth_sessions_active_tenant_id",
            "tenants",
            ["active_tenant_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.drop_constraint("fk_auth_sessions_active_tenant_id", type_="foreignkey")
        batch_op.drop_column("active_tenant_id")

    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_constraint("fk_tenants_owner_id_users", type_="foreignkey")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("owner_id")
        batch_op.drop_column("description")

