"""State-aware Solution Landscape.

A read-only projection over the canonical Solution Boundaries: ownership,
membership, Contract associations by role, evidence, and typed Solution-to-
Solution relationships. It answers ownership and dependency questions; the
Integration Landscape remains authoritative for technical exchange paths, so no
mappings, transformations, scenarios, conformance, resilience or full Contract
documents appear here.

Everything is bulk-loaded: one query per concern, never one per solution.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.architecture.evidence import assert_no_evidence, evidence_counts_by_target
from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    SolutionLandscapeContractAssociation,
    SolutionLandscapeContractCounts,
    SolutionLandscapeEdge,
    SolutionLandscapeNode,
    SolutionLandscapeResponse,
    SolutionLandscapeSystem,
    SolutionLandscapeWarning,
    SolutionRelationshipCreate,
    SolutionRelationshipResponse,
    SolutionRelationshipUpdate,
)
from app.architecture.state_scope import assert_writable
from app.architecture.state_scope import get_state as _get_state
from app.architecture.state_scope import state_is_editable as _state_is_editable
from app.architecture.state_scope import state_members as _state_members
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.integrations.facts import effective_facts, overrides_for_state
from app.integrations.schemas import IntegrationFactValue
from app.models import (
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    AuthSession,
    CatalogSystem,
    Integration,
    SolutionBoundary,
    SolutionComponent,
    SolutionIntegration,
    SolutionMember,
    Workspace,
)

logger = logging.getLogger("app.architecture.solution_landscape")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/solution",
    tags=["architecture"],
)

SOLUTION_KIND = "solution_boundary"

# The approved Solution-to-Solution vocabulary. Arbitrary strings are rejected by
# the request schema, not by convention.
SOLUTION_RELATIONSHIP_TYPES: tuple[str, ...] = (
    "depends_on",
    "uses",
    "provides_to",
    "replaces",
    "transitions_to",
    "shares_information_with",
)

SOLUTION_RELATIONSHIP_LABELS: dict[str, str] = {
    "depends_on": "Depends on",
    "uses": "Uses",
    "provides_to": "Provides to",
    "replaces": "Replaces",
    "transitions_to": "Transitions to",
    "shares_information_with": "Shares information with",
}

SYMMETRIC_RELATIONSHIP_TYPES = {"shares_information_with"}


def _require_solution(workspace: Workspace) -> None:
    if "solution" not in workspace.disciplines:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )


def _as_uuid(value) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def relationship_description(properties: dict | None) -> str | None:
    if not isinstance(properties, dict):
        return None
    value = properties.get("description")
    return value if isinstance(value, str) and value else None


def _solution_visibilities(
    db: Session, workspace: Workspace, state: ArchitectureState
) -> dict[UUID, dict | None]:
    """Visible Solution Boundaries for one state, keyed by object id.

    Reuses the existing state semantics: a boundary placed on the state canvas or
    explicitly included by a state member is visible; an explicitly excluded one
    is not. This keeps Candidate/Target isolation identical to the workbench.
    """
    members = _state_members(db, state)
    placed: dict[UUID, dict] = {}
    for node in state.nodes:
        object_id = _as_uuid(node.get("object_id"))
        if object_id is not None:
            placed[object_id] = node

    candidates = set(placed)
    candidates.update(
        object_id
        for object_id, member in members.items()
        if member.membership == "included"
    )
    if not candidates:
        return {}

    registrations = {
        row.id: row
        for row in db.scalars(
            select(ArchitectureObject).where(
                ArchitectureObject.tenant_id == workspace.tenant_id,
                ArchitectureObject.id.in_(candidates),
                ArchitectureObject.kind == SOLUTION_KIND,
            )
        )
    }
    visibilities: dict[UUID, dict | None] = {}
    for object_id in registrations:
        member = members.get(object_id)
        if member is not None and member.membership == "excluded":
            continue
        visibilities[object_id] = placed.get(object_id)
    return visibilities


def _bulk_boundaries(
    db: Session, workspace: Workspace, object_ids: set[UUID]
) -> dict[UUID, SolutionBoundary]:
    if not object_ids:
        return {}
    rows = db.scalars(
        select(SolutionBoundary).where(
            SolutionBoundary.tenant_id == workspace.tenant_id,
            SolutionBoundary.object_id.in_(object_ids),
        )
    )
    return {row.object_id: row for row in rows}


def _bulk_systems(db: Session, workspace: Workspace) -> dict[UUID, CatalogSystem]:
    rows = db.scalars(
        select(CatalogSystem).where(
            CatalogSystem.tenant_id == workspace.tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    )
    return {row.id: row for row in rows}


def _system_ref(system: CatalogSystem, *, external: bool) -> SolutionLandscapeSystem:
    return SolutionLandscapeSystem(
        system_id=system.id, name=system.name, kind=system.kind, external=external
    )


def build_solution_landscape(
    db: Session, workspace: Workspace, state: ArchitectureState
) -> SolutionLandscapeResponse:
    visibilities = _solution_visibilities(db, workspace, state)
    boundaries = _bulk_boundaries(db, workspace, set(visibilities))
    systems = _bulk_systems(db, workspace)
    warnings: list[SolutionLandscapeWarning] = []

    # --- membership (one query for every solution) ---------------------------
    member_rows = list(
        db.scalars(
            select(SolutionMember).where(
                SolutionMember.tenant_id == workspace.tenant_id,
                SolutionMember.solution_object_id.in_(set(boundaries) or {None}),
                or_(
                    SolutionMember.created_in_state_id.is_(None),
                    SolutionMember.created_in_state_id == state.id,
                ),
            )
        )
    )
    members_by_solution: dict[UUID, list[UUID]] = defaultdict(list)
    for row in member_rows:
        members_by_solution[row.solution_object_id].append(row.system_id)

    # --- components (one grouped query) --------------------------------------
    component_rows = db.execute(
        select(SolutionComponent.solution_object_id, SolutionComponent.object_id).where(
            SolutionComponent.tenant_id == workspace.tenant_id,
            SolutionComponent.solution_object_id.in_(set(boundaries) or {None}),
        )
    ).all()
    components_by_solution: dict[UUID, int] = defaultdict(int)
    for solution_object_id, _object_id in component_rows:
        components_by_solution[solution_object_id] += 1

    # --- Contract associations (one query) -----------------------------------
    association_rows = list(
        db.scalars(
            select(SolutionIntegration)
            .where(
                SolutionIntegration.tenant_id == workspace.tenant_id,
                SolutionIntegration.solution_object_id.in_(set(boundaries) or {None}),
                or_(
                    SolutionIntegration.created_in_state_id.is_(None),
                    SolutionIntegration.created_in_state_id == state.id,
                ),
            )
            .order_by(
                SolutionIntegration.created_in_state_id.is_not(None),
                SolutionIntegration.integration_id,
            )
        )
    )
    integration_ids = {row.integration_id for row in association_rows}
    integrations = (
        {
            row.id: row
            for row in db.scalars(
                select(Integration).where(
                    Integration.tenant_id == workspace.tenant_id,
                    Integration.id.in_(integration_ids),
                )
            )
        }
        if integration_ids
        else {}
    )
    contract_overrides = overrides_for_state(db, workspace.tenant_id, state.id)
    contract_evidence = evidence_counts_by_target(
        db, workspace.tenant_id, "integration", state.id
    )

    # --- evidence on boundaries and relationships (two grouped queries) ------
    object_evidence = evidence_counts_by_target(
        db, workspace.tenant_id, "architecture_object", state.id
    )
    relationship_evidence = evidence_counts_by_target(
        db, workspace.tenant_id, "architecture_relationship", state.id
    )

    # --- typed Solution relationships (one query) ----------------------------
    edge_rows = list(
        db.scalars(
            select(ArchitectureRelationship).where(
                ArchitectureRelationship.tenant_id == workspace.tenant_id,
                ArchitectureRelationship.relationship_type.in_(SOLUTION_RELATIONSHIP_TYPES),
                or_(
                    ArchitectureRelationship.created_in_state_id.is_(None),
                    ArchitectureRelationship.created_in_state_id == state.id,
                ),
            )
        )
    )
    edges = [
        row
        for row in edge_rows
        if row.source_object_id in boundaries and row.target_object_id in boundaries
    ]
    incoming: dict[UUID, int] = defaultdict(int)
    outgoing: dict[UUID, int] = defaultdict(int)
    for edge in edges:
        outgoing[edge.source_object_id] += 1
        incoming[edge.target_object_id] += 1

    state_names = {state.id: state.name}
    # External participating systems reuse the existing Solution Context
    # semantics: a system placed on the state canvas that is not a member.
    placed_system_ids: set[UUID] = set()
    for node in state.nodes:
        object_id = _as_uuid(node.get("object_id"))
        if object_id is not None and object_id in systems:
            placed_system_ids.add(object_id)

    solutions: list[SolutionLandscapeNode] = []
    for object_id, boundary in boundaries.items():
        member_ids = members_by_solution.get(object_id, [])
        member_summaries: list[SolutionLandscapeSystem] = []
        for system_id in member_ids:
            system = systems.get(system_id)
            if system is None:
                warnings.append(
                    SolutionLandscapeWarning(
                        code="member_system_unavailable",
                        message="A member system is archived or unavailable.",
                        solution_object_id=object_id,
                    )
                )
                continue
            member_summaries.append(_system_ref(system, external=False))
        member_summaries.sort(key=lambda item: (item.name.casefold(), str(item.system_id)))

        external_summaries: list[SolutionLandscapeSystem] = []
        for system_id in sorted(placed_system_ids, key=str):
            if system_id in set(member_ids) or system_id in boundaries:
                continue
            external_summaries.append(_system_ref(systems[system_id], external=True))
        external_summaries.sort(key=lambda item: (item.name.casefold(), str(item.system_id)))

        contracts: list[SolutionLandscapeContractAssociation] = []
        counts = SolutionLandscapeContractCounts()
        for row in association_rows:
            if row.solution_object_id != object_id:
                continue
            integration = integrations.get(row.integration_id)
            available = integration is not None and integration.deleted_at is None
            if not available:
                warnings.append(
                    SolutionLandscapeWarning(
                        code="archived_contract_association",
                        message=(
                            "This association references a Contract that is archived "
                            "or unavailable."
                        ),
                        solution_object_id=object_id,
                        association_id=row.id,
                        integration_id=row.integration_id,
                    )
                )
            facts = (
                effective_facts(integration, contract_overrides.get(integration.id))
                if available and integration is not None
                else None
            )
            contracts.append(
                SolutionLandscapeContractAssociation(
                    association_id=row.id,
                    role=row.role,  # type: ignore[arg-type]
                    description=row.description,
                    state_applicability=(
                        "canonical" if row.created_in_state_id is None else "state"
                    ),
                    state_name=(
                        state_names.get(row.created_in_state_id)
                        if row.created_in_state_id is not None
                        else None
                    ),
                    contract_id=row.integration_id,
                    contract_name=integration.name if integration is not None else None,
                    available=available,
                    implementation_status=(
                        (integration.implementation_status or "draft")
                        if available and integration is not None
                        else None
                    ),
                    lifecycle_stage=IntegrationFactValue(**facts["lifecycle_stage"])
                    if facts
                    else IntegrationFactValue(),
                    operational_status=IntegrationFactValue(**facts["operational_status"])
                    if facts
                    else IntegrationFactValue(),
                    environment_scope=IntegrationFactValue(**facts["environment_scope"])
                    if facts
                    else IntegrationFactValue(),
                    evidence_count=contract_evidence.get(row.integration_id, 0),
                )
            )
            if row.role == "owned":
                counts.owned += 1
            elif row.role == "participating":
                counts.participating += 1
            elif row.role == "dependency":
                counts.dependency += 1
        counts.total = counts.owned + counts.participating + counts.dependency

        solutions.append(
            SolutionLandscapeNode(
                solution_object_id=object_id,
                occurrence_id=(
                    str(visibilities.get(object_id, {}).get("occurrence_id"))
                    if visibilities.get(object_id)
                    else None
                ),
                name=boundary.name,
                description=boundary.description,
                owner=boundary.owner,
                lifecycle_stage=None,
                operational_status=None,
                component_count=components_by_solution.get(object_id, 0),
                member_count=len(member_summaries),
                external_system_count=len(external_summaries),
                members=member_summaries,
                external_systems=external_summaries,
                contract_counts=counts,
                contracts=contracts,
                evidence_count=object_evidence.get(object_id, 0),
                relationships_in=incoming.get(object_id, 0),
                relationships_out=outgoing.get(object_id, 0),
            )
        )
    solutions.sort(key=lambda item: (item.name.casefold(), str(item.solution_object_id)))

    relationships = [
        SolutionLandscapeEdge(
            id=edge.id,
            source_object_id=edge.source_object_id,
            target_object_id=edge.target_object_id,
            relationship_type=edge.relationship_type,  # type: ignore[arg-type]
            description=relationship_description(edge.properties),
            created_in_state_id=edge.created_in_state_id,
            state_applicability=(
                "canonical" if edge.created_in_state_id is None else "state"
            ),
            state_name=(
                state_names.get(edge.created_in_state_id)
                if edge.created_in_state_id is not None
                else None
            ),
            evidence_count=relationship_evidence.get(edge.id, 0),
        )
        for edge in edges
    ]
    relationships.sort(
        key=lambda item: (
            str(item.source_object_id),
            str(item.target_object_id),
            str(item.id),
        )
    )

    warnings.sort(
        key=lambda item: (
            item.code,
            str(item.solution_object_id),
            str(item.association_id),
        )
    )

    logger.info(
        "solution landscape generated workspace=%s state=%s "
        "solutions=%s relationships=%s warnings=%s",
        workspace.id,
        state.id,
        len(solutions),
        len(relationships),
        len(warnings),
    )
    return SolutionLandscapeResponse(
        state_id=state.id,
        state_type=state.state_type,
        editable=_state_is_editable(state),
        solutions=solutions,
        relationships=relationships,
        warnings=warnings,
    )


@router.get("/landscape", response_model=SolutionLandscapeResponse)
def solution_landscape(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionLandscapeResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, state_id)
    return build_solution_landscape(db, workspace, state)


def _get_solution_registry(
    db: Session, workspace: Workspace, object_id: UUID
) -> ArchitectureObject:
    registry = db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == object_id,
            ArchitectureObject.tenant_id == workspace.tenant_id,
            ArchitectureObject.kind == SOLUTION_KIND,
        )
    )
    if registry is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "not_a_solution",
                "message": "Both relationship endpoints must be Solution Boundaries",
            },
        )
    return registry


def _relationship_response(
    row: ArchitectureRelationship,
    state: ArchitectureState,
    state_names: dict[UUID, str],
    evidence_count: int,
) -> SolutionRelationshipResponse:
    return SolutionRelationshipResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        source_object_id=row.source_object_id,
        target_object_id=row.target_object_id,
        relationship_type=row.relationship_type,  # type: ignore[arg-type]
        description=relationship_description(row.properties),
        created_in_state_id=row.created_in_state_id,
        state_applicability="canonical" if row.created_in_state_id is None else "state",
        state_name=(
            state_names.get(row.created_in_state_id)
            if row.created_in_state_id is not None
            else None
        ),
        evidence_count=evidence_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get_solution_relationship(
    db: Session, workspace: Workspace, relationship_id: UUID, state: ArchitectureState
) -> ArchitectureRelationship:
    row = db.scalar(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.id == relationship_id,
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            ArchitectureRelationship.relationship_type.in_(SOLUTION_RELATIONSHIP_TYPES),
        )
    )
    if row is None or row.created_in_state_id not in (None, state.id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Solution relationship not found"
        )
    return row


def _relationship_evidence(
    db: Session, workspace: Workspace, relationship_id: UUID, state: ArchitectureState
) -> int:
    return evidence_counts_by_target(
        db, workspace.tenant_id, "architecture_relationship", state.id
    ).get(relationship_id, 0)


@router.post(
    "/relationships",
    response_model=SolutionRelationshipResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_relationship(
    workspace_id: UUID,
    payload: SolutionRelationshipCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionRelationshipResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, payload.state_id)
    assert_writable(state)
    if payload.source_object_id == payload.target_object_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "self_relationship",
                "message": "A Solution cannot relate to itself",
            },
        )
    # Both endpoints must be real, same-tenant Solution Boundaries.
    _get_solution_registry(db, workspace, payload.source_object_id)
    _get_solution_registry(db, workspace, payload.target_object_id)

    row = ArchitectureRelationship(
        id=uuid4(),
        tenant_id=workspace.tenant_id,
        source_object_id=payload.source_object_id,
        target_object_id=payload.target_object_id,
        relationship_type=payload.relationship_type,
        properties={"description": payload.description} if payload.description else {},
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
                "code": "duplicate_solution_relationship",
                "message": (
                    "These two Solutions already have this relationship type. Remove the "
                    "existing relationship before adding another."
                ),
            },
        ) from error
    db.refresh(row)
    logger.info(
        "solution relationship created workspace=%s id=%s type=%s",
        workspace.id,
        row.id,
        row.relationship_type,
    )
    return _relationship_response(row, state, {state.id: state.name}, 0)


@router.patch(
    "/relationships/{relationship_id}",
    response_model=SolutionRelationshipResponse,
)
def update_solution_relationship(
    workspace_id: UUID,
    relationship_id: UUID,
    payload: SolutionRelationshipUpdate,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionRelationshipResponse:
    """Update the relationship type or description. Endpoints are immutable."""
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, state_id)
    assert_writable(state)
    row = _get_solution_relationship(db, workspace, relationship_id, state)
    if row.created_in_state_id is None:
        # A canonical relationship is the Current baseline, so a single state must
        # not rewrite it.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "canonical_relationship_readonly",
                "message": "A canonical relationship cannot be changed from a single state",
            },
        )
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "empty_relationship_update",
                "message": "Provide a relationship type or description to update",
            },
        )
    if "relationship_type" in changes:
        row.relationship_type = changes["relationship_type"]
    if "description" in changes:
        properties = dict(row.properties or {})
        if changes["description"]:
            properties["description"] = changes["description"]
        else:
            properties.pop("description", None)
        row.properties = properties
    row.updated_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_solution_relationship",
                "message": "These two Solutions already have this relationship type.",
            },
        ) from error
    db.refresh(row)
    return _relationship_response(
        row,
        state,
        {state.id: state.name},
        _relationship_evidence(db, workspace, row.id, state),
    )


@router.delete("/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_solution_relationship(
    workspace_id: UUID,
    relationship_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Remove the relationship. Both Solution Boundaries are left untouched."""
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, state_id)
    assert_writable(state)
    row = _get_solution_relationship(db, workspace, relationship_id, state)
    if row.created_in_state_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "canonical_relationship_readonly",
                "message": "A canonical relationship cannot be deleted from a single state",
            },
        )
    # Evidence attached to the relationship blocks destructive deletion.
    assert_no_evidence(
        db, workspace.tenant_id, [("architecture_relationship", row.id)]
    )
    db.delete(row)
    db.commit()
    logger.info(
        "solution relationship removed workspace=%s id=%s", workspace.id, relationship_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
