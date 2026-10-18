"""Explicit single mediator on Integration Contracts.

Revision ID: 0025_contract_mediator
Revises: 0024_architecture_facts

Additive only. Adds nullable ``mediator_system_id`` / ``mediator_responsibility``
to ``integrations`` plus the composite tenant-scoped foreign key, an index and a
database check that a mediator is never the business source or target. ``NULL``
means "no explicitly modelled mediator" and is never backfilled; existing rows
stay valid and unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_contract_mediator"
down_revision: str | None = "0024_architecture_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MEDIATOR_DISTINCT = (
    "mediator_system_id IS NULL OR ("
    "mediator_system_id != source_system_id "
    "AND mediator_system_id != target_system_id)"
)


def upgrade() -> None:
    with op.batch_alter_table("integrations") as batch_op:
        batch_op.add_column(
            sa.Column("mediator_system_id", sa.Uuid(as_uuid=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("mediator_responsibility", sa.String(length=300), nullable=True)
        )
    # SQLite cannot ALTER TABLE to add a constraint to an existing table, so the
    # composite foreign key and the check are only created on PostgreSQL. The ORM
    # model declares both, so dialect-created schemas enforce them everywhere.
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_integrations_mediator_system",
            "integrations",
            "systems",
            ["mediator_system_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "ck_integrations_mediator_distinct", "integrations", MEDIATOR_DISTINCT
        )
    op.create_index(
        "ix_integrations_mediator_system",
        "integrations",
        ["tenant_id", "mediator_system_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_integrations_mediator_system", table_name="integrations")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "ck_integrations_mediator_distinct", "integrations", type_="check"
        )
        op.drop_constraint(
            "fk_integrations_mediator_system", "integrations", type_="foreignkey"
        )
    with op.batch_alter_table("integrations") as batch_op:
        batch_op.drop_column("mediator_responsibility")
        batch_op.drop_column("mediator_system_id")
