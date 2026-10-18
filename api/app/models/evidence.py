"""Generic architecture evidence.

Evidence records *why* an architecture assertion is believed: its source, its
evidentiary classification, the recorder's confidence, and its verification
status. One model serves Enterprise, Information, Solution and Integration
Architecture, so it deliberately carries no discipline-specific meaning.

The target is an **exclusive arc** of five real, nullable, tenant-scoped foreign
keys. Exactly one is non-null (enforced by a database check), which is why there
is no polymorphic ``target_type``/``target_id`` column here: a polymorphic pair
would give up referential integrity, and the arc keeps it.

Evidence never modifies the fact it describes, never stores documents or binary
content (``source_reference`` holds only an external locator), and is never
cascade-deleted when a target is archived.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.architecture.vocabulary import (
    CONFIDENCES,
    EVIDENCE_CLASSIFICATIONS,
    EVIDENCE_SOURCE_TYPES,
    VERIFICATION_STATUSES,
    sql_in_list,
)
from app.db import Base
from app.models.catalog import utc_now

# The five exclusive-arc target columns, in a stable order.
EVIDENCE_TARGET_FIELDS: tuple[str, ...] = (
    "architecture_object_id",
    "architecture_relationship_id",
    "integration_id",
    "integration_dependency_id",
    "solution_member_id",
)

_EVIDENCE_TARGET_COUNT = " + ".join(
    f"(CASE WHEN {column} IS NOT NULL THEN 1 ELSE 0 END)"
    for column in EVIDENCE_TARGET_FIELDS
)


class ArchitectureEvidence(Base):
    """One piece of evidence supporting exactly one architecture assertion."""

    __tablename__ = "architecture_evidence"
    __table_args__ = (
        # Real, tenant-scoped foreign keys. RESTRICT is deliberate: archiving a
        # fact must never silently delete its evidence, and hard-deleting a fact
        # must fail loudly instead of orphaning evidence.
        ForeignKeyConstraint(
            ["architecture_object_id", "tenant_id"],
            ["architecture_objects.id", "architecture_objects.tenant_id"],
            name="fk_architecture_evidence_object_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["architecture_relationship_id", "tenant_id"],
            ["architecture_relationships.id", "architecture_relationships.tenant_id"],
            name="fk_architecture_evidence_relationship_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_architecture_evidence_integration_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["integration_dependency_id", "tenant_id"],
            ["integration_dependencies.id", "integration_dependencies.tenant_id"],
            name="fk_architecture_evidence_dependency_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["solution_member_id", "tenant_id"],
            ["solution_members.id", "solution_members.tenant_id"],
            name="fk_architecture_evidence_solution_member_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"({_EVIDENCE_TARGET_COUNT}) = 1",
            name="ck_architecture_evidence_single_target",
        ),
        CheckConstraint(
            f"evidence_classification IN {sql_in_list(EVIDENCE_CLASSIFICATIONS)}",
            name="ck_architecture_evidence_classification",
        ),
        CheckConstraint(
            f"source_type IN {sql_in_list(EVIDENCE_SOURCE_TYPES)}",
            name="ck_architecture_evidence_source_type",
        ),
        CheckConstraint(
            f"confidence IN {sql_in_list(CONFIDENCES)}",
            name="ck_architecture_evidence_confidence",
        ),
        CheckConstraint(
            f"verification_status IN {sql_in_list(VERIFICATION_STATUSES)}",
            name="ck_architecture_evidence_verification_status",
        ),
        Index("ix_architecture_evidence_tenant", "tenant_id"),
        Index("ix_architecture_evidence_state", "tenant_id", "created_in_state_id"),
        Index(
            "ix_architecture_evidence_object", "tenant_id", "architecture_object_id"
        ),
        Index(
            "ix_architecture_evidence_relationship",
            "tenant_id",
            "architecture_relationship_id",
        ),
        Index("ix_architecture_evidence_integration", "tenant_id", "integration_id"),
        Index(
            "ix_architecture_evidence_dependency",
            "tenant_id",
            "integration_dependency_id",
        ),
        Index(
            "ix_architecture_evidence_solution_member",
            "tenant_id",
            "solution_member_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )

    # Exclusive arc: exactly one of these is non-null (database check above).
    architecture_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    architecture_relationship_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    integration_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    integration_dependency_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    solution_member_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))

    evidence_classification: Mapped[str] = mapped_column(String(48), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_title: Mapped[str] = mapped_column(String(300), nullable=False)
    # An external locator only: a URL, document/ticket identifier, repository
    # path or similar. Never a document body, file, credential or secret.
    source_reference: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(2000))
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unverified"
    )

    # Server-controlled provenance. Immutable after creation.
    recorded_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    # ``NULL`` means the evidence is canonically applicable; otherwise it was
    # introduced for that specific non-current state.
    created_in_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("architecture_states.id", ondelete="SET NULL")
    )
