"""Add request/response mapping support."""

import sqlalchemy as sa

from alembic import op
from app.models.integration import json_type

revision = "0005_bidirectional_mappings"
down_revision = "0004_architecture_indexes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column(
            "response_graph",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.execute(
        "UPDATE integrations SET response_graph = "
        "'{\"version\": 1, \"nodes\": [], \"edges\": []}'"
    )
    op.alter_column("integrations", "response_graph", server_default=None)
    op.add_column(
        "integrations",
        sa.Column(
            "interaction_type",
            sa.String(length=32),
            nullable=False,
            server_default="ONE_WAY",
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_integrations_response_graph_object",
            "integrations",
            "jsonb_typeof(response_graph) = 'object'",
        )
    op.create_check_constraint(
        "ck_integrations_interaction_type",
        "integrations",
        "interaction_type IN ('ONE_WAY', 'REQUEST_RESPONSE', 'ASYNC_CALLBACK')",
    )
    op.drop_constraint("ck_field_ref_direction", "integration_field_refs", type_="check")
    op.alter_column(
        "integration_field_refs",
        "direction",
        existing_type=sa.String(length=10),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_field_ref_direction",
        "integration_field_refs",
        "direction IN ('source', 'target', 'response_source', 'response_target')",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM integration_field_refs "
        "WHERE direction IN ('response_source', 'response_target')"
    )
    op.drop_constraint("ck_field_ref_direction", "integration_field_refs", type_="check")
    op.alter_column(
        "integration_field_refs",
        "direction",
        existing_type=sa.String(length=16),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_field_ref_direction",
        "integration_field_refs",
        "direction IN ('source', 'target')",
    )
    op.drop_constraint("ck_integrations_interaction_type", "integrations", type_="check")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "ck_integrations_response_graph_object", "integrations", type_="check"
        )
    op.drop_column("integrations", "interaction_type")
    op.drop_column("integrations", "response_graph")
