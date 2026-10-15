"""Add canonical architecture object identities and thin typed records.

Revision ID: 0010_shared_architecture_objects
Revises: 0009_architecture_states
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_shared_architecture_objects"
down_revision: str | None = "0009_architecture_states"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_typed_table(name: str, extra_columns: tuple[sa.Column, ...] = ()) -> None:
    op.create_table(
        name,
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        *extra_columns,
        sa.PrimaryKeyConstraint("object_id"),
        sa.ForeignKeyConstraint(
            ["object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            ondelete="CASCADE",
        ),
    )


def upgrade() -> None:
    op.create_table(
        "architecture_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_architecture_objects_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["system_id", "tenant_id"],
            ["systems.id", "systems.tenant_id"],
            name="fk_architecture_objects_system_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_architecture_objects_id_tenant"),
    )
    op.create_index(
        "uq_architecture_objects_system",
        "architecture_objects",
        ["tenant_id", "system_id"],
        unique=True,
        postgresql_where=sa.text("system_id IS NOT NULL"),
        sqlite_where=sa.text("system_id IS NOT NULL"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO architecture_objects (id, tenant_id, kind, system_id)
            SELECT id, tenant_id, 'system', id FROM systems
            """
        )
    )

    _create_typed_table("business_requirements")
    _create_typed_table("business_capabilities")
    _create_typed_table(
        "information_objects",
        (
            sa.Column("owner", sa.String(length=160), nullable=False),
            sa.Column("authoritative_system_id", sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint(
                ["authoritative_system_id", "tenant_id"],
                ["systems.id", "systems.tenant_id"],
                name="fk_information_objects_authoritative_system_tenant",
                ondelete="RESTRICT",
            ),
        ),
    )
    _create_typed_table("solution_boundaries")
    _create_typed_table("solution_components")
    _create_typed_table("architecture_interfaces")


def downgrade() -> None:
    op.drop_table("architecture_interfaces")
    op.drop_table("solution_components")
    op.drop_table("solution_boundaries")
    op.drop_table("information_objects")
    op.drop_table("business_capabilities")
    op.drop_table("business_requirements")
    op.drop_index("uq_architecture_objects_system", table_name="architecture_objects")
    op.drop_table("architecture_objects")
