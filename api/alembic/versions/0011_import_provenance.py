"""Add import provenance, external identifiers, and solution membership.

Revision ID: 0011_import_provenance
Revises: 0010_shared_architecture_objects
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0011_import_provenance"
down_revision: str | None = "0010_shared_architecture_objects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("systems") as batch_op:
        batch_op.add_column(sa.Column("external_identifier", sa.String(length=255), nullable=True))
    op.create_index(
        "uq_systems_active_external_id",
        "systems",
        ["tenant_id", "external_identifier"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND external_identifier IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND external_identifier IS NOT NULL"),
    )

    with op.batch_alter_table("information_objects") as batch_op:
        batch_op.add_column(sa.Column("external_identifier", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("classification", sa.String(length=100), nullable=True))
    op.create_index(
        "uq_information_objects_external_id",
        "information_objects",
        ["tenant_id", "external_identifier"],
        unique=True,
        postgresql_where=sa.text("external_identifier IS NOT NULL"),
        sqlite_where=sa.text("external_identifier IS NOT NULL"),
    )

    with op.batch_alter_table("solution_boundaries") as batch_op:
        batch_op.add_column(sa.Column("external_identifier", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("owner", sa.String(length=160), nullable=True))
        batch_op.create_unique_constraint(
            "uq_solution_boundaries_object_tenant", ["object_id", "tenant_id"]
        )
    op.create_index(
        "uq_solution_boundaries_external_id",
        "solution_boundaries",
        ["tenant_id", "external_identifier"],
        unique=True,
        postgresql_where=sa.text("external_identifier IS NOT NULL"),
        sqlite_where=sa.text("external_identifier IS NOT NULL"),
    )

    with op.batch_alter_table("integrations") as batch_op:
        batch_op.add_column(sa.Column("external_identifier", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("metadata", json_type, nullable=False, server_default="{}"))
    op.create_index(
        "uq_integrations_active_external_id",
        "integrations",
        ["tenant_id", "external_identifier"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND external_identifier IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND external_identifier IS NOT NULL"),
    )

    op.create_table(
        "solution_members",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("solution_object_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_solution_members_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["solution_object_id", "tenant_id"],
            ["solution_boundaries.object_id", "solution_boundaries.tenant_id"],
            name="fk_solution_members_solution_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["system_id", "tenant_id"],
            ["systems.id", "systems.tenant_id"],
            name="fk_solution_members_system_tenant",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("solution_object_id", "system_id", name="uq_solution_members_pair"),
    )
    op.create_index(
        "ix_solution_members_solution",
        "solution_members",
        ["tenant_id", "solution_object_id"],
    )

    op.create_table(
        "import_batches",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("sheet_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("import_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="applied"),
        sa.Column("counts", json_type, nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_import_batches_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_import_batches_workspace",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('applied', 'undone', 'undo_blocked')",
            name="ck_import_batches_status",
        ),
    )
    op.create_index(
        "ix_import_batches_workspace",
        "import_batches",
        ["tenant_id", "workspace_id", "imported_at"],
    )

    op.create_table(
        "import_row_results",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_kind", sa.String(length=40), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("before", json_type, nullable=True),
        sa.Column("after", json_type, nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_import_row_results_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name="fk_import_row_results_batch",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_import_row_results_row"),
    )
    op.create_index(
        "ix_import_row_results_target",
        "import_row_results",
        ["tenant_id", "target_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_row_results_target", table_name="import_row_results")
    op.drop_table("import_row_results")
    op.drop_index("ix_import_batches_workspace", table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_index("ix_solution_members_solution", table_name="solution_members")
    op.drop_table("solution_members")

    op.drop_index("uq_integrations_active_external_id", table_name="integrations")
    with op.batch_alter_table("integrations") as batch_op:
        batch_op.drop_column("metadata")
        batch_op.drop_column("external_identifier")

    op.drop_index("uq_solution_boundaries_external_id", table_name="solution_boundaries")
    with op.batch_alter_table("solution_boundaries") as batch_op:
        batch_op.drop_constraint("uq_solution_boundaries_object_tenant", type_="unique")
        batch_op.drop_column("owner")
        batch_op.drop_column("external_identifier")

    op.drop_index("uq_information_objects_external_id", table_name="information_objects")
    with op.batch_alter_table("information_objects") as batch_op:
        batch_op.drop_column("classification")
        batch_op.drop_column("external_identifier")

    op.drop_index("uq_systems_active_external_id", table_name="systems")
    with op.batch_alter_table("systems") as batch_op:
        batch_op.drop_column("external_identifier")
