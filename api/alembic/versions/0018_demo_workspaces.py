"""Add demo workspace metadata (preset, version, timestamp, generated assets).

Revision ID: 0018_demo_workspaces
Revises: 0017_integration_integrity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0018_demo_workspaces"
down_revision: str | None = "0017_integration_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("demo_preset", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("demo_version", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column("demo_generated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("demo_assets", json_type, nullable=False, server_default=sa.text("'{}'"))
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("demo_assets")
        batch_op.drop_column("demo_generated_at")
        batch_op.drop_column("demo_version")
        batch_op.drop_column("demo_preset")
