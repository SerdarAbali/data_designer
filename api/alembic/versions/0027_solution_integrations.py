"""Solution Boundary to Integration Contract associations.

Revision ID: 0027_solution_integrations
Revises: 0026_architecture_evidence

Additive only. Creates ``solution_integrations``: an authoritative, state-aware
association between an existing Solution Boundary and an existing Contract, with
an approved role. Contract ownership cannot be inferred from source/target system
membership, so this is an explicit statement rather than a derived one.

Two partial unique indexes enforce "one association per (solution, contract) per
state scope": a plain unique constraint would allow duplicate canonical rows
because ``NULL`` is never equal to ``NULL``. Existing data is untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_solution_integrations"
down_revision: str | None = "0026_architecture_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_IN = "('owned', 'participating', 'dependency')"


def upgrade() -> None:
    op.create_table(
        "solution_integrations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("solution_object_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("integration_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "created_in_state_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("architecture_states.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Real, tenant-scoped foreign keys. RESTRICT is deliberate: removing a
        # Contract or a Boundary must never silently drop its associations.
        sa.ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_solution_integrations_solution_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_solution_integrations_integration_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"role IN {ROLE_IN}", name="ck_solution_integrations_role"),
    )

    op.create_index(
        "uq_solution_integrations_canonical",
        "solution_integrations",
        ["tenant_id", "solution_object_id", "integration_id"],
        unique=True,
        postgresql_where=sa.text("created_in_state_id IS NULL"),
        sqlite_where=sa.text("created_in_state_id IS NULL"),
    )
    op.create_index(
        "uq_solution_integrations_state",
        "solution_integrations",
        ["tenant_id", "solution_object_id", "integration_id", "created_in_state_id"],
        unique=True,
        postgresql_where=sa.text("created_in_state_id IS NOT NULL"),
        sqlite_where=sa.text("created_in_state_id IS NOT NULL"),
    )
    op.create_index(
        "ix_solution_integrations_solution",
        "solution_integrations",
        ["tenant_id", "solution_object_id"],
    )
    op.create_index(
        "ix_solution_integrations_integration",
        "solution_integrations",
        ["tenant_id", "integration_id"],
    )


def downgrade() -> None:
    for name in (
        "ix_solution_integrations_integration",
        "ix_solution_integrations_solution",
        "uq_solution_integrations_state",
        "uq_solution_integrations_canonical",
    ):
        op.drop_index(name, table_name="solution_integrations")
    op.drop_table("solution_integrations")
