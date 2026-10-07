from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.catalog.schemas import (
    FieldCreate,
    FieldResponse,
    FieldUpdate,
    ObjectCreate,
    ObjectResponse,
    ObjectUpdate,
    SystemCreate,
    SystemResponse,
    SystemUpdate,
)
from app.catalog.service import next_position
from app.db import get_session
from app.models import (
    AuthSession,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
    IntegrationFieldRef,
)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def active_system(db: Session, tenant_id: UUID, system_id: UUID) -> CatalogSystem:
    system = db.scalar(
        select(CatalogSystem).where(
            CatalogSystem.id == system_id,
            CatalogSystem.tenant_id == tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    )
    if system is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "System not found")
    return system


def active_object(db: Session, tenant_id: UUID, object_id: UUID) -> CatalogObject:
    obj = db.scalar(
        select(CatalogObject).where(
            CatalogObject.id == object_id,
            CatalogObject.tenant_id == tenant_id,
            CatalogObject.deleted_at.is_(None),
        )
    )
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Object not found")
    return obj


def active_field(db: Session, tenant_id: UUID, field_id: UUID) -> CatalogField:
    field = db.scalar(
        select(CatalogField).where(
            CatalogField.id == field_id,
            CatalogField.tenant_id == tenant_id,
            CatalogField.deleted_at.is_(None),
        )
    )
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field not found")
    return field


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The catalog change conflicts with an existing record",
        ) from error


def apply_update(instance, payload) -> None:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(instance, "extra_metadata" if key == "metadata" else key, value)


def archive_timestamp() -> datetime:
    return datetime.now(UTC)


def raise_if_integration_references(
    db: Session,
    tenant_id: UUID,
    *,
    system_id: UUID | None = None,
    object_id: UUID | None = None,
    field_id: UUID | None = None,
) -> None:
    query = select(Integration.id, Integration.name).where(
        Integration.tenant_id == tenant_id,
        Integration.deleted_at.is_(None),
    )
    if system_id is not None:
        query = query.where(
            (Integration.source_system_id == system_id)
            | (Integration.target_system_id == system_id)
        )
    if object_id is not None:
        query = query.where(
            (Integration.source_object_id == object_id)
            | (Integration.target_object_id == object_id)
        )
    if field_id is not None:
        query = (
            query.join(
                IntegrationFieldRef,
                (IntegrationFieldRef.integration_id == Integration.id)
                & (IntegrationFieldRef.tenant_id == Integration.tenant_id),
            )
            .where(IntegrationFieldRef.field_id == field_id)
            .distinct()
        )
    references = list(db.execute(query))
    if references:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "catalog_item_in_use",
                "message": "Archive the referencing integration before archiving this item",
                "integrations": [
                    {"id": str(integration_id), "name": name}
                    for integration_id, name in references
                ],
            },
        )


@router.get("/systems", response_model=list[SystemResponse])
def list_systems(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[CatalogSystem]:
    return list(
        db.scalars(
            select(CatalogSystem)
            .where(
                CatalogSystem.tenant_id == user.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
            .order_by(CatalogSystem.name, CatalogSystem.id)
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/systems/{system_id}", response_model=SystemResponse)
def get_system(
    system_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogSystem:
    return active_system(db, user.tenant_id, system_id)


@router.post(
    "/systems",
    response_model=SystemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_system(
    payload: SystemCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogSystem:
    require_csrf(request, auth_session)
    system = CatalogSystem(
        tenant_id=user.tenant_id,
        name=payload.name,
        description=payload.description,
        kind=payload.kind,
        icon=payload.icon,
        color=payload.color,
        position=payload.position,
        binding_state=payload.binding_state,
        extra_metadata=payload.metadata,
    )
    db.add(system)
    commit_or_conflict(db)
    db.refresh(system)
    return system


@router.patch("/systems/{system_id}", response_model=SystemResponse)
def update_system(
    system_id: UUID,
    payload: SystemUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogSystem:
    require_csrf(request, auth_session)
    system = active_system(db, user.tenant_id, system_id)
    apply_update(system, payload)
    system.updated_at = archive_timestamp()
    commit_or_conflict(db)
    db.refresh(system)
    return system


@router.delete("/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_system(
    system_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    system = db.scalar(
        select(CatalogSystem)
        .where(
            CatalogSystem.id == system_id,
            CatalogSystem.tenant_id == user.tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if system is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "System not found")
    raise_if_integration_references(db, user.tenant_id, system_id=system.id)
    now = archive_timestamp()
    system.deleted_at = system.updated_at = now
    objects = list(
        db.scalars(
            select(CatalogObject).where(
                CatalogObject.system_id == system.id,
                CatalogObject.tenant_id == user.tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
        )
    )
    for obj in objects:
        obj.deleted_at = obj.updated_at = now
        for field in db.scalars(
            select(CatalogField).where(
                CatalogField.object_id == obj.id,
                CatalogField.tenant_id == user.tenant_id,
                CatalogField.deleted_at.is_(None),
            )
        ):
            field.deleted_at = field.updated_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/systems/{system_id}/restore", response_model=SystemResponse)
def restore_system(
    system_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogSystem:
    require_csrf(request, auth_session)
    system = db.scalar(
        select(CatalogSystem).where(
            CatalogSystem.id == system_id,
            CatalogSystem.tenant_id == user.tenant_id,
            CatalogSystem.deleted_at.is_not(None),
        )
    )
    if system is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Archived system not found")
    system.deleted_at = None
    system.updated_at = archive_timestamp()
    commit_or_conflict(db)
    db.refresh(system)
    return system


@router.get("/systems/{system_id}/objects", response_model=list[ObjectResponse])
def list_objects(
    system_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[CatalogObject]:
    active_system(db, user.tenant_id, system_id)
    return list(
        db.scalars(
            select(CatalogObject)
            .where(
                CatalogObject.system_id == system_id,
                CatalogObject.tenant_id == user.tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
            .order_by(CatalogObject.position, CatalogObject.name, CatalogObject.id)
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/objects/{object_id}", response_model=ObjectResponse)
def get_object(
    object_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogObject:
    return active_object(db, user.tenant_id, object_id)


@router.post(
    "/systems/{system_id}/objects",
    response_model=ObjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_object(
    system_id: UUID,
    payload: ObjectCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogObject:
    require_csrf(request, auth_session)
    active_system(db, user.tenant_id, system_id)
    obj = CatalogObject(
        tenant_id=user.tenant_id,
        system_id=system_id,
        name=payload.name,
        label=payload.label or payload.name,
        description=payload.description,
        external_identifier=payload.external_identifier,
        origin=payload.origin,
        extra_metadata=payload.metadata,
        position=payload.position
        if payload.position is not None
        else next_position(db, CatalogObject, CatalogObject.system_id, system_id),
    )
    db.add(obj)
    commit_or_conflict(db)
    db.refresh(obj)
    return obj


@router.patch("/objects/{object_id}", response_model=ObjectResponse)
def update_object(
    object_id: UUID,
    payload: ObjectUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogObject:
    require_csrf(request, auth_session)
    obj = active_object(db, user.tenant_id, object_id)
    apply_update(obj, payload)
    obj.updated_at = archive_timestamp()
    commit_or_conflict(db)
    db.refresh(obj)
    return obj


@router.delete("/objects/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_object(
    object_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    obj = db.scalar(
        select(CatalogObject)
        .where(
            CatalogObject.id == object_id,
            CatalogObject.tenant_id == user.tenant_id,
            CatalogObject.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Object not found")
    raise_if_integration_references(db, user.tenant_id, object_id=obj.id)
    now = archive_timestamp()
    obj.deleted_at = obj.updated_at = now
    for field in db.scalars(
        select(CatalogField).where(
            CatalogField.object_id == obj.id,
            CatalogField.tenant_id == user.tenant_id,
            CatalogField.deleted_at.is_(None),
        )
    ):
        field.deleted_at = field.updated_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/objects/{object_id}/restore", response_model=ObjectResponse)
def restore_object(
    object_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogObject:
    require_csrf(request, auth_session)
    obj = db.scalar(
        select(CatalogObject).where(
            CatalogObject.id == object_id,
            CatalogObject.tenant_id == user.tenant_id,
            CatalogObject.deleted_at.is_not(None),
        )
    )
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Archived object not found")
    active_system(db, user.tenant_id, obj.system_id)
    obj.deleted_at = None
    obj.updated_at = archive_timestamp()
    commit_or_conflict(db)
    db.refresh(obj)
    return obj


@router.get("/objects/{object_id}/fields", response_model=list[FieldResponse])
def list_fields(
    object_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[CatalogField]:
    active_object(db, user.tenant_id, object_id)
    return list(
        db.scalars(
            select(CatalogField)
            .where(
                CatalogField.object_id == object_id,
                CatalogField.tenant_id == user.tenant_id,
                CatalogField.deleted_at.is_(None),
            )
            .order_by(CatalogField.position, CatalogField.name, CatalogField.id)
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/fields/{field_id}", response_model=FieldResponse)
def get_field(
    field_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogField:
    return active_field(db, user.tenant_id, field_id)


@router.post(
    "/objects/{object_id}/fields",
    response_model=FieldResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_field(
    object_id: UUID,
    payload: FieldCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogField:
    require_csrf(request, auth_session)
    active_object(db, user.tenant_id, object_id)
    field = CatalogField(
        tenant_id=user.tenant_id,
        object_id=object_id,
        name=payload.name,
        label=payload.label or payload.name,
        description=payload.description,
        data_type=payload.data_type,
        required=payload.required,
        nullable=payload.nullable,
        default_value=payload.default_value,
        external_identifier=payload.external_identifier,
        position=payload.position
        if payload.position is not None
        else next_position(db, CatalogField, CatalogField.object_id, object_id),
        origin=payload.origin,
        extra_metadata=payload.metadata,
    )
    db.add(field)
    commit_or_conflict(db)
    db.refresh(field)
    return field


@router.patch("/fields/{field_id}", response_model=FieldResponse)
def update_field(
    field_id: UUID,
    payload: FieldUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogField:
    require_csrf(request, auth_session)
    field = active_field(db, user.tenant_id, field_id)
    apply_update(field, payload)
    field.updated_at = archive_timestamp()
    commit_or_conflict(db)
    db.refresh(field)
    return field


@router.delete("/fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_field(
    field_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    field = db.scalar(
        select(CatalogField)
        .where(
            CatalogField.id == field_id,
            CatalogField.tenant_id == user.tenant_id,
            CatalogField.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field not found")
    raise_if_integration_references(db, user.tenant_id, field_id=field.id)
    field.deleted_at = field.updated_at = archive_timestamp()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/fields/{field_id}/restore", response_model=FieldResponse)
def restore_field(
    field_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CatalogField:
    require_csrf(request, auth_session)
    field = db.scalar(
        select(CatalogField).where(
            CatalogField.id == field_id,
            CatalogField.tenant_id == user.tenant_id,
            CatalogField.deleted_at.is_not(None),
        )
    )
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Archived field not found")
    active_object(db, user.tenant_id, field.object_id)
    field.deleted_at = None
    field.updated_at = archive_timestamp()
    commit_or_conflict(db)
    db.refresh(field)
    return field
