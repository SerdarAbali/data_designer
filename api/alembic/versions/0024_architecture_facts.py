"""Generic lifecycle, operational-status and environment-scope facts.

Revision ID: 0024_architecture_facts
Revises: 0023_assistant_model_settings

Additive only. Adds nullable, checked fact columns to ``systems`` and
``integrations`` plus a bounded ``integration_state_overrides`` table that
carries Candidate/Target deltas for contracts. Existing rows stay valid: every
new column is nullable and ``NULL`` means "not specified", never a concrete
status. Nothing is backfilled and no existing value is rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_architecture_facts"
down_revision: str | None = "0023_assistant_model_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIFECYCLE_IN = "('strategic', 'planned', 'active', 'transitional', 'legacy', 'retiring', 'retired')"
OPERATIONAL_IN = (
    "('unknown', 'proposed', 'tested', 'live', 'degraded', 'suspended',"
    " 'retiring', 'decommissioned')"
)
ENVIRONMENT_IN = (
    "('unknown', 'development', 'test', 'sandbox', 'staging', 'production', 'mixed')"
)


def _fact_columns() -> list[sa.Column]:
    return [
        sa.Column("lifecycle_stage", sa.String(length=32), nullable=True),
        sa.Column("operational_status", sa.String(length=32), nullable=True),
        sa.Column("environment_scope", sa.String(length=32), nullable=True),
    ]


def _create_fact_checks(table: str, prefix: str) -> None:
    # SQLite cannot ALTER TABLE to add a constraint, so the check constraints on
    # existing tables are only created on PostgreSQL. The new table below defines
    # its checks inline, so both dialects enforce them there.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_check_constraint(
        f"{prefix}_lifecycle_stage", table, f"lifecycle_stage IN {LIFECYCLE_IN}"
    )
    op.create_check_constraint(
        f"{prefix}_operational_status", table, f"operational_status IN {OPERATIONAL_IN}"
    )
    op.create_check_constraint(
        f"{prefix}_environment_scope", table, f"environment_scope IN {ENVIRONMENT_IN}"
    )


def upgrade() -> None:
    with op.batch_alter_table("systems") as batch_op:
        for column in _fact_columns():
            batch_op.add_column(column)
    _create_fact_checks("systems", "ck_systems")

    with op.batch_alter_table("integrations") as batch_op:
        for column in _fact_columns():
            batch_op.add_column(column)
    _create_fact_checks("integrations", "ck_integrations")

    op.create_table(
        "integration_state_overrides",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "state_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("architecture_states.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("integration_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=32), nullable=True),
        sa.Column("operational_status", sa.String(length=32), nullable=True),
        sa.Column("environment_scope", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_integration_state_overrides_integration",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "state_id",
            "integration_id",
            name="uq_integration_state_overrides_state_integration",
        ),
        sa.CheckConstraint(
            f"lifecycle_stage IN {LIFECYCLE_IN}",
            name="ck_integration_state_overrides_lifecycle_stage",
        ),
        sa.CheckConstraint(
            f"operational_status IN {OPERATIONAL_IN}",
            name="ck_integration_state_overrides_operational_status",
        ),
        sa.CheckConstraint(
            f"environment_scope IN {ENVIRONMENT_IN}",
            name="ck_integration_state_overrides_environment_scope",
        ),
    )


def downgrade() -> None:
    op.drop_table("integration_state_overrides")

    if op.get_bind().dialect.name == "postgresql":
        for prefix in ("ck_systems", "ck_integrations"):
            op.drop_constraint(f"{prefix}_lifecycle_stage", prefix[3:], type_="check")
            op.drop_constraint(f"{prefix}_operational_status", prefix[3:], type_="check")
            op.drop_constraint(f"{prefix}_environment_scope", prefix[3:], type_="check")

    with op.batch_alter_table("integrations") as batch_op:
        batch_op.drop_column("environment_scope")
        batch_op.drop_column("operational_status")
        batch_op.drop_column("lifecycle_stage")

    with op.batch_alter_table("systems") as batch_op:
        batch_op.drop_column("environment_scope")
        batch_op.drop_column("operational_status")
        batch_op.drop_column("lifecycle_stage")
