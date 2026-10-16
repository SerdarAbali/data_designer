"""Helper-action apply/undo ownership columns.

Revision ID: 0020_helper_apply_undo
Revises: 0019_helper_actions

Slice 4 adds transactional apply/undo. These columns record the apply result,
per-operation ownership, post-apply fingerprints, and undo status so that undo
can remove only change-set-owned rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0020_helper_apply_undo"
down_revision: str | None = "0019_helper_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "helper_change_sets",
        sa.Column("apply_summary", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "helper_change_sets",
        sa.Column("undo_summary", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "helper_change_sets",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "helper_change_sets",
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "helper_change_operations",
        sa.Column("applied_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "helper_change_operations",
        sa.Column(
            "apply_status", sa.String(length=32), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "helper_change_operations",
        sa.Column("ownership", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "helper_change_operations",
        sa.Column("post_fingerprint", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "helper_change_operations",
        sa.Column(
            "undo_status", sa.String(length=32), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "helper_change_operations",
        sa.Column("undo_conflict", json_type, nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("helper_change_operations", "undo_conflict")
    op.drop_column("helper_change_operations", "undo_status")
    op.drop_column("helper_change_operations", "post_fingerprint")
    op.drop_column("helper_change_operations", "ownership")
    op.drop_column("helper_change_operations", "apply_status")
    op.drop_column("helper_change_operations", "applied_id")
    op.drop_column("helper_change_sets", "undone_at")
    op.drop_column("helper_change_sets", "applied_at")
    op.drop_column("helper_change_sets", "undo_summary")
    op.drop_column("helper_change_sets", "apply_summary")
