"""Assistant conversation persistence (Slice C).

Revision ID: 0021_assistant_open_code
Revises: 0020_helper_apply_undo

Adds the read-only Architecture Assistant tables: workspace opt-in, conversations,
messages, bounded tool-call summaries, and durable SSE events. It also adds
``workspaces.assistant_enabled`` (default false, opt-in).

These tables store conversation state only. No architecture-domain table is
touched, and no existing helper-action behaviour changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0021_assistant_open_code"
down_revision: str | None = "0020_helper_apply_undo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "assistant_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("active_state_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("state_type", sa.String(length=32), nullable=True),
        sa.Column("discipline", sa.String(length=32), nullable=True),
        sa.Column("workbench_view", sa.String(length=32), nullable=True),
        sa.Column("selection_ids", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("opencode_session_id", sa.String(length=120), nullable=True, unique=True),
        sa.Column("opencode_version", sa.String(length=32), nullable=True),
        sa.Column("scope_hash", sa.String(length=64), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_assistant_conversations_scope",
        "assistant_conversations",
        ["tenant_id", "workspace_id", "user_id"],
    )
    op.create_index(
        "ix_assistant_conversations_state",
        "assistant_conversations",
        ["tenant_id", "active_state_id"],
    )

    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="complete"),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_assistant_messages_sequence"
        ),
    )
    op.create_index(
        "ix_assistant_messages_conversation", "assistant_messages", ["conversation_id", "sequence"]
    )

    op.create_table(
        "assistant_tool_calls",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("assistant_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("call_id", sa.String(length=120), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("arguments_summary", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result_summary", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "conversation_id", "call_id", name="uq_assistant_tool_calls_call_id"
        ),
    )
    op.create_index(
        "ix_assistant_tool_calls_conversation", "assistant_tool_calls", ["conversation_id"]
    )

    op.create_table(
        "assistant_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("payload", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_assistant_events_sequence"
        ),
    )
    op.create_index(
        "ix_assistant_events_conversation", "assistant_events", ["conversation_id", "sequence"]
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_events_conversation", table_name="assistant_events")
    op.drop_table("assistant_events")
    op.drop_index("ix_assistant_tool_calls_conversation", table_name="assistant_tool_calls")
    op.drop_table("assistant_tool_calls")
    op.drop_index("ix_assistant_messages_conversation", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_conversations_state", table_name="assistant_conversations")
    op.drop_index("ix_assistant_conversations_scope", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
    op.drop_column("workspaces", "assistant_enabled")
