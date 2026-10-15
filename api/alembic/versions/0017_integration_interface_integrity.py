"""Add referential integrity for integration producer/consumer interface links.

Revision ID: 0017_integration_interface_integrity
Revises: 0016_traceability
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_integration_interface_integrity"
down_revision: str | None = "0016_traceability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop any pre-existing dangling references before enforcing the constraints
    # so the migration is safe against data written before integrity existed.
    op.execute(
        """
        UPDATE integrations
        SET producer_interface_id = NULL
        WHERE producer_interface_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM architecture_interfaces ai
              WHERE ai.object_id = integrations.producer_interface_id
                AND ai.tenant_id = integrations.tenant_id
          )
        """
    )
    op.execute(
        """
        UPDATE integrations
        SET consumer_interface_id = NULL
        WHERE consumer_interface_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM architecture_interfaces ai
              WHERE ai.object_id = integrations.consumer_interface_id
                AND ai.tenant_id = integrations.tenant_id
          )
        """
    )
    op.create_foreign_key(
        "fk_integrations_producer_interface",
        "integrations",
        "architecture_interfaces",
        ["producer_interface_id", "tenant_id"],
        ["object_id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_integrations_consumer_interface",
        "integrations",
        "architecture_interfaces",
        ["consumer_interface_id", "tenant_id"],
        ["object_id", "tenant_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_integrations_consumer_interface", "integrations", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_integrations_producer_interface", "integrations", type_="foreignkey"
    )
