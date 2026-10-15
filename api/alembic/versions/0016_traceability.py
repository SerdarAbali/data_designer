"""Cross-discipline traceability support and deferred information views.

Adds an index supporting relationship-type traversal on
``architecture_relationships`` and the ownership/stewardship and
classification/sensitivity fields surfaced by the Information workbench.

Revision ID: 0016_traceability
Revises: 0015_integration_designer
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_traceability"
down_revision: str | None = "0015_integration_designer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_architecture_relationships_type",
        "architecture_relationships",
        ["tenant_id", "relationship_type"],
    )
    op.add_column(
        "information_objects",
        sa.Column("steward", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "information_objects",
        sa.Column("sensitivity", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("information_objects", "sensitivity")
    op.drop_column("information_objects", "steward")
    op.drop_index(
        "ix_architecture_relationships_type",
        table_name="architecture_relationships",
    )
