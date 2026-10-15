"""Add enterprise workbench tables (goals, processes, principles, roles).

Revision ID: 0014_enterprise_workbench
Revises: 0013_solution_designer
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0014_enterprise_workbench"
down_revision: str | None = "0013_solution_designer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def _object_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["object_id", "tenant_id"],
        ["architecture_objects.id", "architecture_objects.tenant_id"],
        name=name,
        ondelete="CASCADE",
    )


def _created_state_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["created_in_state_id"],
        ["architecture_states.id"],
        name=name,
        ondelete="SET NULL",
    )


def upgrade() -> None:
    op.create_table(
        "business_goals",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("owner", sa.String(length=160), nullable=True),
        sa.Column("outcome_metric", sa.String(length=500), nullable=True),
        sa.Column("horizon", sa.String(length=60), nullable=True),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _object_fk("fk_business_goals_object_tenant"),
        _created_state_fk("fk_business_goals_created_state"),
    )
    op.create_index("ix_business_goals_tenant", "business_goals", ["tenant_id"])

    op.create_table(
        "business_processes",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("owner", sa.String(length=160), nullable=True),
        sa.Column("process_type", sa.String(length=40), nullable=True),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _object_fk("fk_business_processes_object_tenant"),
        _created_state_fk("fk_business_processes_created_state"),
    )
    op.create_index("ix_business_processes_tenant", "business_processes", ["tenant_id"])

    op.create_table(
        "architecture_principles",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("principle_type", sa.String(length=40), nullable=True),
        sa.Column("rationale", sa.String(length=2000), nullable=True),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _object_fk("fk_architecture_principles_object_tenant"),
        _created_state_fk("fk_architecture_principles_created_state"),
    )
    op.create_index("ix_architecture_principles_tenant", "architecture_principles", ["tenant_id"])

    op.create_table(
        "organization_roles",
        sa.Column("object_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("role_type", sa.String(length=40), nullable=True),
        sa.Column("properties", json_type, nullable=False),
        sa.Column("created_in_state_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _object_fk("fk_organization_roles_object_tenant"),
        _created_state_fk("fk_organization_roles_created_state"),
    )
    op.create_index("ix_organization_roles_tenant", "organization_roles", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_organization_roles_tenant", table_name="organization_roles")
    op.drop_table("organization_roles")
    op.drop_index("ix_architecture_principles_tenant", table_name="architecture_principles")
    op.drop_table("architecture_principles")
    op.drop_index("ix_business_processes_tenant", table_name="business_processes")
    op.drop_table("business_processes")
    op.drop_index("ix_business_goals_tenant", table_name="business_goals")
    op.drop_table("business_goals")
