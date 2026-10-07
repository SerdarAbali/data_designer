"""Persist a separate error-response schema and graph."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.integration import json_type

revision: str = "0006_error_response_mapping"
down_revision: str | None = "0005_bidirectional_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_GRAPH = '{"version": 1, "nodes": [], "edges": []}'


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column(
            "error_response_graph",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "integrations",
        sa.Column("error_response_object_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        "UPDATE integrations SET error_response_graph = "
        f"'{EMPTY_GRAPH}'"
    )
    with op.batch_alter_table("integrations") as batch_op:
        batch_op.alter_column(
            "error_response_graph",
            existing_type=json_type,
            existing_nullable=False,
            server_default=None,
        )
        batch_op.create_foreign_key(
            "fk_integrations_error_response_object",
            "objects",
            ["error_response_object_id", "target_system_id", "tenant_id"],
            ["id", "system_id", "tenant_id"],
            ondelete="RESTRICT",
        )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_integrations_error_response_graph_object",
            "integrations",
            "jsonb_typeof(error_response_graph) = 'object'",
        )
    with op.batch_alter_table("integration_field_refs") as batch_op:
        batch_op.drop_constraint("ck_field_ref_direction", type_="check")
        batch_op.alter_column(
            "direction",
            existing_type=sa.String(length=16),
            type_=sa.String(length=24),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_field_ref_direction",
            "direction IN ('source', 'target', 'response_source', 'response_target', "
            "'error_response_source', 'error_response_target')",
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM integration_field_refs "
        "WHERE direction IN ('error_response_source', 'error_response_target')"
    )
    with op.batch_alter_table("integration_field_refs") as batch_op:
        batch_op.drop_constraint("ck_field_ref_direction", type_="check")
        batch_op.alter_column(
            "direction",
            existing_type=sa.String(length=24),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_field_ref_direction",
            "direction IN ('source', 'target', 'response_source', 'response_target')",
        )
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "ck_integrations_error_response_graph_object",
            "integrations",
            type_="check",
        )
    with op.batch_alter_table("integrations") as batch_op:
        batch_op.drop_constraint(
            "fk_integrations_error_response_object",
            type_="foreignkey",
        )
        batch_op.drop_column("error_response_object_id")
        batch_op.drop_column("error_response_graph")
