"""Helper-action persistence: change sets, operations, and audit events.

Revision ID: 0019_helper_actions
Revises: 0018_demo_workspaces
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0019_helper_actions"
down_revision: str | None = "0018_demo_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "helper_change_sets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("state_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("state_type", sa.String(length=32), nullable=True),
        sa.Column("helper_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("summary", sa.String(length=2000), nullable=True),
        sa.Column("input_summary", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("assumptions", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "unresolved_decisions", json_type, nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("warnings", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("reused_objects", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("proposed_objects", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "expected_traceability", json_type, nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("validation_summary", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("proposal_hash", sa.String(length=64), nullable=True),
        sa.Column("proposed_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_hash", sa.String(length=64), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["state_id"], ["architecture_states.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["proposed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_helper_change_sets_workspace", "helper_change_sets", ["tenant_id", "workspace_id"]
    )
    op.create_index("ix_helper_change_sets_state", "helper_change_sets", ["tenant_id", "state_id"])

    op.create_table(
        "helper_change_operations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("change_set_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("operation_id", sa.String(length=80), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("domain_action", sa.String(length=60), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("temporary_id", sa.String(length=80), nullable=True),
        sa.Column("before_value", json_type, nullable=True),
        sa.Column("proposed_value", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("depends_on", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "validation_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("validation_issues", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("explanation", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["change_set_id"], ["helper_change_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "change_set_id", "operation_id", name="uq_helper_change_operations_operation_id"
        ),
    )
    op.create_index(
        "ix_helper_change_operations_change_set",
        "helper_change_operations",
        ["change_set_id", "ordinal"],
    )

    op.create_table(
        "helper_audit_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("change_set_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("state_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("summary", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "affected_object_ids", json_type, nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "affected_contract_ids", json_type, nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["change_set_id"], ["helper_change_sets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_helper_audit_events_change_set",
        "helper_audit_events",
        ["tenant_id", "change_set_id"],
    )
    op.create_index(
        "ix_helper_audit_events_workspace",
        "helper_audit_events",
        ["tenant_id", "workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_helper_audit_events_workspace", table_name="helper_audit_events")
    op.drop_index("ix_helper_audit_events_change_set", table_name="helper_audit_events")
    op.drop_table("helper_audit_events")
    op.drop_index(
        "ix_helper_change_operations_change_set", table_name="helper_change_operations"
    )
    op.drop_table("helper_change_operations")
    op.drop_index("ix_helper_change_sets_state", table_name="helper_change_sets")
    op.drop_index("ix_helper_change_sets_workspace", table_name="helper_change_sets")
    op.drop_table("helper_change_sets")
