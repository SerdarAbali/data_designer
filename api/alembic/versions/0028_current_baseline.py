"""Current baseline status and lock metadata.

Revision ID: 0028_current_baseline
Revises: 0027_solution_integrations

Additive only. Adds the Current-baseline lifecycle to ``architecture_states``:
``baseline_status`` (``draft`` or ``locked``, ``NULL`` on Candidate/Target),
plus the server-controlled ``baseline_locked_at`` and ``baseline_locked_by``.

Every state that already exists with ``state_type = 'current'`` becomes
``locked``, which preserves exactly the read-only protection it had before this
slice. Candidate and Target rows keep ``NULL`` because the field carries no
meaning for them. Nothing else is rewritten and no record is deleted.

The check constraint and the foreign key are added on PostgreSQL only: SQLite
cannot ``ALTER TABLE ... ADD CONSTRAINT``. The model still declares both, so a
freshly created database enforces them on either dialect.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_current_baseline"
down_revision: str | None = "0027_solution_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BASELINE_IN = "('draft', 'locked')"


def upgrade() -> None:
    with op.batch_alter_table("architecture_states") as batch_op:
        batch_op.add_column(
            sa.Column("baseline_status", sa.String(length=16), nullable=True)
        )
        batch_op.add_column(
            sa.Column("baseline_locked_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("baseline_locked_by", sa.Uuid(as_uuid=True), nullable=True)
        )

    # Existing Current states were read-only before the lifecycle existed, so
    # they migrate as locked. Candidate and Target rows are left NULL.
    op.execute(
        "UPDATE architecture_states SET baseline_status = 'locked' "
        "WHERE state_type = 'current'"
    )

    op.create_index(
        "ix_architecture_states_workspace_type",
        "architecture_states",
        ["workspace_id", "state_type"],
    )

    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_check_constraint(
        "ck_architecture_states_baseline_status",
        "architecture_states",
        f"baseline_status IN {BASELINE_IN}",
    )
    op.create_foreign_key(
        "fk_architecture_states_baseline_locked_by",
        "architecture_states",
        "users",
        ["baseline_locked_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "fk_architecture_states_baseline_locked_by",
            "architecture_states",
            type_="foreignkey",
        )
        op.drop_constraint(
            "ck_architecture_states_baseline_status",
            "architecture_states",
            type_="check",
        )

    op.drop_index(
        "ix_architecture_states_workspace_type", table_name="architecture_states"
    )

    with op.batch_alter_table("architecture_states") as batch_op:
        batch_op.drop_column("baseline_locked_by")
        batch_op.drop_column("baseline_locked_at")
        batch_op.drop_column("baseline_status")
