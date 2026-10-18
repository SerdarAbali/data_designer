"""Generic architecture evidence API.

Evidence records *why* an architecture assertion is believed: its source, its
evidentiary classification, the recorder's confidence, and its verification
status. One model serves Enterprise, Information, Solution and Integration
Architecture.

The target is an **exclusive arc** of five real, tenant-scoped foreign keys. The
API speaks in ``(target_kind, target_id)``; the table stores the concrete foreign
key, so referential integrity is never traded for polymorphism.

State applicability mirrors the rest of the studio: ``created_in_state_id`` null
means canonically applicable, otherwise the record was introduced for one
Candidate/Target state. Current stays read-only for state-scoped writes, and
evidence never modifies the fact it describes.

Retention: the foreign keys are ``ON DELETE RESTRICT``, so archiving a fact never
silently drops its evidence and hard-deleting a fact that is still supported
returns a conflict instead of orphaning rows. Removing evidence is always the
explicit, tenant- and workspace-guarded delete below.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    EvidenceCreate,
    EvidenceResponse,
    EvidenceTargetKind,
    EvidenceUpdate,
)
from app.architecture.state_scope import assert_writable, get_state
from app.architecture.vocabulary import EVIDENCE_TARGET_COLUMNS
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.models import (
    ArchitectureEvidence,
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    AuthSession,
    Integration,
    IntegrationDependency,
    SolutionMember,
    Workspace,
)

logger = logging.getLogger("app.architecture.evidence")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/evidence",
    tags=["architecture"],
)

# target kind -> model. A closed mapping; the kind is schema-validated and is
# never used to build SQL.
_TARGET_MODELS: dict[str, type] = {
    "architecture_object": ArchitectureObject,
    "architecture_relationship": ArchitectureRelationship,
    "integration": Integration,
    "integration_dependency": IntegrationDependency,
    "solution_member": SolutionMember,
}

# Targets that are archived by soft delete rather than physically removed.
_SOFT_DELETE_TARGETS = {"integration"}


def target_column(kind: str) -> str:
    return EVIDENCE_TARGET_COLUMNS[kind]


def evidence_visible_in_state(condition_state_id: UUID):
    """SQL predicate: canonical evidence plus evidence introduced for one state.

    ``created_in_state_id IN (NULL, :state)`` would never match canonical rows
    because ``NULL IN (...)`` is never true, so the null case is an explicit
    ``IS NULL``. Because the state comparison is exact, evidence introduced for
    one Candidate/Target state can never appear in another state.
    """
    return or_(
        ArchitectureEvidence.created_in_state_id.is_(None),
        ArchitectureEvidence.created_in_state_id == condition_state_id,
    )


def _target_kind_of(row: ArchitectureEvidence) -> str:
    for kind, column in EVIDENCE_TARGET_COLUMNS.items():
        if getattr(row, column) is not None:
            return kind
    raise RuntimeError(f"evidence {row.id} has no target")  # pragma: no cover


def _verify_target(
    db: Session, workspace: Workspace, target_kind: str, target_id: UUID
) -> None:
    """The target must exist, belong to this tenant, and not be retired.

    Evidence already attached to a fact that is later archived is retained and
    stays readable; attaching *new* evidence to an already-retired fact is
    refused so a retired assertion cannot quietly acquire fresh support.
    """
    model = _TARGET_MODELS.get(target_kind)
    if model is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsupported_evidence_target",
                "message": "Evidence targets must be one of the supported kinds",
            },
        )
    row = db.scalar(
        select(model).where(model.id == target_id, model.tenant_id == workspace.tenant_id)
    )
    if row is None:
        # Same answer for unknown and for another tenant's id, so a cross-tenant
        # identifier cannot be probed for existence.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "unknown_evidence_target",
                "message": "The evidence target does not exist in this workspace",
            },
        )
    if target_kind in _SOFT_DELETE_TARGETS and getattr(row, "deleted_at", None) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "evidence_target_archived",
                "message": "New evidence cannot be attached to an archived target",
            },
        )


def assert_no_evidence(
    db: Session, tenant_id: UUID, targets: Iterable[tuple[str, UUID]]
) -> None:
    """Refuse to hard-delete facts that are still supported by evidence.

    Called by the architecture delete paths, so a user gets an actionable
    conflict instead of a database integrity error, and evidence is never
    silently dropped.
    """
    blocked: list[dict[str, str]] = []
    for kind, target_id in targets:
        column = getattr(ArchitectureEvidence, target_column(kind))
        rows = db.scalars(
            select(ArchitectureEvidence.id).where(
                ArchitectureEvidence.tenant_id == tenant_id,
                column == target_id,
            )
        ).all()
        blocked.extend(
            {"target_kind": kind, "target_id": str(target_id), "evidence_id": str(row)}
            for row in rows
        )
    if blocked:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "evidence_blocks_delete",
                "message": (
                    "Delete the evidence that supports this fact before removing the fact"
                ),
                "evidence": blocked,
            },
        )


def _state_names(db: Session, workspace: Workspace, state_ids: set[UUID]) -> dict[UUID, str]:
    if not state_ids:
        return {}
    rows = db.scalars(
        select(ArchitectureState).where(
            ArchitectureState.id.in_(state_ids),
            ArchitectureState.workspace_id == workspace.id,
        )
    )
    return {row.id: row.name for row in rows}


def _evidence_response(
    row: ArchitectureEvidence, state_names: dict[UUID, str] | None = None
) -> EvidenceResponse:
    target_kind = _target_kind_of(row)
    state_names = state_names or {}
    return EvidenceResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        target_kind=target_kind,  # type: ignore[arg-type]
        target_id=getattr(row, target_column(target_kind)),
        evidence_classification=row.evidence_classification,  # type: ignore[arg-type]
        source_type=row.source_type,  # type: ignore[arg-type]
        source_title=row.source_title,
        source_reference=row.source_reference,
        source_locator=row.source_locator,
        summary=row.summary,
        confidence=row.confidence,  # type: ignore[arg-type]
        verification_status=row.verification_status,  # type: ignore[arg-type]
        recorded_by=row.recorded_by,
        recorded_at=row.recorded_at,
        updated_at=row.updated_at,
        created_in_state_id=row.created_in_state_id,
        state_applicability="canonical" if row.created_in_state_id is None else "state",
        state_name=(
            state_names.get(row.created_in_state_id)
            if row.created_in_state_id is not None
            else None
        ),
    )


def _get_evidence(db: Session, workspace: Workspace, evidence_id: UUID) -> ArchitectureEvidence:
    row = db.scalar(
        select(ArchitectureEvidence).where(
            ArchitectureEvidence.id == evidence_id,
            ArchitectureEvidence.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return row


def evidence_count(
    db: Session, tenant_id: UUID, target_kind: str, target_id: UUID, state_id: UUID
) -> int:
    """Bounded count of the evidence visible for one target in one state."""
    column = getattr(ArchitectureEvidence, target_column(target_kind))
    return db.scalar(
        select(func.count(ArchitectureEvidence.id)).where(
            ArchitectureEvidence.tenant_id == tenant_id,
            column == target_id,
            evidence_visible_in_state(state_id),
        )
    ) or 0


def evidence_counts_by_target(
    db: Session, tenant_id: UUID, target_kind: str, state_id: UUID
) -> dict[UUID, int]:
    """Bulk counts so a projection never issues one query per row."""
    column = getattr(ArchitectureEvidence, target_column(target_kind))
    rows = db.execute(
        select(column, func.count(ArchitectureEvidence.id))
        .where(
            ArchitectureEvidence.tenant_id == tenant_id,
            column.is_not(None),
            evidence_visible_in_state(state_id),
        )
        .group_by(column)
    ).all()
    return {target_id: count for target_id, count in rows}


@router.post("", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
def create_evidence(
    workspace_id: UUID,
    payload: EvidenceCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EvidenceResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _verify_target(db, workspace, payload.target_kind, payload.target_id)

    if payload.created_in_state_id is not None:
        state = get_state(db, workspace, payload.created_in_state_id)
        # Current is read-only for state-scoped writes; Candidate and Target are
        # allowed. Canonical evidence (no state) is always allowed.
        assert_writable(state)

    row = ArchitectureEvidence(
        tenant_id=workspace.tenant_id,
        evidence_classification=payload.evidence_classification,
        source_type=payload.source_type,
        source_title=payload.source_title,
        source_reference=payload.source_reference,
        source_locator=payload.source_locator,
        summary=payload.summary,
        confidence=payload.confidence,
        verification_status=payload.verification_status,
        # Provenance is server-controlled; the client can never supply it.
        recorded_by=user.id,
        created_in_state_id=payload.created_in_state_id,
    )
    setattr(row, target_column(payload.target_kind), payload.target_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "evidence created workspace=%s target_kind=%s target=%s classification=%s",
        workspace.id,
        payload.target_kind,
        payload.target_id,
        payload.evidence_classification,
    )
    state_names = _state_names(
        db, workspace, {row.created_in_state_id} if row.created_in_state_id else set()
    )
    return _evidence_response(row, state_names)


@router.get("", response_model=list[EvidenceResponse])
def list_evidence(
    workspace_id: UUID,
    target_kind: EvidenceTargetKind,
    target_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[EvidenceResponse]:
    """Bounded list for exactly one target and one state, deterministically ordered.

    A state is always supplied, so evidence introduced for one Candidate/Target
    state can never leak into another; the result is canonical evidence plus the
    evidence introduced for that state.
    """
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = get_state(db, workspace, state_id)
    column = getattr(ArchitectureEvidence, target_column(target_kind))
    rows = list(
        db.scalars(
            select(ArchitectureEvidence)
            .where(
                ArchitectureEvidence.tenant_id == workspace.tenant_id,
                column == target_id,
                evidence_visible_in_state(state.id),
            )
            .order_by(ArchitectureEvidence.recorded_at.desc(), ArchitectureEvidence.id)
        )
    )
    state_names = _state_names(
        db, workspace, {row.created_in_state_id for row in rows if row.created_in_state_id}
    )
    return [_evidence_response(row, state_names) for row in rows]


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    workspace_id: UUID,
    evidence_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EvidenceResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    row = _get_evidence(db, workspace, evidence_id)
    state_names = _state_names(
        db, workspace, {row.created_in_state_id} if row.created_in_state_id else set()
    )
    return _evidence_response(row, state_names)


@router.patch("/{evidence_id}", response_model=EvidenceResponse)
def update_evidence(
    workspace_id: UUID,
    evidence_id: UUID,
    payload: EvidenceUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EvidenceResponse:
    """Update evidence metadata.

    The target, the state applicability and ``recorded_by`` / ``recorded_at`` are
    provenance and are never replaced by an update.
    """
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    row = _get_evidence(db, workspace, evidence_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "empty_evidence_update",
                "message": "Provide at least one evidence field to update",
            },
        )
    for key, value in changes.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    logger.info("evidence updated workspace=%s evidence=%s", workspace.id, row.id)
    state_names = _state_names(
        db, workspace, {row.created_in_state_id} if row.created_in_state_id else set()
    )
    return _evidence_response(row, state_names)


@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(
    workspace_id: UUID,
    evidence_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Explicitly delete one evidence record.

    Evidence is never cascade-deleted and never soft-deleted implicitly; removing
    it is always this deliberate, tenant- and workspace-guarded operation.
    """
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    row = _get_evidence(db, workspace, evidence_id)
    db.delete(row)
    db.commit()
    logger.info("evidence deleted workspace=%s evidence=%s", workspace.id, evidence_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
