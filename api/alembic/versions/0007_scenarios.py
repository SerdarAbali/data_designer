"""Create design-time scenarios.

Revision ID: 0007_scenarios
Revises: 0006_error_response_mapping
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_scenarios"
down_revision: str | None = "0006_error_response_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("scope_integration_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("document", json_type, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("revision >= 1", name="ck_scenarios_revision_positive"),
        sa.CheckConstraint(
            "category IN ('happy_path', 'alternative', 'error')",
            name="ck_scenarios_category",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_scenarios_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scope_integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_scenarios_scope_integration",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_scenarios_document_object",
            "scenarios",
            "jsonb_typeof(document) = 'object'",
        )
    op.create_index(
        "uq_scenarios_active_name",
        "scenarios",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_scenarios_scope", "scenarios", ["tenant_id", "scope_integration_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_scenarios_scope", table_name="scenarios")
    op.drop_index("uq_scenarios_active_name", table_name="scenarios")
    op.drop_table("scenarios")
