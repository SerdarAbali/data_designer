import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    ArchitectureStateNode,
    SolutionComponentCreate,
    SolutionComponentResponse,
    SolutionComponentUpdate,
    SolutionContextResponse,
    SolutionCreate,
    SolutionDeploymentCreate,
    SolutionDeploymentResponse,
    SolutionDeploymentUpdate,
    SolutionDesignResponse,
    SolutionInterfaceCreate,
    SolutionInterfaceResponse,
    SolutionInterfaceUpdate,
    SolutionLinkRequest,
    SolutionLinkResponse,
    SolutionMemberCreate,
    SolutionMemberResponse,
    SolutionOperationCreate,
    SolutionOperationResponse,
    SolutionOperationUpdate,
    SolutionRepositoryCreate,
    SolutionRepositoryResponse,
    SolutionRepositoryUpdate,
    SolutionSummary,
    SolutionTrustBoundaryCreate,
    SolutionTrustBoundaryResponse,
    SolutionTrustBoundaryUpdate,
    SolutionUpdate,
)
from app.architecture.state_scope import (
    assert_writable as _assert_writable,
)
from app.architecture.state_scope import (
    exclude_member as _exclude_member,
)
from app.architecture.state_scope import (
    get_state as _get_state,
)
from app.architecture.state_scope import (
    node_for_object as _node_for_object,
)
from app.architecture.state_scope import (
    node_overrides as _node_overrides,
)
from app.architecture.state_scope import (
    present_in_current as _present_in_current,
)
from app.architecture.state_scope import (
    set_member_override as _set_member_override,
)
from app.architecture.state_scope import (
    state_members as _state_members,
)
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.models import (
    ArchitectureInterface,
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    ArchitectureStateMember,
    AuthSession,
    CatalogSystem,
    DataRepository,
    DeploymentNode,
    Integration,
    InterfaceOperation,
    SolutionBoundary,
    SolutionComponent,
    SolutionMember,
    TrustBoundary,
    Workspace,
)

logger = logging.getLogger("app.architecture.solution")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/solution",
    tags=["architecture"],
)

SOLUTION_KIND = "solution_boundary"
COMPONENT_KIND = "component"
INTERFACE_KIND = "interface"
OPERATION_KIND = "interface_operation"
REPOSITORY_KIND = "data_repository"
DEPLOYMENT_KIND = "deployment_node"
TRUST_KIND = "trust_boundary"

USES_REPOSITORY = "uses_repository"
DEPLOYED_ON = "deployed_on"
CROSSES = "crosses"
LINK_TYPES = (USES_REPOSITORY, DEPLOYED_ON, CROSSES)

COMPONENT_FIELDS = ("name", "description", "responsibility", "component_type", "technology")
BOUNDARY_FIELDS = ("name", "description", "owner")
INTERFACE_FIELDS = (
    "name",
    "description",
    "direction",
    "interface_kind",
    "protocol",
    "technology",
)
OPERATION_FIELDS = (
    "name",
    "description",
    "operation_kind",
    "request_object_id",
    "response_object_id",
    "ordinal",
)
REPOSITORY_FIELDS = ("name", "description", "owner", "repository_type", "technology")
DEPLOYMENT_FIELDS = ("name", "description", "technology", "environment", "hosting")
TRUST_FIELDS = ("name", "description", "security_level")


def _require_solution(workspace: Workspace) -> None:
    if "solution" not in workspace.disciplines:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )


def _get_registry(
    db: Session, workspace: Workspace, object_id: UUID, kind: str, label: str
) -> ArchitectureObject:
    registry = db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == object_id,
            ArchitectureObject.tenant_id == workspace.tenant_id,
            ArchitectureObject.kind == kind,
        )
    )
    if registry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return registry


def _get_boundary(db: Session, workspace: Workspace, object_id: UUID) -> SolutionBoundary:
    registry = _get_registry(db, workspace, object_id, SOLUTION_KIND, "Solution")
    row = db.scalar(
        select(SolutionBoundary).where(
            SolutionBoundary.object_id == registry.id,
            SolutionBoundary.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solution not found")
    return row


def _get_component(db: Session, workspace: Workspace, object_id: UUID) -> SolutionComponent:
    registry = _get_registry(db, workspace, object_id, COMPONENT_KIND, "Component")
    row = db.scalar(
        select(SolutionComponent).where(
            SolutionComponent.object_id == registry.id,
            SolutionComponent.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found")
    return row


def _get_interface(db: Session, workspace: Workspace, object_id: UUID) -> ArchitectureInterface:
    registry = _get_registry(db, workspace, object_id, INTERFACE_KIND, "Interface")
    row = db.scalar(
        select(ArchitectureInterface).where(
            ArchitectureInterface.object_id == registry.id,
            ArchitectureInterface.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interface not found")
    return row


def _get_operation(db: Session, workspace: Workspace, object_id: UUID) -> InterfaceOperation:
    registry = _get_registry(db, workspace, object_id, OPERATION_KIND, "Operation")
    row = db.scalar(
        select(InterfaceOperation).where(
            InterfaceOperation.object_id == registry.id,
            InterfaceOperation.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operation not found")
    return row


def _register_child(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    kind: str,
    object_id: UUID,
) -> None:
    db.add(ArchitectureObject(id=object_id, tenant_id=workspace.tenant_id, kind=kind))
    db.flush()
    db.add(
        ArchitectureStateMember(
            id=uuid4(),
            tenant_id=workspace.tenant_id,
            workspace_id=workspace.id,
            state_id=state.id,
            object_id=object_id,
            membership="included",
        )
    )


def _set_override(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    object_id: UUID,
    changes: dict,
) -> None:
    _set_member_override(db, workspace, state, object_id, changes)


def _node_position(state: ArchitectureState, object_id: UUID) -> dict[str, float]:
    node = _node_for_object(state, object_id)
    position = (node or {}).get("position") or {}
    return {"x": float(position.get("x", 0.0)), "y": float(position.get("y", 0.0))}


def _node_occurrence(state: ArchitectureState, object_id: UUID) -> str:
    node = _node_for_object(state, object_id)
    return str((node or {}).get("occurrence_id", ""))


def _effective(row, fields: tuple[str, ...], overrides: dict) -> dict:
    result: dict = {}
    for field in fields:
        if field in overrides:
            result[field] = overrides[field]
        else:
            result[field] = getattr(row, field, None)
    return result


def _as_uuid(value) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _member_response(system: CatalogSystem) -> SolutionMemberResponse:
    return SolutionMemberResponse(system_id=system.id, name=system.name, kind=system.kind)


def _operation_response(operation: InterfaceOperation, member) -> SolutionOperationResponse:
    overrides = member.property_overrides if member is not None else {}
    values = _effective(operation, OPERATION_FIELDS, overrides)
    return SolutionOperationResponse(
        object_id=operation.object_id,
        interface_object_id=operation.interface_object_id,
        name=values["name"],
        description=values["description"],
        operation_kind=values["operation_kind"] or "operation",
        request_object_id=_as_uuid(values["request_object_id"]),
        response_object_id=_as_uuid(values["response_object_id"]),
        ordinal=int(values["ordinal"] or 0),
        created_in_state_id=operation.created_in_state_id,
    )


def _interface_response(
    interface: ArchitectureInterface,
    member,
    operations: list[SolutionOperationResponse],
) -> SolutionInterfaceResponse:
    overrides = member.property_overrides if member is not None else {}
    values = _effective(interface, INTERFACE_FIELDS, overrides)
    return SolutionInterfaceResponse(
        object_id=interface.object_id,
        component_object_id=interface.component_object_id,
        name=values["name"],
        description=values["description"],
        direction=values["direction"] or "provided",
        interface_kind=values["interface_kind"],
        protocol=values["protocol"],
        technology=values["technology"],
        created_in_state_id=interface.created_in_state_id,
        operations=operations,
    )


def _component_response(
    component: SolutionComponent,
    state: ArchitectureState,
    member,
    interfaces: list[SolutionInterfaceResponse],
) -> SolutionComponentResponse:
    overrides = (
        member.property_overrides
        if member is not None
        else _node_overrides(state, component.object_id)
    )
    values = _effective(component, COMPONENT_FIELDS, overrides)
    return SolutionComponentResponse(
        object_id=component.object_id,
        occurrence_id=_node_occurrence(state, component.object_id),
        solution_object_id=component.solution_object_id,
        parent_component_object_id=component.parent_component_object_id,
        name=values["name"],
        description=values["description"],
        responsibility=values["responsibility"],
        component_type=values["component_type"],
        technology=values["technology"],
        position=_node_position(state, component.object_id),
        created_in_state_id=component.created_in_state_id,
        interfaces=interfaces,
    )


def _repository_response(row: DataRepository, member) -> SolutionRepositoryResponse:
    overrides = member.property_overrides if member is not None else {}
    values = _effective(row, REPOSITORY_FIELDS, overrides)
    return SolutionRepositoryResponse(
        object_id=row.object_id,
        solution_object_id=row.solution_object_id,
        name=values["name"],
        description=values["description"],
        owner=values["owner"],
        repository_type=values["repository_type"],
        technology=values["technology"],
        created_in_state_id=row.created_in_state_id,
    )


def _deployment_response(row: DeploymentNode, member) -> SolutionDeploymentResponse:
    overrides = member.property_overrides if member is not None else {}
    values = _effective(row, DEPLOYMENT_FIELDS, overrides)
    return SolutionDeploymentResponse(
        object_id=row.object_id,
        solution_object_id=row.solution_object_id,
        name=values["name"],
        description=values["description"],
        technology=values["technology"],
        environment=values["environment"],
        hosting=values["hosting"],
        created_in_state_id=row.created_in_state_id,
    )


def _trust_response(row: TrustBoundary, member) -> SolutionTrustBoundaryResponse:
    overrides = member.property_overrides if member is not None else {}
    values = _effective(row, TRUST_FIELDS, overrides)
    return SolutionTrustBoundaryResponse(
        object_id=row.object_id,
        solution_object_id=row.solution_object_id,
        name=values["name"],
        description=values["description"],
        security_level=values["security_level"],
        created_in_state_id=row.created_in_state_id,
    )


def _visible(child, state: ArchitectureState, member) -> bool:
    if member is not None and member.membership == "excluded":
        return False
    if member is not None:
        return True
    return child.created_in_state_id in (None, state.id)


def _boundary_overrides(state: ArchitectureState, members: dict, object_id: UUID) -> dict:
    """Solution boundaries write overrides to a state-member (like every other
    solution child); fall back to node overrides for legacy data."""
    member = members.get(object_id)
    if member is not None and member.property_overrides:
        return dict(member.property_overrides)
    return _node_overrides(state, object_id)


def _build_design(
    db: Session, workspace: Workspace, state: ArchitectureState, boundary: SolutionBoundary
) -> SolutionDesignResponse:
    members = _state_members(db, state)
    solution_id = boundary.object_id

    component_rows = list(
        db.scalars(
            select(SolutionComponent).where(
                SolutionComponent.tenant_id == workspace.tenant_id,
                SolutionComponent.solution_object_id == solution_id,
            )
        )
    )
    component_rows = [
        row
        for row in component_rows
        if _node_for_object(state, row.object_id) is not None
        and _visible(row, state, members.get(row.object_id))
    ]
    component_ids = [row.object_id for row in component_rows]

    interface_rows = (
        list(
            db.scalars(
                select(ArchitectureInterface).where(
                    ArchitectureInterface.tenant_id == workspace.tenant_id,
                    ArchitectureInterface.component_object_id.in_(component_ids),
                )
            )
        )
        if component_ids
        else []
    )
    interface_rows = [
        row for row in interface_rows if _visible(row, state, members.get(row.object_id))
    ]
    interface_ids = [row.object_id for row in interface_rows]

    operation_rows = (
        list(
            db.scalars(
                select(InterfaceOperation).where(
                    InterfaceOperation.tenant_id == workspace.tenant_id,
                    InterfaceOperation.interface_object_id.in_(interface_ids),
                )
            )
        )
        if interface_ids
        else []
    )
    operation_rows = [
        row for row in operation_rows if _visible(row, state, members.get(row.object_id))
    ]
    operation_rows.sort(key=lambda row: (row.ordinal, row.name))

    operations_by_interface: dict[UUID, list[SolutionOperationResponse]] = {
        iid: [] for iid in interface_ids
    }
    for row in operation_rows:
        operations_by_interface[row.interface_object_id].append(
            _operation_response(row, members.get(row.object_id))
        )

    interfaces_by_component: dict[UUID, list[SolutionInterfaceResponse]] = {
        cid: [] for cid in component_ids
    }
    for row in interface_rows:
        if row.component_object_id is None:
            continue
        interfaces_by_component[row.component_object_id].append(
            _interface_response(
                row,
                members.get(row.object_id),
                operations_by_interface.get(row.object_id, []),
            )
        )
    for items in interfaces_by_component.values():
        items.sort(key=lambda item: (item.direction, item.name))

    components = [
        _component_response(
            row,
            state,
            members.get(row.object_id),
            interfaces_by_component.get(row.object_id, []),
        )
        for row in component_rows
    ]
    components.sort(key=lambda item: item.name)

    def _children(model, response):
        return [
            response(row, members.get(row.object_id))
            for row in db.scalars(
                select(model).where(
                    model.tenant_id == workspace.tenant_id,
                    model.solution_object_id == solution_id,
                )
            )
            if _visible(row, state, members.get(row.object_id))
        ]

    repositories = sorted(_children(DataRepository, _repository_response), key=lambda r: r.name)
    deployment_nodes = sorted(_children(DeploymentNode, _deployment_response), key=lambda r: r.name)
    trust_boundaries = sorted(_children(TrustBoundary, _trust_response), key=lambda r: r.name)

    known_ids = {solution_id, *component_ids, *interface_ids}
    known_ids.update(row.object_id for row in operation_rows)
    known_ids.update(row.object_id for row in [*repositories, *deployment_nodes, *trust_boundaries])
    links: list[SolutionLinkResponse] = []
    relationship_rows = list(
        db.scalars(
            select(ArchitectureRelationship).where(
                ArchitectureRelationship.tenant_id == workspace.tenant_id,
                ArchitectureRelationship.relationship_type.in_(LINK_TYPES),
            )
        )
    )
    for edge in relationship_rows:
        if edge.created_in_state_id not in (None, state.id):
            continue
        if edge.source_object_id not in known_ids and edge.target_object_id not in known_ids:
            continue
        links.append(
            SolutionLinkResponse(
                id=edge.id,
                source_object_id=edge.source_object_id,
                target_object_id=edge.target_object_id,
                relationship_type=edge.relationship_type,
            )
        )

    overrides = _boundary_overrides(state, members, solution_id)
    boundary_values = _effective(boundary, BOUNDARY_FIELDS, overrides)
    boundary_members = list(
        db.scalars(
            select(SolutionMember).where(
                SolutionMember.tenant_id == workspace.tenant_id,
                SolutionMember.solution_object_id == solution_id,
                SolutionMember.created_in_state_id.in_([None, state.id]),
            )
        )
    )
    member_ids = {row.system_id for row in boundary_members}
    member_responses: list[SolutionMemberResponse] = []
    for member_row in boundary_members:
        system = db.get(CatalogSystem, member_row.system_id)
        if system is not None and system.deleted_at is None:
            member_responses.append(_member_response(system))
    external: list[SolutionMemberResponse] = []
    for node in state.nodes:
        object_id = _as_uuid(node.get("object_id"))
        if object_id is None or object_id in member_ids:
            continue
        system = db.get(CatalogSystem, object_id)
        if (
            system is not None
            and system.deleted_at is None
            and system.tenant_id == workspace.tenant_id
        ):
            external.append(_member_response(system))

    solution_context = SolutionContextResponse(
        solution_object_id=solution_id,
        occurrence_id=_node_occurrence(state, solution_id),
        name=boundary_values["name"],
        description=boundary_values["description"],
        owner=boundary_values["owner"],
        position=_node_position(state, solution_id),
        members=sorted(member_responses, key=lambda item: item.name),
        external_systems=sorted(external, key=lambda item: item.name),
    )

    return SolutionDesignResponse(
        state_id=state.id,
        state_type=state.state_type,
        editable=state.state_type != "current",
        solution=solution_context,
        components=components,
        repositories=repositories,
        deployment_nodes=deployment_nodes,
        trust_boundaries=trust_boundaries,
        links=links,
    )


@router.get("/solutions", response_model=list[SolutionSummary])
def list_solutions(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[SolutionSummary]:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, state_id)
    members = _state_members(db, state)
    summaries: list[SolutionSummary] = []
    for node in state.nodes:
        object_id = _as_uuid(node.get("object_id"))
        if object_id is None:
            continue
        registry = db.get(ArchitectureObject, object_id)
        if registry is None or registry.kind != SOLUTION_KIND:
            continue
        boundary = db.scalar(
            select(SolutionBoundary).where(
                SolutionBoundary.object_id == object_id,
                SolutionBoundary.tenant_id == workspace.tenant_id,
            )
        )
        if boundary is None:
            continue
        component_count = len(
            list(
                db.scalars(
                    select(SolutionComponent.object_id).where(
                        SolutionComponent.tenant_id == workspace.tenant_id,
                        SolutionComponent.solution_object_id == object_id,
                    )
                )
            )
        )
        member_count = len(
            list(
                db.scalars(
                    select(SolutionMember.id).where(
                        SolutionMember.tenant_id == workspace.tenant_id,
                        SolutionMember.solution_object_id == object_id,
                        SolutionMember.created_in_state_id.in_([None, state.id]),
                    )
                )
            )
        )
        overrides = _boundary_overrides(state, members, object_id)
        values = _effective(boundary, BOUNDARY_FIELDS, overrides)
        summaries.append(
            SolutionSummary(
                object_id=object_id,
                occurrence_id=str(node.get("occurrence_id")),
                name=values["name"],
                description=values["description"],
                component_count=component_count,
                member_count=member_count,
            )
        )
    summaries.sort(key=lambda item: item.name)
    return summaries


@router.get("/solutions/{solution_object_id}/design", response_model=SolutionDesignResponse)
def get_solution_design(
    workspace_id: UUID,
    solution_object_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, state_id)
    boundary = _get_boundary(db, workspace, solution_object_id)
    return _build_design(db, workspace, state, boundary)


@router.get(
    "/solutions/{solution_object_id}/components/{component_object_id}",
    response_model=SolutionComponentResponse,
)
def get_solution_component(
    workspace_id: UUID,
    solution_object_id: UUID,
    component_object_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionComponentResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, state_id)
    _get_boundary(db, workspace, solution_object_id)
    design = _build_design(db, workspace, state, _get_boundary(db, workspace, solution_object_id))
    for component in design.components:
        if component.object_id == component_object_id:
            return component
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Component not found in this solution state",
    )


@router.post(
    "/solutions",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution(
    workspace_id: UUID,
    payload: SolutionCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)

    object_id = uuid4()
    registry = ArchitectureObject(id=object_id, tenant_id=workspace.tenant_id, kind=SOLUTION_KIND)
    boundary = SolutionBoundary(
        object_id=object_id,
        tenant_id=workspace.tenant_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        owner=payload.owner.strip() if payload.owner else None,
    )
    node = ArchitectureStateNode(
        occurrence_id=f"occ-{uuid4()}",
        object_id=object_id,
        position=payload.position,
        discipline="solution",
    ).model_dump(mode="json")
    nodes = list(state.nodes)
    nodes.append(node)
    db.add(registry)
    db.flush()
    db.add(boundary)
    state.nodes = nodes
    state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(boundary)
    db.refresh(state)
    logger.info(
        "solution created workspace=%s object=%s state=%s", workspace.id, object_id, state.id
    )
    return _build_design(db, workspace, state, boundary)


@router.patch("/solutions/{solution_object_id}", response_model=SolutionDesignResponse)
def update_solution(
    workspace_id: UUID,
    solution_object_id: UUID,
    state_id: UUID,
    payload: SolutionUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    changes = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if key in BOUNDARY_FIELDS
    }
    if _present_in_current(db, workspace, solution_object_id):
        _set_override(db, workspace, state, solution_object_id, changes)
    else:
        for field, value in changes.items():
            setattr(boundary, field, value.strip() if isinstance(value, str) and value else value)
    db.commit()
    db.refresh(state)
    db.refresh(boundary)
    logger.info(
        "solution updated workspace=%s object=%s state=%s",
        workspace.id,
        solution_object_id,
        state.id,
    )
    return _build_design(db, workspace, state, boundary)


@router.post(
    "/solutions/{solution_object_id}/members",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_solution_member(
    workspace_id: UUID,
    solution_object_id: UUID,
    payload: SolutionMemberCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    system = db.scalar(
        select(CatalogSystem).where(
            CatalogSystem.id == payload.system_id,
            CatalogSystem.tenant_id == workspace.tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    )
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System not found")
    existing = db.scalar(
        select(SolutionMember).where(
            SolutionMember.solution_object_id == solution_object_id,
            SolutionMember.system_id == system.id,
            SolutionMember.created_in_state_id.in_([None, state.id]),
        )
    )
    if existing is None:
        db.add(
            SolutionMember(
                id=uuid4(),
                tenant_id=workspace.tenant_id,
                solution_object_id=solution_object_id,
                system_id=system.id,
                created_in_state_id=state.id,
            )
        )
    if _node_for_object(state, system.id) is None:
        nodes = list(state.nodes)
        nodes.append(
            ArchitectureStateNode(
                occurrence_id=f"occ-{uuid4()}",
                object_id=system.id,
                position=payload.position or {"x": 420.0, "y": 420.0},
                discipline="solution",
            ).model_dump(mode="json")
        )
        state.nodes = nodes
        state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(state)
    logger.info(
        "solution member added workspace=%s solution=%s system=%s",
        workspace.id,
        solution_object_id,
        system.id,
    )
    return _build_design(db, workspace, state, boundary)


@router.delete(
    "/solutions/{solution_object_id}/members/{system_id}",
    response_model=SolutionDesignResponse,
)
def remove_solution_member(
    workspace_id: UUID,
    solution_object_id: UUID,
    system_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    db.execute(
        delete(SolutionMember).where(
            SolutionMember.solution_object_id == solution_object_id,
            SolutionMember.system_id == system_id,
            SolutionMember.created_in_state_id == state.id,
        )
    )
    remaining = list(state.nodes)
    filtered = [node for node in remaining if str(node.get("object_id")) != str(system_id)]
    if len(filtered) != len(remaining):
        state.nodes = filtered
        state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(state)
    logger.info(
        "solution member removed workspace=%s solution=%s system=%s",
        workspace.id,
        solution_object_id,
        system_id,
    )
    return _build_design(db, workspace, state, boundary)


def _create_node_object(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    kind: str,
    position: dict[str, float],
    discipline: str = "solution",
) -> UUID:
    object_id = uuid4()
    db.add(ArchitectureObject(id=object_id, tenant_id=workspace.tenant_id, kind=kind))
    db.flush()
    nodes = list(state.nodes)
    nodes.append(
        ArchitectureStateNode(
            occurrence_id=f"occ-{uuid4()}",
            object_id=object_id,
            position=position,
            discipline=discipline,
        ).model_dump(mode="json")
    )
    state.nodes = nodes
    state.updated_at = datetime.now(UTC)
    return object_id


@router.post(
    "/solutions/{solution_object_id}/components",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_component(
    workspace_id: UUID,
    solution_object_id: UUID,
    payload: SolutionComponentCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    if payload.parent_component_object_id is not None:
        _get_component(db, workspace, payload.parent_component_object_id)
    duplicate = db.scalar(
        select(SolutionComponent.object_id).where(
            SolutionComponent.tenant_id == workspace.tenant_id,
            SolutionComponent.solution_object_id == solution_object_id,
            SolutionComponent.name == payload.name.strip(),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A component with this name already exists in the solution",
        )
    object_id = _create_node_object(db, workspace, state, COMPONENT_KIND, payload.position)
    db.add(
        SolutionComponent(
            object_id=object_id,
            tenant_id=workspace.tenant_id,
            solution_object_id=solution_object_id,
            parent_component_object_id=payload.parent_component_object_id,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            responsibility=payload.responsibility.strip() if payload.responsibility else None,
            component_type=payload.component_type,
            technology=payload.technology.strip() if payload.technology else None,
            created_in_state_id=state.id,
        )
    )
    db.commit()
    db.refresh(state)
    logger.info(
        "solution component created workspace=%s solution=%s object=%s",
        workspace.id,
        solution_object_id,
        object_id,
    )
    return _build_design(db, workspace, state, boundary)


@router.patch("/components/{component_object_id}", response_model=SolutionDesignResponse)
def update_solution_component(
    workspace_id: UUID,
    component_object_id: UUID,
    payload: SolutionComponentUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    component = _get_component(db, workspace, component_object_id)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    changes = {key: value for key, value in changes.items() if key in COMPONENT_FIELDS}
    if state_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="state_id is required to scope a component edit",
        )
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if _present_in_current(db, workspace, component_object_id):
        _set_override(db, workspace, state, component_object_id, changes)
    else:
        for field, value in changes.items():
            setattr(component, field, value.strip() if isinstance(value, str) and value else value)
    db.commit()
    db.refresh(state)
    logger.info(
        "solution component updated workspace=%s object=%s state=%s",
        workspace.id,
        component_object_id,
        state.id,
    )
    boundary = _boundary_for_component(db, workspace, component)
    return _build_design(db, workspace, state, boundary)


@router.delete("/components/{component_object_id}", response_model=SolutionDesignResponse)
def delete_solution_component(
    workspace_id: UUID,
    component_object_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    component = _get_component(db, workspace, component_object_id)
    solution_id = component.solution_object_id
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if component.created_in_state_id == state.id:
        for interface in db.scalars(
            select(ArchitectureInterface).where(
                ArchitectureInterface.tenant_id == workspace.tenant_id,
                ArchitectureInterface.component_object_id == component_object_id,
            )
        ):
            for operation in db.scalars(
                select(InterfaceOperation).where(
                    InterfaceOperation.tenant_id == workspace.tenant_id,
                    InterfaceOperation.interface_object_id == interface.object_id,
                )
            ):
                _purge_object(db, workspace, operation.object_id)
            _purge_object(db, workspace, interface.object_id)
        _purge_object(db, workspace, component_object_id)
    state.nodes = [
        node for node in state.nodes if str(node.get("object_id")) != str(component_object_id)
    ]
    state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(state)
    logger.info(
        "solution component deleted workspace=%s object=%s state=%s",
        workspace.id,
        component_object_id,
        state.id,
    )
    boundary = _get_boundary(db, workspace, solution_id)
    return _build_design(db, workspace, state, boundary)


def _purge_object(db: Session, workspace: Workspace, object_id: UUID) -> None:
    for edge in db.scalars(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            (ArchitectureRelationship.source_object_id == object_id)
            | (ArchitectureRelationship.target_object_id == object_id),
        )
    ):
        db.delete(edge)
    db.execute(
        delete(ArchitectureStateMember).where(ArchitectureStateMember.object_id == object_id)
    )
    # Detach any contract interface links so RESTRICT referential integrity does
    # not block removing an interface that is no longer available in the design.
    db.execute(
        update(Integration)
        .where(
            Integration.tenant_id == workspace.tenant_id,
            Integration.producer_interface_id == object_id,
        )
        .values(producer_interface_id=None)
    )
    db.execute(
        update(Integration)
        .where(
            Integration.tenant_id == workspace.tenant_id,
            Integration.consumer_interface_id == object_id,
        )
        .values(consumer_interface_id=None)
    )
    registry = db.get(ArchitectureObject, object_id)
    if registry is not None:
        db.delete(registry)


@router.post(
    "/components/{component_object_id}/interfaces",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_interface(
    workspace_id: UUID,
    component_object_id: UUID,
    payload: SolutionInterfaceCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    component = _get_component(db, workspace, component_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    duplicate = db.scalar(
        select(ArchitectureInterface.object_id).where(
            ArchitectureInterface.tenant_id == workspace.tenant_id,
            ArchitectureInterface.component_object_id == component_object_id,
            ArchitectureInterface.name == payload.name.strip(),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An interface with this name already exists on the component",
        )
    object_id = uuid4()
    _register_child(db, workspace, state, INTERFACE_KIND, object_id)
    db.add(
        ArchitectureInterface(
            object_id=object_id,
            tenant_id=workspace.tenant_id,
            component_object_id=component_object_id,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            direction=payload.direction,
            interface_kind=payload.interface_kind,
            protocol=payload.protocol,
            technology=payload.technology,
            created_in_state_id=state.id,
        )
    )
    db.commit()
    db.refresh(state)
    logger.info(
        "solution interface created workspace=%s component=%s object=%s",
        workspace.id,
        component_object_id,
        object_id,
    )
    boundary = _boundary_for_component(db, workspace, component)
    return _build_design(db, workspace, state, boundary)


@router.patch("/interfaces/{interface_object_id}", response_model=SolutionDesignResponse)
def update_solution_interface(
    workspace_id: UUID,
    interface_object_id: UUID,
    payload: SolutionInterfaceUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    interface = _get_interface(db, workspace, interface_object_id)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    changes = {key: value for key, value in changes.items() if key in INTERFACE_FIELDS}
    if state_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="state_id is required to scope an interface edit",
        )
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if interface.created_in_state_id is None and _present_in_current(
        db, workspace, interface.component_object_id
    ):
        _set_override(db, workspace, state, interface_object_id, changes)
    else:
        for field, value in changes.items():
            setattr(interface, field, value.strip() if isinstance(value, str) and value else value)
    db.commit()
    db.refresh(state)
    logger.info(
        "solution interface updated workspace=%s object=%s state=%s",
        workspace.id,
        interface_object_id,
        state.id,
    )
    boundary = _boundary_for_interface(db, workspace, interface)
    return _build_design(db, workspace, state, boundary)


@router.delete("/interfaces/{interface_object_id}", response_model=SolutionDesignResponse)
def delete_solution_interface(
    workspace_id: UUID,
    interface_object_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    interface = _get_interface(db, workspace, interface_object_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if interface.created_in_state_id == state.id:
        for operation in db.scalars(
            select(InterfaceOperation).where(
                InterfaceOperation.interface_object_id == interface_object_id,
                InterfaceOperation.tenant_id == workspace.tenant_id,
            )
        ):
            _purge_object(db, workspace, operation.object_id)
        _purge_object(db, workspace, interface_object_id)
    else:
        _set_override(db, workspace, state, interface_object_id, {})
        member = db.scalar(
            select(ArchitectureStateMember).where(
                ArchitectureStateMember.state_id == state.id,
                ArchitectureStateMember.object_id == interface_object_id,
            )
        )
        if member is None:
            db.add(
                ArchitectureStateMember(
                    id=uuid4(),
                    tenant_id=workspace.tenant_id,
                    workspace_id=workspace.id,
                    state_id=state.id,
                    object_id=interface_object_id,
                    membership="excluded",
                )
            )
        else:
            member.membership = "excluded"
    db.commit()
    db.refresh(state)
    boundary = _boundary_for_interface(db, workspace, interface)
    return _build_design(db, workspace, state, boundary)


@router.post(
    "/interfaces/{interface_object_id}/operations",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_operation(
    workspace_id: UUID,
    interface_object_id: UUID,
    payload: SolutionOperationCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    interface = _get_interface(db, workspace, interface_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    duplicate = db.scalar(
        select(InterfaceOperation.object_id).where(
            InterfaceOperation.tenant_id == workspace.tenant_id,
            InterfaceOperation.interface_object_id == interface_object_id,
            InterfaceOperation.name == payload.name.strip(),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An operation with this name already exists on the interface",
        )
    object_id = uuid4()
    _register_child(db, workspace, state, OPERATION_KIND, object_id)
    db.add(
        InterfaceOperation(
            object_id=object_id,
            tenant_id=workspace.tenant_id,
            interface_object_id=interface_object_id,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            operation_kind=payload.operation_kind,
            request_object_id=payload.request_object_id,
            response_object_id=payload.response_object_id,
            ordinal=payload.ordinal,
            created_in_state_id=state.id,
        )
    )
    db.commit()
    db.refresh(state)
    logger.info(
        "solution operation created workspace=%s interface=%s object=%s",
        workspace.id,
        interface_object_id,
        object_id,
    )
    boundary = _boundary_for_interface(db, workspace, interface)
    return _build_design(db, workspace, state, boundary)


def _boundary_for_component(
    db: Session, workspace: Workspace, component: SolutionComponent
) -> SolutionBoundary:
    if component.solution_object_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This component is not attached to a solution boundary",
        )
    return _get_boundary(db, workspace, component.solution_object_id)


def _boundary_for_interface(
    db: Session, workspace: Workspace, interface: ArchitectureInterface
) -> SolutionBoundary:
    component = db.scalar(
        select(SolutionComponent).where(
            SolutionComponent.object_id == interface.component_object_id,
            SolutionComponent.tenant_id == workspace.tenant_id,
        )
    )
    if component is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found")
    return _boundary_for_component(db, workspace, component)


@router.patch("/operations/{operation_object_id}", response_model=SolutionDesignResponse)
def update_solution_operation(
    workspace_id: UUID,
    operation_object_id: UUID,
    payload: SolutionOperationUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    operation = _get_operation(db, workspace, operation_object_id)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    changes = {key: value for key, value in changes.items() if key in OPERATION_FIELDS}
    if state_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="state_id is required to scope an operation edit",
        )
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if operation.created_in_state_id is None and _present_in_current(
        db, workspace, operation.interface_object_id
    ):
        _set_override(db, workspace, state, operation_object_id, changes)
    else:
        for field, value in changes.items():
            setattr(operation, field, value.strip() if isinstance(value, str) and value else value)
    db.commit()
    db.refresh(state)
    interface = _get_interface(db, workspace, operation.interface_object_id)
    boundary = _boundary_for_interface(db, workspace, interface)
    logger.info(
        "solution operation updated workspace=%s object=%s state=%s",
        workspace.id,
        operation_object_id,
        state.id,
    )
    return _build_design(db, workspace, state, boundary)


@router.delete("/operations/{operation_object_id}", response_model=SolutionDesignResponse)
def delete_solution_operation(
    workspace_id: UUID,
    operation_object_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    operation = _get_operation(db, workspace, operation_object_id)
    interface = _get_interface(db, workspace, operation.interface_object_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if operation.created_in_state_id == state.id:
        _purge_object(db, workspace, operation_object_id)
        db.delete(operation)
    else:
        member = db.scalar(
            select(ArchitectureStateMember).where(
                ArchitectureStateMember.state_id == state.id,
                ArchitectureStateMember.object_id == operation_object_id,
            )
        )
        if member is None:
            db.add(
                ArchitectureStateMember(
                    id=uuid4(),
                    tenant_id=workspace.tenant_id,
                    workspace_id=workspace.id,
                    state_id=state.id,
                    object_id=operation_object_id,
                    membership="excluded",
                )
            )
        else:
            member.membership = "excluded"
    db.commit()
    db.refresh(state)
    boundary = _boundary_for_interface(db, workspace, interface)
    return _build_design(db, workspace, state, boundary)


def _create_solution_child(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    solution_id: UUID,
    model,
    kind: str,
    values: dict,
):
    duplicate = db.scalar(
        select(model.object_id).where(
            model.tenant_id == workspace.tenant_id,
            model.solution_object_id == solution_id,
            model.name == values["name"],
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {kind.replace('_', ' ')} with this name already exists",
        )
    object_id = uuid4()
    _register_child(db, workspace, state, kind, object_id)
    row = model(
        object_id=object_id, tenant_id=workspace.tenant_id, solution_object_id=solution_id, **values
    )
    db.add(row)
    return object_id


@router.post(
    "/solutions/{solution_object_id}/repositories",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_repository(
    workspace_id: UUID,
    solution_object_id: UUID,
    payload: SolutionRepositoryCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    object_id = _create_solution_child(
        db,
        workspace,
        state,
        solution_object_id,
        DataRepository,
        REPOSITORY_KIND,
        {
            "name": payload.name.strip(),
            "description": payload.description.strip() if payload.description else None,
            "owner": payload.owner.strip() if payload.owner else None,
            "repository_type": payload.repository_type,
            "technology": payload.technology,
            "created_in_state_id": state.id,
        },
    )
    db.commit()
    db.refresh(state)
    logger.info(
        "solution repository created workspace=%s solution=%s object=%s",
        workspace.id,
        solution_object_id,
        object_id,
    )
    return _build_design(db, workspace, state, boundary)


def _get_repository(db: Session, workspace: Workspace, object_id: UUID) -> DataRepository:
    _get_registry(db, workspace, object_id, REPOSITORY_KIND, "Repository")
    row = db.scalar(
        select(DataRepository).where(
            DataRepository.object_id == object_id,
            DataRepository.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return row


@router.patch("/repositories/{repository_object_id}", response_model=SolutionDesignResponse)
def update_solution_repository(
    workspace_id: UUID,
    repository_object_id: UUID,
    payload: SolutionRepositoryUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    row = _get_repository(db, workspace, repository_object_id)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    changes = {key: value for key, value in changes.items() if key in REPOSITORY_FIELDS}
    if state_id is None:
        raise HTTPException(status_code=422, detail="state_id is required")
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if row.created_in_state_id is None and _present_in_current(
        db, workspace, row.solution_object_id
    ):
        _set_override(db, workspace, state, repository_object_id, changes)
    else:
        for field, value in changes.items():
            setattr(row, field, value.strip() if isinstance(value, str) and value else value)
    db.commit()
    db.refresh(state)
    boundary = _get_boundary(db, workspace, row.solution_object_id)
    return _build_design(db, workspace, state, boundary)


@router.delete("/repositories/{repository_object_id}", response_model=SolutionDesignResponse)
def delete_solution_repository(
    workspace_id: UUID,
    repository_object_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    row = _get_repository(db, workspace, repository_object_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if row.created_in_state_id == state.id:
        _purge_object(db, workspace, repository_object_id)
    else:
        _exclude_member(db, workspace, state, repository_object_id)
    db.commit()
    db.refresh(state)
    boundary = _get_boundary(db, workspace, row.solution_object_id)
    return _build_design(db, workspace, state, boundary)


@router.post(
    "/solutions/{solution_object_id}/deployment-nodes",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_deployment(
    workspace_id: UUID,
    solution_object_id: UUID,
    payload: SolutionDeploymentCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    object_id = _create_solution_child(
        db,
        workspace,
        state,
        solution_object_id,
        DeploymentNode,
        DEPLOYMENT_KIND,
        {
            "name": payload.name.strip(),
            "description": payload.description.strip() if payload.description else None,
            "technology": payload.technology,
            "environment": payload.environment,
            "hosting": payload.hosting,
            "created_in_state_id": state.id,
        },
    )
    db.commit()
    db.refresh(state)
    logger.info(
        "solution deployment created workspace=%s solution=%s object=%s",
        workspace.id,
        solution_object_id,
        object_id,
    )
    return _build_design(db, workspace, state, boundary)


def _get_deployment(db: Session, workspace: Workspace, object_id: UUID) -> DeploymentNode:
    _get_registry(db, workspace, object_id, DEPLOYMENT_KIND, "Deployment node")
    row = db.scalar(
        select(DeploymentNode).where(
            DeploymentNode.object_id == object_id,
            DeploymentNode.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Deployment node not found"
        )
    return row


@router.patch("/deployment-nodes/{deployment_object_id}", response_model=SolutionDesignResponse)
def update_solution_deployment(
    workspace_id: UUID,
    deployment_object_id: UUID,
    payload: SolutionDeploymentUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    row = _get_deployment(db, workspace, deployment_object_id)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    changes = {key: value for key, value in changes.items() if key in DEPLOYMENT_FIELDS}
    if state_id is None:
        raise HTTPException(status_code=422, detail="state_id is required")
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if row.created_in_state_id is None and _present_in_current(
        db, workspace, row.solution_object_id
    ):
        _set_override(db, workspace, state, deployment_object_id, changes)
    else:
        for field, value in changes.items():
            setattr(row, field, value.strip() if isinstance(value, str) and value else value)
    db.commit()
    db.refresh(state)
    boundary = _get_boundary(db, workspace, row.solution_object_id)
    return _build_design(db, workspace, state, boundary)


@router.delete("/deployment-nodes/{deployment_object_id}", response_model=SolutionDesignResponse)
def delete_solution_deployment(
    workspace_id: UUID,
    deployment_object_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    row = _get_deployment(db, workspace, deployment_object_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if row.created_in_state_id == state.id:
        _purge_object(db, workspace, deployment_object_id)
    else:
        _exclude_member(db, workspace, state, deployment_object_id)
    db.commit()
    db.refresh(state)
    boundary = _get_boundary(db, workspace, row.solution_object_id)
    return _build_design(db, workspace, state, boundary)


@router.post(
    "/solutions/{solution_object_id}/trust-boundaries",
    response_model=SolutionDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_trust_boundary(
    workspace_id: UUID,
    solution_object_id: UUID,
    payload: SolutionTrustBoundaryCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    boundary = _get_boundary(db, workspace, solution_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    object_id = _create_solution_child(
        db,
        workspace,
        state,
        solution_object_id,
        TrustBoundary,
        TRUST_KIND,
        {
            "name": payload.name.strip(),
            "description": payload.description.strip() if payload.description else None,
            "security_level": payload.security_level,
            "created_in_state_id": state.id,
        },
    )
    db.commit()
    db.refresh(state)
    logger.info(
        "solution trust boundary created workspace=%s solution=%s object=%s",
        workspace.id,
        solution_object_id,
        object_id,
    )
    return _build_design(db, workspace, state, boundary)


def _get_trust(db: Session, workspace: Workspace, object_id: UUID) -> TrustBoundary:
    _get_registry(db, workspace, object_id, TRUST_KIND, "Trust boundary")
    row = db.scalar(
        select(TrustBoundary).where(
            TrustBoundary.object_id == object_id,
            TrustBoundary.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trust boundary not found"
        )
    return row


@router.patch("/trust-boundaries/{trust_object_id}", response_model=SolutionDesignResponse)
def update_solution_trust_boundary(
    workspace_id: UUID,
    trust_object_id: UUID,
    payload: SolutionTrustBoundaryUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    row = _get_trust(db, workspace, trust_object_id)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    changes = {key: value for key, value in changes.items() if key in TRUST_FIELDS}
    if state_id is None:
        raise HTTPException(status_code=422, detail="state_id is required")
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if row.created_in_state_id is None and _present_in_current(
        db, workspace, row.solution_object_id
    ):
        _set_override(db, workspace, state, trust_object_id, changes)
    else:
        for field, value in changes.items():
            setattr(row, field, value.strip() if isinstance(value, str) and value else value)
    db.commit()
    db.refresh(state)
    boundary = _get_boundary(db, workspace, row.solution_object_id)
    return _build_design(db, workspace, state, boundary)


@router.delete("/trust-boundaries/{trust_object_id}", response_model=SolutionDesignResponse)
def delete_solution_trust_boundary(
    workspace_id: UUID,
    trust_object_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    row = _get_trust(db, workspace, trust_object_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if row.created_in_state_id == state.id:
        _purge_object(db, workspace, trust_object_id)
    else:
        _exclude_member(db, workspace, state, trust_object_id)
    db.commit()
    db.refresh(state)
    boundary = _get_boundary(db, workspace, row.solution_object_id)
    return _build_design(db, workspace, state, boundary)


def _replace_link(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    source_object_id: UUID,
    link_type: str,
    target_object_id: UUID | None,
) -> None:
    for edge in db.scalars(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            ArchitectureRelationship.source_object_id == source_object_id,
            ArchitectureRelationship.relationship_type == link_type,
        )
    ):
        if edge.created_in_state_id in (None, state.id):
            db.delete(edge)
    if target_object_id is not None:
        db.add(
            ArchitectureRelationship(
                id=uuid4(),
                tenant_id=workspace.tenant_id,
                source_object_id=source_object_id,
                target_object_id=target_object_id,
                relationship_type=link_type,
                properties={},
                created_in_state_id=state.id,
            )
        )


@router.put("/components/{component_object_id}/repository", response_model=SolutionDesignResponse)
def link_component_repository(
    workspace_id: UUID,
    component_object_id: UUID,
    payload: SolutionLinkRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    component = _get_component(db, workspace, component_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    if payload.target_object_id is not None:
        _get_repository(db, workspace, payload.target_object_id)
    _replace_link(
        db, workspace, state, component_object_id, USES_REPOSITORY, payload.target_object_id
    )
    db.commit()
    db.refresh(state)
    boundary = _boundary_for_component(db, workspace, component)
    return _build_design(db, workspace, state, boundary)


@router.put("/components/{component_object_id}/deployment", response_model=SolutionDesignResponse)
def link_component_deployment(
    workspace_id: UUID,
    component_object_id: UUID,
    payload: SolutionLinkRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    component = _get_component(db, workspace, component_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    if payload.target_object_id is not None:
        _get_deployment(db, workspace, payload.target_object_id)
    _replace_link(db, workspace, state, component_object_id, DEPLOYED_ON, payload.target_object_id)
    db.commit()
    db.refresh(state)
    boundary = _boundary_for_component(db, workspace, component)
    return _build_design(db, workspace, state, boundary)


@router.put(
    "/interfaces/{interface_object_id}/trust-boundary", response_model=SolutionDesignResponse
)
def link_interface_trust_boundary(
    workspace_id: UUID,
    interface_object_id: UUID,
    payload: SolutionLinkRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SolutionDesignResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_solution(workspace)
    interface = _get_interface(db, workspace, interface_object_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    if payload.target_object_id is not None:
        _get_trust(db, workspace, payload.target_object_id)
    _replace_link(db, workspace, state, interface_object_id, CROSSES, payload.target_object_id)
    db.commit()
    db.refresh(state)
    boundary = _boundary_for_interface(db, workspace, interface)
    return _build_design(db, workspace, state, boundary)
