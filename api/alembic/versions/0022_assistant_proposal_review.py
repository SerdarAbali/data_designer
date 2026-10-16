"""Proposal review: structured unresolved decisions and change-set references.

Revision ID: 0022_assistant_proposal_review
Revises: 0021_assistant_open_code

Additive only:
* ``helper_change_sets.unresolved_details`` — structured, closed decision
  descriptors derived from existing unresolved operations (readable UI);
* ``helper_change_operations.resolution_state`` — ``active`` | ``removed`` so a
  proposed operation can be removed without deleting its row;
* ``assistant_tool_calls.change_set_id`` — the helper change set a proposal tool
  created, so conversations can reference it without duplicating the payload;
* ``assistant_messages.referenced_change_set_ids`` — bounded change-set
  references attached to an assistant message.

No existing helper-action behaviour changes. The proposal hash ignores
``resolution_state`` while it is ``active``, so already-stored hashes stay valid.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0022_assistant_proposal_review"
down_revision: str | None = "0021_assistant_open_code"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "helper_change_sets",
        sa.Column("unresolved_details", json_type, nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "helper_change_operations",
        sa.Column(
            "resolution_state",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "assistant_tool_calls",
        sa.Column("change_set_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "assistant_messages",
        sa.Column(
            "referenced_change_set_ids",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("assistant_messages", "referenced_change_set_ids")
    op.drop_column("assistant_tool_calls", "change_set_id")
    op.drop_column("helper_change_operations", "resolution_state")
    op.drop_column("helper_change_sets", "unresolved_details")
