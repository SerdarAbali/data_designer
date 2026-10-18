from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.schemas import (
    ArchitectureStateCreate,
    ArchitectureStateNode,
    ArchitectureStateRelationship,
    ArchitectureStateResponse,
    ArchitectureStateUpdate,
    DuplicateStateRequest,
    IncludeObjectsRequest,
    IncludeObjectsResponse,
    IncludeObjectsSkipped,
)
from app.architecture.state_scope import BASELINE_DRAFT, assert_writable
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.models import (
    ArchitectureObject,
    ArchitectureState,
    AuthSession,
    CatalogSystem,
    Integration,
    SolutionMember,
    Workspace,
)
from app.workspaces.routes import _ensure_workspace_entity, _user_can_access_workspace

router = APIRouter(prefix="/api/workspaces/{workspace_id}/states", tags=["architecture"])


def get_accessible_workspace(db: Session, user: AuthenticatedUser, workspace_id: UUID) -> Workspace:
    # Workspaces share their id with the backing tenant, so tenant access rules apply.
    tenant = _user_can_access_workspace(db, user, workspace_id)
    workspace = _ensure_workspace_entity(db, tenant)
    db.commit()
    return workspace


def auto_initialize_current_state(
    db: Session,
    workspace: Workspace,
    *,
    baseline_status: str = BASELINE_DRAFT,
) -> ArchitectureState:
    """Create the workspace's Current state.

    This is the lazy first-read initializer: it captures the Catalog systems and
    Contracts that exist by then and starts the baseline as a draft, so the user
    can capture and confirm it. The Candidate-starter option passes ``locked``
    explicitly. Existing Current rows are locked by the Slice 8C migration.
    """
    # Build nodes from active canonical catalog systems in tenant
    systems = list(
        db.scalars(
            select(CatalogSystem)
            .where(
                CatalogSystem.tenant_id == workspace.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
            .order_by(CatalogSystem.created_at.asc())
        )
    )

    nodes: list[dict] = []
    occurrence_by_system: dict[UUID, str] = {}
    col_width = 360
    row_height = 200
    for idx, sys in enumerate(systems):
        if (
            sys.position
            and isinstance(sys.position, dict)
            and "x" in sys.position
            and "y" in sys.position
        ):
            pos = {"x": float(sys.position["x"]), "y": float(sys.position["y"])}
        else:
            col = idx % 3
            row = idx // 3
            pos = {"x": float(col * col_width + 80), "y": float(row * row_height + 80)}

        occurrence_by_system[sys.id] = f"occ-{sys.id}"
        nodes.append(
            ArchitectureStateNode(
                occurrence_id=occurrence_by_system[sys.id],
                object_id=sys.id,
                position=pos,
                parent_occurrence_id=None,
                width=320.0,
                height=160.0,
                display_metadata={},
                candidate_overrides={},
            ).model_dump(mode="json")
        )

    # Build relationships from active integrations in tenant
    integrations = list(
        db.scalars(
            select(Integration).where(
                Integration.tenant_id == workspace.tenant_id,
                Integration.deleted_at.is_(None),
            )
        )
    )
    relationships: list[dict] = []
    for intg in integrations:
        source_occurrence = occurrence_by_system.get(intg.source_system_id)
        target_occurrence = occurrence_by_system.get(intg.target_system_id)
        if source_occurrence is None or target_occurrence is None:
            continue
        relationships.append(
            ArchitectureStateRelationship(
                id=f"rel-{intg.id}",
                source_id=source_occurrence,
                target_id=target_occurrence,
                type="Consumes",
                name=intg.name,
                integration_id=intg.id,
                candidate_overrides={},
                display_metadata={},
            ).model_dump(mode="json")
        )

    initial_state = ArchitectureState(
        id=uuid4(),
        workspace_id=workspace.id,
        name="Current State",
        state_type="current",
        description="Authoritative current state architecture",
        baseline_status=baseline_status,
        nodes=nodes,
        relationships=relationships,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(initial_state)
    db.commit()
    db.refresh(initial_state)
    return initial_state


def _validate_state_nodes(
    db: Session,
    workspace: Workspace,
    nodes: list[ArchitectureStateNode],
) -> None:
    object_ids = {node.object_id for node in nodes}
    if not object_ids:
        return
    valid_ids = set(
        db.scalars(
            select(ArchitectureObject.id).where(
                ArchitectureObject.tenant_id == workspace.tenant_id,
                ArchitectureObject.id.in_(object_ids),
            )
        )
    )
    if valid_ids != object_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One or more architecture objects do not belong to this workspace",
        )


@router.get("", response_model=list[ArchitectureStateResponse])
def list_architecture_states(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[ArchitectureState]:
    workspace = get_accessible_workspace(db, user, workspace_id)
    states = list(
        db.scalars(
            select(ArchitectureState)
            .where(
                ArchitectureState.workspace_id == workspace.id,
                ArchitectureState.deleted_at.is_(None),
            )
            .order_by(ArchitectureState.created_at.asc())
        )
    )
    if not states:
        initial = auto_initialize_current_state(db, workspace)
        states = [initial]
    return states


@router.post("", response_model=ArchitectureStateResponse, status_code=status.HTTP_201_CREATED)
def create_architecture_state(
    workspace_id: UUID,
    payload: ArchitectureStateCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureState:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    if payload.state_type == "current":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Current state is initialized automatically and cannot be created manually",
        )
    _validate_state_nodes(db, workspace, payload.nodes)

    # Check unique name for active states in this workspace
    existing = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.name == payload.name.strip(),
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An architecture state named '{payload.name}' already exists in this workspace",
        )

    new_state = ArchitectureState(
        id=uuid4(),
        workspace_id=workspace.id,
        name=payload.name.strip(),
        state_type=payload.state_type,
        description=payload.description.strip() if payload.description else None,
        nodes=[node.model_dump(mode="json") for node in payload.nodes],
        relationships=[rel.model_dump(mode="json") for rel in payload.relationships],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(new_state)
    db.commit()
    db.refresh(new_state)
    return new_state


@router.get("/{state_id}", response_model=ArchitectureStateResponse)
def get_architecture_state(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureState:
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Architecture state not found"
        )
    return state


@router.put("/{state_id}", response_model=ArchitectureStateResponse)
def update_architecture_state(
    workspace_id: UUID,
    state_id: UUID,
    payload: ArchitectureStateUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureState:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Architecture state not found"
        )
    assert_writable(state)

    if payload.name is not None and payload.name.strip() != state.name:
        existing = db.scalar(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == workspace.id,
                ArchitectureState.name == payload.name.strip(),
                ArchitectureState.id != state.id,
                ArchitectureState.deleted_at.is_(None),
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"An architecture state named '{payload.name}' already exists "
                    "in this workspace"
                ),
            )
        state.name = payload.name.strip()

    if payload.description is not None:
        state.description = payload.description.strip() if payload.description else None

    if payload.nodes is not None:
        _validate_state_nodes(db, workspace, payload.nodes)
        state.nodes = [node.model_dump(mode="json") for node in payload.nodes]

    if payload.relationships is not None:
        state.relationships = [rel.model_dump(mode="json") for rel in payload.relationships]

    state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(state)
    return state


@router.post(
    "/{state_id}/duplicate",
    response_model=ArchitectureStateResponse,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_architecture_state(
    workspace_id: UUID,
    state_id: UUID,
    payload: DuplicateStateRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureState:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    source_state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if source_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source architecture state not found"
        )

    target_name = payload.target_name.strip()
    existing = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.name == target_name,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An architecture state named '{target_name}' already exists in this workspace",
        )

    # Deep copy nodes and relationships, assigning new occurrence_ids but PRESERVING object_ids!
    occurrence_map: dict[str, str] = {}
    copied_nodes: list[dict] = []
    for node in deepcopy(source_state.nodes):
        old_occ = node.get("occurrence_id", "")
        new_occ = f"occ-{uuid4()}"
        occurrence_map[old_occ] = new_occ
        node["occurrence_id"] = new_occ
        copied_nodes.append(node)

    # Update parent_occurrence_id if any was mapped
    for node in copied_nodes:
        if node.get("parent_occurrence_id") and node["parent_occurrence_id"] in occurrence_map:
            node["parent_occurrence_id"] = occurrence_map[node["parent_occurrence_id"]]

    copied_relationships: list[dict] = []
    for rel in deepcopy(source_state.relationships):
        rel["id"] = f"rel-{uuid4()}"
        # Remap source and target if they referenced occurrence_ids
        if rel.get("source_id") in occurrence_map:
            rel["source_id"] = occurrence_map[rel["source_id"]]
        if rel.get("target_id") in occurrence_map:
            rel["target_id"] = occurrence_map[rel["target_id"]]
        copied_relationships.append(rel)

    new_state = ArchitectureState(
        id=uuid4(),
        workspace_id=workspace.id,
        name=target_name,
        state_type=payload.target_state_type,
        description=payload.description.strip()
        if payload.description
        else source_state.description,
        nodes=copied_nodes,
        relationships=copied_relationships,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(new_state)
    db.commit()
    db.refresh(new_state)
    return new_state


@router.delete("/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_architecture_state(
    workspace_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Architecture state not found"
        )
    if state.state_type == "current":
        # Deleting the baseline itself is not part of the capture/lock lifecycle:
        # the Current state is the workspace's baseline container either way.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "current_state_protected",
                "message": "The Current state cannot be deleted.",
            },
        )

    state.deleted_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


KIND_DISCIPLINE_FOR_INCLUDE = {
    "business_requirement": "enterprise",
    "business_capability": "enterprise",
    "information_object": "information",
    "solution_boundary": "solution",
    "component": "solution",
    "interface": "solution",
}


def _placement(index: int) -> dict[str, float]:
    column = index % 3
    row = index // 3
    return {"x": float(column * 360 + 80), "y": float(row * 200 + 80)}


@router.post("/{state_id}/include-objects", response_model=IncludeObjectsResponse)
def include_objects_in_state(
    workspace_id: UUID,
    state_id: UUID,
    payload: IncludeObjectsRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> IncludeObjectsResponse:
    """Append explicitly selected imported objects to an architecture state.

    This is the controlled enrichment path for a writable state — including the
    Current baseline while it is still a draft. Only the objects the user
    selected are placed, nothing is removed, and a locked Current refuses the
    write through the shared policy.
    """

    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Architecture state not found"
        )
    # Inclusion is a structural change, so it follows the same policy as every
    # other write: allowed while Current is a draft, refused once it is locked.
    assert_writable(state)

    nodes = [dict(node) for node in (state.nodes or [])]
    relationships = [dict(item) for item in (state.relationships or [])]
    occurrences: dict[str, str] = {
        str(node.get("object_id")): str(node.get("occurrence_id")) for node in nodes
    }
    skipped: list[IncludeObjectsSkipped] = []
    added_occurrences = 0
    added_relationships = 0
    next_index = len(nodes)

    def place(object_id: UUID, discipline: str | None = None) -> str:
        nonlocal added_occurrences, next_index
        key = str(object_id)
        if key in occurrences:
            return occurrences[key]
        occurrence_id = f"occ-{uuid4()}"
        node = ArchitectureStateNode(
            occurrence_id=occurrence_id,
            object_id=object_id,
            position=_placement(next_index),
            discipline=discipline,
        ).model_dump(mode="json")
        nodes.append(node)
        occurrences[key] = occurrence_id
        next_index += 1
        added_occurrences += 1
        return occurrence_id

    def has_relationship(source_id: str, target_id: str, integration_id: str | None) -> bool:
        for item in relationships:
            if integration_id is not None and str(item.get("integration_id")) == integration_id:
                return True
            if (
                integration_id is None
                and str(item.get("source_id")) == source_id
                and str(item.get("target_id")) == target_id
                and item.get("type") == "Contains"
            ):
                return True
        return False

    selected_systems: dict[UUID, CatalogSystem] = {}
    for system_id in payload.system_ids:
        system = db.scalar(
            select(CatalogSystem).where(
                CatalogSystem.id == system_id,
                CatalogSystem.tenant_id == workspace.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
        )
        if system is None:
            skipped.append(
                IncludeObjectsSkipped(
                    kind="system",
                    id=system_id,
                    message="System is not an active system in this workspace",
                )
            )
            continue
        selected_systems[system_id] = system

    selected_objects: dict[UUID, ArchitectureObject] = {}
    for object_id in payload.architecture_object_ids:
        registry = db.scalar(
            select(ArchitectureObject).where(
                ArchitectureObject.id == object_id,
                ArchitectureObject.tenant_id == workspace.tenant_id,
                ArchitectureObject.system_id.is_(None),
            )
        )
        if registry is None:
            skipped.append(
                IncludeObjectsSkipped(
                    kind="architecture_object",
                    id=object_id,
                    message="Architecture object is not available in this workspace",
                )
            )
            continue
        selected_objects[object_id] = registry

    selected_integrations: dict[UUID, Integration] = {}
    for integration_id in payload.integration_ids:
        integration = db.scalar(
            select(Integration).where(
                Integration.id == integration_id,
                Integration.tenant_id == workspace.tenant_id,
                Integration.deleted_at.is_(None),
            )
        )
        if integration is None:
            skipped.append(
                IncludeObjectsSkipped(
                    kind="integration",
                    id=integration_id,
                    message="Contract is not an active contract in this workspace",
                )
            )
            continue
        selected_integrations[integration_id] = integration

    for system_id in selected_systems:
        place(system_id)

    for object_id, registry in selected_objects.items():
        place(object_id, KIND_DISCIPLINE_FOR_INCLUDE.get(registry.kind))
        if registry.kind == "solution_boundary" and payload.visualize_solution_membership:
            boundary_occurrence = occurrences[str(object_id)]
            members = list(
                db.scalars(
                    select(SolutionMember.system_id).where(
                        SolutionMember.tenant_id == workspace.tenant_id,
                        SolutionMember.solution_object_id == object_id,
                    )
                )
            )
            for member_id in members:
                member_system = db.scalar(
                    select(CatalogSystem).where(
                        CatalogSystem.id == member_id,
                        CatalogSystem.tenant_id == workspace.tenant_id,
                        CatalogSystem.deleted_at.is_(None),
                    )
                )
                if member_system is None:
                    skipped.append(
                        IncludeObjectsSkipped(
                            kind="solution_member",
                            id=member_id,
                            message="A solution member system is no longer active",
                        )
                    )
                    continue
                member_occurrence = place(member_id)
                if not has_relationship(boundary_occurrence, member_occurrence, None):
                    relationships.append(
                        ArchitectureStateRelationship(
                            id=f"rel-{uuid4()}",
                            source_id=boundary_occurrence,
                            target_id=member_occurrence,
                            type="Contains",
                        ).model_dump(mode="json")
                    )
                    added_relationships += 1

    for integration_id, integration in selected_integrations.items():
        source_occurrence = occurrences.get(str(integration.source_system_id))
        target_occurrence = occurrences.get(str(integration.target_system_id))
        if source_occurrence is None or target_occurrence is None:
            skipped.append(
                IncludeObjectsSkipped(
                    kind="integration",
                    id=integration_id,
                    name=integration.name,
                    message=(
                        "Both endpoint systems must be on the canvas before this "
                        "contract can be shown"
                    ),
                )
            )
            continue
        if has_relationship(source_occurrence, target_occurrence, str(integration_id)):
            continue
        relationships.append(
            ArchitectureStateRelationship(
                id=f"rel-{uuid4()}",
                source_id=source_occurrence,
                target_id=target_occurrence,
                type="Consumes",
                name=integration.name,
                integration_id=integration_id,
            ).model_dump(mode="json")
        )
        added_relationships += 1

    state.nodes = nodes
    state.relationships = relationships
    state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(state)
    return IncludeObjectsResponse(
        state=ArchitectureStateResponse.model_validate(state),
        added_occurrences=added_occurrences,
        added_relationships=added_relationships,
        skipped=skipped,
    )
