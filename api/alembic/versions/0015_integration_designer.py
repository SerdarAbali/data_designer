"""Add integration designer properties to the integrations table.

Revision ID: 0015_integration_designer
Revises: 0014_enterprise_workbench
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0015_integration_designer"
down_revision: str | None = "0014_enterprise_workbench"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column("pattern", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column(
            "implementation_status",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
    )
    op.add_column(
        "integrations",
        sa.Column("producer_interface_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column("consumer_interface_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column("specification", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_check_constraint(
        "ck_integrations_implementation_status",
        "integrations",
        "implementation_status IN ('draft', 'in_progress', 'built', 'verified')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_integrations_implementation_status", "integrations", type_="check"
    )
    op.drop_column("integrations", "specification")
    op.drop_column("integrations", "consumer_interface_id")
    op.drop_column("integrations", "producer_interface_id")
    op.drop_column("integrations", "implementation_status")
    op.drop_column("integrations", "pattern")
