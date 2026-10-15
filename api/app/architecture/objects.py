from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    ArchitectureObjectCreate,
    ArchitectureObjectCreatedResponse,
    ArchitectureObjectResponse,
    ArchitectureObjectUpdate,
    ArchitectureStateNode,
    ArchitectureStateRelationship,
    ArchitectureStateResponse,
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
    ArchitectureState,
    AuthSession,
    BusinessCapability,
    BusinessRequirement,
    CatalogSystem,
    InformationObject,
    SolutionBoundary,
    SolutionComponent,
    Workspace,
)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/architecture-objects",
    tags=["architecture"],
)


class ArchitectureRecord(Protocol):
    object_id: UUID
    tenant_id: UUID
    name: str
    description: str | None


KIND_DISCIPLINE = {
    "business_requirement": "enterprise",
    "business_capability": "enterprise",
    "information_object": "information",
    "solution_boundary": "solution",
    "component": "solution",
    "interface": "solution",
}
KIND_MODELS = {
    "business_requirement": BusinessRequirement,
    "business_capability": BusinessCapability,
    "information_object": InformationObject,
    "solution_boundary": SolutionBoundary,
    "component": SolutionComponent,
    "interface": ArchitectureInterface,
}
RELATIONSHIP_TYPE = {
    "business_requirement": "Impacts",
    "business_capability": "Uses",
    "information_object": "Authoritative source",
    "solution_boundary": "Contains",
    "component": "Uses",
    "interface": "Provides",
}


def _object_response(
    row: ArchitectureRecord,
    registry: ArchitectureObject,
) -> ArchitectureObjectResponse:
    return ArchitectureObjectResponse(
        id=registry.id,
        kind=registry.kind,
        name=row.name,
        description=row.description,
        owner=getattr(row, "owner", None),
        authoritative_system_id=getattr(row, "authoritative_system_id", None),
    )


def _enabled(workspace: Workspace, kind: str) -> bool:
    return KIND_DISCIPLINE.get(kind) in workspace.disciplines


def _get_active_system(db: Session, workspace: Workspace, system_id: UUID) -> CatalogSystem:
    system = db.scalar(
        select(CatalogSystem).where(
            CatalogSystem.id == system_id,
            CatalogSystem.tenant_id == workspace.tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    )
    if system is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="System not found",
        )
    return system


def _system_occurrence(
    nodes: list[dict],
    system_id: UUID,
    position: dict[str, float],
) -> str:
    for node in nodes:
        if node.get("object_id") == str(system_id):
            return str(node["occurrence_id"])

    occurrence_id = f"occ-{uuid4()}"
    nodes.append(
        ArchitectureStateNode(
            occurrence_id=occurrence_id,
            object_id=system_id,
            position=position,
        ).model_dump(mode="json")
    )
    return occurrence_id


@router.get("", response_model=list[ArchitectureObjectResponse])
def list_architecture_objects(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[ArchitectureObjectResponse]:
    workspace = get_accessible_workspace(db, user, workspace_id)
    result: list[ArchitectureObjectResponse] = []
    for kind, model in KIND_MODELS.items():
        if not _enabled(workspace, kind):
            continue
        records = list(
            db.scalars(
                select(model).where(model.tenant_id == workspace.tenant_id).order_by(model.name)
            )
        )
        for record in records:
            registry = db.get(ArchitectureObject, record.object_id)
            if registry is not None:
                result.append(_object_response(record, registry))
    return result


@router.post(
    "",
    response_model=ArchitectureObjectCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_architecture_object(
    workspace_id: UUID,
    payload: ArchitectureObjectCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureObjectCreatedResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    if not _enabled(workspace, payload.kind):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )

    state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == payload.state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture state not found",
        )
    if state.state_type == "current":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Current architecture state is read-only",
        )

    if payload.kind == "information_object":
        if not payload.owner or not payload.owner.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Owner is required for an information object",
            )
        if payload.authoritative_system_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An authoritative system is required for an information object",
            )
        related_system_id = payload.authoritative_system_id
    else:
        if payload.related_system_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose an existing system to relate to this architecture object",
            )
        related_system_id = payload.related_system_id

    _get_active_system(db, workspace, related_system_id)

    object_id = uuid4()
    registry = ArchitectureObject(
        id=object_id,
        tenant_id=workspace.tenant_id,
        kind=payload.kind,
    )
    model = KIND_MODELS[payload.kind]
    typed_record = model(
        object_id=object_id,
        tenant_id=workspace.tenant_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        **(
            {
                "owner": payload.owner.strip(),
                "authoritative_system_id": related_system_id,
            }
            if payload.kind == "information_object"
            else {}
        ),
    )

    occurrence_id = f"occ-{uuid4()}"
    nodes = list(state.nodes)
    system_occurrence_id = _system_occurrence(
        nodes,
        related_system_id,
        {"x": payload.position["x"] + 360.0, "y": payload.position["y"]},
    )
    nodes.append(
        ArchitectureStateNode(
            occurrence_id=occurrence_id,
            object_id=object_id,
            position=payload.position,
            discipline=KIND_DISCIPLINE[payload.kind],
        ).model_dump(mode="json")
    )
    relationships = list(state.relationships)
    relationships.append(
        ArchitectureStateRelationship(
            id=f"rel-{uuid4()}",
            source_id=occurrence_id,
            target_id=system_occurrence_id,
            type=RELATIONSHIP_TYPE[payload.kind],
            name=None,
            integration_id=None,
        ).model_dump(mode="json")
    )

    db.add(registry)
    db.flush()
    db.add(typed_record)
    state.nodes = nodes
    state.relationships = relationships
    state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(registry)
    db.refresh(typed_record)
    db.refresh(state)
    return ArchitectureObjectCreatedResponse(
        object=_object_response(typed_record, registry),
        state=ArchitectureStateResponse.model_validate(state),
    )


@router.patch("/{object_id}", response_model=ArchitectureObjectResponse)
def update_architecture_object(
    workspace_id: UUID,
    object_id: UUID,
    payload: ArchitectureObjectUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureObjectResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    registry = db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == object_id,
            ArchitectureObject.tenant_id == workspace.tenant_id,
            ArchitectureObject.system_id.is_(None),
        )
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )
    if not _enabled(workspace, registry.kind):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )

    current = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.state_type == "current",
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if current and any(str(node.get("object_id")) == str(object_id) for node in current.nodes):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Objects present in Current cannot be edited from a candidate state",
        )

    model = KIND_MODELS[registry.kind]
    record = db.scalar(
        select(model).where(
            model.object_id == object_id,
            model.tenant_id == workspace.tenant_id,
        )
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        record.name = changes["name"].strip()  # type: ignore[union-attr]
    if "description" in changes:
        record.description = changes["description"].strip() if changes["description"] else None
    if registry.kind == "information_object":
        if "owner" in changes:
            owner = changes["owner"]
            if owner is None or not owner.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Owner is required for an information object",
                )
            record.owner = owner.strip()  # type: ignore[attr-defined]
        if "authoritative_system_id" in changes:
            system_id = changes["authoritative_system_id"]
            if system_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="An authoritative system is required for an information object",
                )
            _get_active_system(db, workspace, system_id)
            record.authoritative_system_id = system_id  # type: ignore[attr-defined]

    db.commit()
    db.refresh(record)
    return _object_response(record, registry)
