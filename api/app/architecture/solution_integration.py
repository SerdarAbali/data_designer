"""Solution Boundary <-> Integration Contract associations.

Contract ownership cannot be inferred from source/target system membership: an
external participating system may sit outside ``SolutionMember`` while its
Contract still belongs to the solution. This module owns the explicit,
state-aware association and the bounded Contract projection the Solution
inspector needs.

Semantics:

* canonical (``created_in_state_id`` null) associations apply everywhere;
* a Candidate/Target association applies only in that state;
* Current stays read-only for state-scoped writes;
* one association per (solution, contract) inside a state scope;
* an association never implies or creates a membership, and removing it never
  touches the Contract or the Solution Boundary.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.architecture.evidence import evidence_counts_by_target
from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    SolutionIntegrationContractSummary,
    SolutionIntegrationCreate,
    SolutionIntegrationResponse,
    SolutionIntegrationUpdate,
)
from app.architecture.state_scope import assert_writable, current_state
from app.architecture.state_scope import get_state as _get_state
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.integrations.facts import effective_facts, overrides_for_state
from app.integrations.mediation import endpoint_ref, resolve_mediation
from app.integrations.schemas import IntegrationFactValue
from app.models import (
    ArchitectureObject,
    ArchitectureState,
    AuthSession,
    CatalogObject,
    CatalogSystem,
    Integration,
    SolutionBoundary,
    SolutionIntegration,
    Workspace,
)

logger = logging.getLogger("app.architecture.solution_integration")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/solution",
    tags=["architecture"],
)

SOLUTION_KIND = "solution_boundary"

# Derived traceability edges, one per approved role.
ROLE_EDGE_TYPE: dict[str, str] = {
    "owned": "owns_contract",
    "participating": "participates_in_contract",
    "dependency": "depends_on_contract",
}


def assert_no_solution_integration(
    db: Session,
    tenant_id: UUID,
    *,
    integration_id: UUID | None = None,
    solution_object_id: UUID | None = None,
) -> None:
    """Refuse to remove a Contract or Boundary that still has associations.

    Returns an actionable conflict rather than silently orphaning the
    association. There is no generic cascade: removing associations is always an
    explicit delete.
    """
    if integration_id is None and solution_object_id is None:
        return
    query = select(SolutionIntegration).where(SolutionIntegration.tenant_id == tenant_id)
    if integration_id is not None:
        query = query.where(SolutionIntegration.integration_id == integration_id)
    if solution_object_id is not None:
        query = query.where(SolutionIntegration.solution_object_id == solution_object_id)
    rows = list(db.scalars(query))
    if not rows:
        return
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail={
            "code": "solution_integration_conflict",
            "message": (
                "Remove the Solution Contract association(s) before removing this item"
            ),
            "associations": [
                {
                    "id": str(row.id),
                    "solution_object_id": str(row.solution_object_id),
                    "integration_id": str(row.integration_id),
                    "role": row.role,
                }
                for row in sorted(rows, key=lambda item: str(item.id))
            ],
        },
    )


def _require_solution(workspace: Workspace) -> None:
    if "solution" not in workspace.disciplines:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )


def _get_boundary(db: Session, workspace: Workspace, object_id: UUID) -> SolutionBoundary:
    """The selected object must be a Solution Boundary, not a component or system."""
    registry = db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == object_id,
            ArchitectureObject.tenant_id == workspace.tenant_id,
            ArchitectureObject.kind == SOLUTION_KIND,
        )
    )
    if registry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solution not found")
    boundary = db.scalar(
        select(SolutionBoundary).where(
            SolutionBoundary.object_id == registry.id,
            SolutionBoundary.tenant_id == workspace.tenant_id,
        )
    )
    if boundary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solution not found")
    return boundary


def _association_visible_in_state(state_id: UUID):
    """Canonical associations plus associations introduced for one state.

    ``NULL IN (...)`` is never true, so the canonical case is an explicit
    ``IS NULL``; the equality keeps one state's associations out of another's.
    """
    return or_(
        SolutionIntegration.created_in_state_id.is_(None),
        SolutionIntegration.created_in_state_id == state_id,
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


def _contract_summaries(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    integrations: list[Integration],
) -> dict[UUID, SolutionIntegrationContractSummary]:
    """Bounded Contract projection for the Solution inspector.

    Deliberately excludes mappings, transformations, scenarios and the
    resilience/security specification, which stay in Integration Architecture.
    """
    systems = {
        system.id: system
        for system in db.scalars(
            select(CatalogSystem).where(
                CatalogSystem.tenant_id == workspace.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
        )
    }
    objects = {
        obj.id: obj
        for obj in db.scalars(
            select(CatalogObject).where(
                CatalogObject.tenant_id == workspace.tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
        )
    }
    overrides = overrides_for_state(db, workspace.tenant_id, state.id)
    evidence_counts = evidence_counts_by_target(
        db, workspace.tenant_id, "integration", state.id
    )
    summaries: dict[UUID, SolutionIntegrationContractSummary] = {}
    for integration in integrations:
        source = endpoint_ref(
            systems, objects, integration.source_system_id, integration.source_object_id
        )
        target = endpoint_ref(
            systems, objects, integration.target_system_id, integration.target_object_id
        )
        mediation = resolve_mediation(integration, systems, source, target)
        facts = effective_facts(integration, overrides.get(integration.id))
        summaries[integration.id] = SolutionIntegrationContractSummary(
            id=integration.id,
            name=integration.name,
            interaction_type=integration.interaction_type,
            implementation_status=integration.implementation_status or "draft",
            source=source,
            target=target,
            mediator=mediation.mediator,
            explicit_mediator=mediation.explicit_mediator,
            mediated=mediation.mediated,
            mediation_source=mediation.source,
            evidence_count=evidence_counts.get(integration.id, 0),
            lifecycle_stage=IntegrationFactValue(**facts["lifecycle_stage"]),
            operational_status=IntegrationFactValue(**facts["operational_status"]),
            environment_scope=IntegrationFactValue(**facts["environment_scope"]),
        )
    return summaries


def _association_response(
    row: SolutionIntegration,
    contract: SolutionIntegrationContractSummary,
    state_names: dict[UUID, str] | None = None,
) -> SolutionIntegrationResponse:
    state_names = state_names or {}
    return SolutionIntegrationResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        solution_object_id=row.solution_object_id,
        integration_id=row.integration_id,
        role=row.role,  # type: ignore[arg-type]
        description=row.description,
        created_in_state_id=row.created_in_state_id,
        state_applicability="canonical" if row.created_in_state_id is None else "state",
        state_name=(
            state_names.get(row.created_in_state_id)
            if row.created_in_state_id is not None
            else None
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        contract=contract,
    )


def _associations_for_state(
    db: Session, workspace: Workspace, solution_object_id: UUID, state: ArchitectureState
) -> list[SolutionIntegration]:
    """Deterministic ordering: canonical first, then by contract name and id."""
    return list(
        db.scalars(
            select(SolutionIntegration)
            .join(
                Integration,
                (Integration.id == SolutionIntegration.integration_id)
                & (Integration.tenant_id == SolutionIntegration.tenant_id),
            )
            .where(
                SolutionIntegration.tenant_id == workspace.tenant_id,
                SolutionIntegration.solution_object_id == solution_object_id,
                _association_visible_in_state(state.id),
            )
            .order_by(
                SolutionIntegration.created_in_state_id.is_not(None),
                Integration.name,
                SolutionIntegration.integration_id,
            )
        )
    )


def _load_integrations(
    db: Session, workspace: Workspace, ids: set[UUID]
) -> dict[UUID, Integration]:
    if not ids:
        return {}
    rows = db.scalars(
        select(Integration).where(
            Integration.tenant_id == workspace.tenant_id,
            Integration.id.in_(ids),
            Integration.deleted_at.is_(None),
        )
    )
    return {row.id: row for row in rows}


@router.get(
    "/solutions/{solution_object_id}/contracts",
    response_model=list[SolutionIntegrationResponse],
)
def list_solution_contracts(
    workspace_id: UUID,
    solution_object_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[SolutionIntegrationResponse]:
    """Canonical associations plus those introduced in the selected state."""
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, state_id)
    rows = _associations_for_state(db, workspace, boundary.object_id, state)
    integrations = _load_integrations(db, workspace, {row.integration_id for row in rows})
    summaries = _contract_summaries(db, workspace, state, list(integrations.values()))
    state_names = _state_names(
        db, workspace, {row.created_in_state_id for row in rows if row.created_in_state_id}
    )
    responses: list[SolutionIntegrationResponse] = []
    for row in rows:
        contract = summaries.get(row.integration_id)
        if contract is None:
            # The Contract was archived; the association is retained but cannot be
            # projected as an active Contract.
            continue
        responses.append(_association_response(row, contract, state_names))
    return responses


@router.get(
    "/solutions/{solution_object_id}/contracts/{association_id}",
    response_model=SolutionIntegrationResponse,
)
def get_solution_contract(
    workspace_id: UUID,
    solution_object_id: UUID,
    association_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionIntegrationResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, state_id)
    row = _get_association(db, workspace, boundary.object_id, association_id)
    integration = _load_integrations(db, workspace, {row.integration_id}).get(row.integration_id)
    if integration is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "association_contract_archived",
                "message": "The associated Contract is archived",
            },
        )
    summaries = _contract_summaries(db, workspace, state, [integration])
    state_names = _state_names(
        db, workspace, {row.created_in_state_id} if row.created_in_state_id else set()
    )
    return _association_response(row, summaries[integration.id], state_names)


def _get_association(
    db: Session, workspace: Workspace, solution_object_id: UUID, association_id: UUID
) -> SolutionIntegration:
    row = db.scalar(
        select(SolutionIntegration).where(
            SolutionIntegration.id == association_id,
            SolutionIntegration.tenant_id == workspace.tenant_id,
            SolutionIntegration.solution_object_id == solution_object_id,
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Solution association not found")
    return row


@router.post(
    "/solutions/{solution_object_id}/contracts",
    response_model=SolutionIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_contract(
    workspace_id: UUID,
    solution_object_id: UUID,
    payload: SolutionIntegrationCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionIntegrationResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, payload.state_id)
    assert_writable(state)
    integration = db.scalar(
        select(Integration).where(
            Integration.id == payload.integration_id,
            Integration.tenant_id == workspace.tenant_id,
        )
    )
    if integration is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "unknown_contract",
                "message": "The Contract does not exist in this workspace",
            },
        )
    if integration.deleted_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "archived_contract",
                "message": "An archived Contract cannot be associated with a solution",
            },
        )

    row = SolutionIntegration(
        id=uuid4(),
        tenant_id=workspace.tenant_id,
        solution_object_id=boundary.object_id,
        integration_id=integration.id,
        role=payload.role,
        description=payload.description,
        created_in_state_id=state.id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_solution_association",
                "message": "This Contract is already associated with this solution here",
            },
        ) from error
    db.refresh(row)
    logger.info(
        "solution contract associated workspace=%s solution=%s contract=%s role=%s state=%s",
        workspace.id,
        boundary.object_id,
        integration.id,
        row.role,
        state.id,
    )
    summaries = _contract_summaries(db, workspace, state, [integration])
    state_names = _state_names(db, workspace, {row.created_in_state_id})
    return _association_response(row, summaries[integration.id], state_names)


@router.patch(
    "/solutions/{solution_object_id}/contracts/{association_id}",
    response_model=SolutionIntegrationResponse,
)
def update_solution_contract(
    workspace_id: UUID,
    solution_object_id: UUID,
    association_id: UUID,
    payload: SolutionIntegrationUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionIntegrationResponse:
    """Update the role or the description. The Contract link itself is immutable."""
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    row = _get_association(db, workspace, boundary.object_id, association_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "empty_association_update",
                "message": "Provide a role or a description to update",
            },
        )
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    # The Contract projection is state-dependent, so it is rendered for the
    # association's own state (canonical associations use the Current baseline).
    state = (
        _get_state(db, workspace, row.created_in_state_id)
        if row.created_in_state_id is not None
        else current_state(db, workspace)
    )
    if state is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Architecture state not found"
        )
    integration = _load_integrations(db, workspace, {row.integration_id}).get(row.integration_id)
    if integration is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "association_contract_archived",
                "message": "The associated Contract is archived",
            },
        )
    summaries = _contract_summaries(db, workspace, state, [integration])
    state_names = _state_names(
        db, workspace, {row.created_in_state_id} if row.created_in_state_id else set()
    )
    logger.info(
        "solution contract association updated workspace=%s association=%s",
        workspace.id,
        row.id,
    )
    return _association_response(row, summaries[integration.id], state_names)


@router.delete(
    "/solutions/{solution_object_id}/contracts/{association_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_solution_contract(
    workspace_id: UUID,
    solution_object_id: UUID,
    association_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Remove the association. Neither the Contract nor the solution is touched."""
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    row = _get_association(db, workspace, boundary.object_id, association_id)
    integration_id = row.integration_id
    db.delete(row)
    db.commit()
    logger.info(
        "solution contract association removed workspace=%s solution=%s contract=%s",
        workspace.id,
        boundary.object_id,
        integration_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
