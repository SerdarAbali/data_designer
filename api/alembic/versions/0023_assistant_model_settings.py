"""Owner-only assistant provider/model settings (tenant scoped).

Revision ID: 0023_assistant_model_settings
Revises: 0022_assistant_proposal_review

Additive. Stores non-secret provider/model configuration and the observed
credential *status* only. Provider credentials are never persisted here; they
remain in server-side environment/secret material.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_assistant_model_settings"
down_revision: str | None = "0022_assistant_proposal_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_model_settings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("model_variant", sa.String(length=40), nullable=True),
        sa.Column(
            "reasoning_effort", sa.String(length=20), nullable=False, server_default="medium"
        ),
        sa.Column("max_input_tokens", sa.Integer(), nullable=False, server_default="16000"),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="4000"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("step_limit", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "privacy_classification",
            sa.String(length=20),
            nullable=False,
            server_default="internal",
        ),
        sa.Column(
            "trains_on_data", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "approved_for_sensitive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("fallback_provider", sa.String(length=80), nullable=True),
        sa.Column("fallback_model_id", sa.String(length=120), nullable=True),
        sa.Column(
            "fallback_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "credential_status", sa.String(length=20), nullable=False, server_default="missing"
        ),
        sa.Column("credential_last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_assistant_model_settings_tenant"),
    )


def downgrade() -> None:
    op.drop_table("assistant_model_settings")
