"""Generic architecture evidence.

Revision ID: 0026_architecture_evidence
Revises: 0025_contract_mediator

Additive only. Creates ``architecture_evidence``: one generic evidence record
whose target is an exclusive arc of five real, tenant-scoped foreign keys, with
controlled-vocabulary and single-target check constraints and per-target indexes.
Three existing target tables gain the ``(id, tenant_id)`` unique constraint the
composite foreign keys need. No existing row or column is modified.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_architecture_evidence"
down_revision: str | None = "0025_contract_mediator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLASSIFICATION_IN = (
    "('confirmed_by_requirements_document', 'confirmed_by_current_implementation',"
    " 'confirmed_by_field_mapping', 'confirmed_by_user_working_knowledge',"
    " 'assumption', 'open_decision', 'future_scope')"
)
SOURCE_TYPE_IN = (
    "('document', 'implementation', 'mapping', 'meeting', 'message', 'test',"
    " 'ticket', 'repository', 'user_statement', 'other')"
)
CONFIDENCE_IN = "('low', 'medium', 'high')"
VERIFICATION_IN = "('unverified', 'verified', 'disputed', 'superseded')"

TARGET_COUNT = (
    "(CASE WHEN architecture_object_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN architecture_relationship_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN integration_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN integration_dependency_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN solution_member_id IS NOT NULL THEN 1 ELSE 0 END)"
)

# The existing target tables that did not yet expose (id, tenant_id) uniquely.
# The composite foreign keys below need it, exactly as ``architecture_objects``,
# ``integrations`` and ``systems`` already do.
_SUPPORTING_UNIQUE_CONSTRAINTS = (
    ("architecture_relationships", "uq_architecture_relationships_id_tenant"),
    ("integration_dependencies", "uq_integration_dependencies_id_tenant"),
    ("solution_members", "uq_solution_members_id_tenant"),
)


def _create_supporting_unique_constraints() -> None:
    # SQLite cannot ALTER TABLE to add a constraint to an existing table, so the
    # supporting uniques are only created on PostgreSQL (same precedent as 0024).
    # The ORM model declares them, so dialect-created schemas have them everywhere.
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name in _SUPPORTING_UNIQUE_CONSTRAINTS:
        op.create_unique_constraint(name, table, ["id", "tenant_id"])


def upgrade() -> None:
    _create_supporting_unique_constraints()

    op.create_table(
        "architecture_evidence",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("architecture_object_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("architecture_relationship_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("integration_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("integration_dependency_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("solution_member_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("evidence_classification", sa.String(length=48), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_title", sa.String(length=300), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=False),
        sa.Column("source_locator", sa.String(length=2000), nullable=True),
        sa.Column("summary", sa.String(length=2000), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column(
            "recorded_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_in_state_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("architecture_states.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["architecture_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_evidence_object_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["architecture_relationship_id", "tenant_id"],
            ["architecture_relationships.id", "architecture_relationships.tenant_id"],
            name="fk_architecture_evidence_relationship_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_architecture_evidence_integration_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["integration_dependency_id", "tenant_id"],
            ["integration_dependencies.id", "integration_dependencies.tenant_id"],
            name="fk_architecture_evidence_dependency_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["solution_member_id", "tenant_id"],
            ["solution_members.id", "solution_members.tenant_id"],
            name="fk_architecture_evidence_solution_member_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"{TARGET_COUNT} = 1",
            name="ck_architecture_evidence_single_target",
        ),
        sa.CheckConstraint(
            f"evidence_classification IN {CLASSIFICATION_IN}",
            name="ck_architecture_evidence_classification",
        ),
        sa.CheckConstraint(
            f"source_type IN {SOURCE_TYPE_IN}",
            name="ck_architecture_evidence_source_type",
        ),
        sa.CheckConstraint(
            f"confidence IN {CONFIDENCE_IN}",
            name="ck_architecture_evidence_confidence",
        ),
        sa.CheckConstraint(
            f"verification_status IN {VERIFICATION_IN}",
            name="ck_architecture_evidence_verification_status",
        ),
    )

    op.create_index("ix_architecture_evidence_tenant", "architecture_evidence", ["tenant_id"])
    op.create_index(
        "ix_architecture_evidence_state",
        "architecture_evidence",
        ["tenant_id", "created_in_state_id"],
    )
    op.create_index(
        "ix_architecture_evidence_object",
        "architecture_evidence",
        ["tenant_id", "architecture_object_id"],
    )
    op.create_index(
        "ix_architecture_evidence_relationship",
        "architecture_evidence",
        ["tenant_id", "architecture_relationship_id"],
    )
    op.create_index(
        "ix_architecture_evidence_integration",
        "architecture_evidence",
        ["tenant_id", "integration_id"],
    )
    op.create_index(
        "ix_architecture_evidence_dependency",
        "architecture_evidence",
        ["tenant_id", "integration_dependency_id"],
    )
    op.create_index(
        "ix_architecture_evidence_solution_member",
        "architecture_evidence",
        ["tenant_id", "solution_member_id"],
    )


def downgrade() -> None:
    for name in (
        "ix_architecture_evidence_solution_member",
        "ix_architecture_evidence_dependency",
        "ix_architecture_evidence_integration",
        "ix_architecture_evidence_relationship",
        "ix_architecture_evidence_object",
        "ix_architecture_evidence_state",
        "ix_architecture_evidence_tenant",
    ):
        op.drop_index(name, table_name="architecture_evidence")
    op.drop_table("architecture_evidence")

    if op.get_bind().dialect.name == "postgresql":
        for table, name in reversed(_SUPPORTING_UNIQUE_CONSTRAINTS):
            op.drop_constraint(name, table, type_="unique")
