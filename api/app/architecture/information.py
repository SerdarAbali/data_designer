from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.architecture.evidence import assert_no_evidence
from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    ArchitectureStateNode,
    ArchitectureStateResponse,
    InformationAttributeCreate,
    InformationAttributeResponse,
    InformationAttributeUpdate,
    InformationConcept,
    InformationConceptRelationship,
    InformationConceptualResponse,
    InformationContractRef,
    InformationEntityCreate,
    InformationEntityCreatedResponse,
    InformationEntityResponse,
    InformationEntityUpdate,
    InformationImpactChange,
    InformationImpactResponse,
    InformationLineageEdge,
    InformationLineageNode,
    InformationLineageResponse,
    InformationModelResponse,
    InformationOwnershipEntry,
    InformationOwnershipResponse,
    InformationPhysicalMapping,
    InformationPhysicalResponse,
    InformationRealization,
    InformationRealizationRequest,
    InformationRelationshipCreate,
    InformationRelationshipResponse,
    InformationRelationshipUpdate,
)
from app.architecture.state_scope import (
    assert_writable as _assert_writable,
)
from app.architecture.state_scope import (
    current_state as _current_state,
)
from app.architecture.state_scope import (
    exclude_member as _exclude_member,
)
from app.architecture.state_scope import (
    get_state as _get_state,
)
from app.architecture.state_scope import (
    present_in_current as _present_in_current,
)
from app.architecture.state_scope import (
    set_member_override as _set_member_override,
)
from app.architecture.state_scope import (
    state_is_editable as _state_is_editable,
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
    ArchitectureObject,
    ArchitectureRelationship,
    ArchitectureState,
    ArchitectureStateMember,
    AuthSession,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    InformationAttribute,
    InformationObject,
    Integration,
    IntegrationFieldRef,
    Workspace,
)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/information",
    tags=["architecture"],
)

ENTITY_KIND = "information_object"
ATTRIBUTE_KIND = "information_attribute"
FIELD_REF_KIND = "catalog_field_ref"
ER_EDGE_TYPE = "references"
REALIZES_EDGE_TYPE = "realizes"

_OVERRIDABLE_FIELDS = (
    "name",
    "data_type",
    "required",
    "nullable",
    "is_key",
    "is_identifier",
    "ordinal",
    "definition",
)


def _require_information(workspace: Workspace) -> None:
    if "information" not in workspace.disciplines:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )


def _get_entity(db: Session, workspace: Workspace, entity_object_id: UUID) -> ArchitectureObject:
    registry = db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == entity_object_id,
            ArchitectureObject.tenant_id == workspace.tenant_id,
            ArchitectureObject.kind == ENTITY_KIND,
        )
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Information entity not found",
        )
    return registry


def _get_attribute(db: Session, workspace: Workspace, attribute_id: UUID) -> InformationAttribute:
    attribute = db.scalar(
        select(InformationAttribute).where(
            InformationAttribute.object_id == attribute_id,
            InformationAttribute.tenant_id == workspace.tenant_id,
        )
    )
    if attribute is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Information attribute not found",
        )
    return attribute


def _get_relationship(
    db: Session, workspace: Workspace, relationship_id: UUID
) -> ArchitectureRelationship:
    relationship = db.scalar(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.id == relationship_id,
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
        )
    )
    if relationship is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Information relationship not found",
        )
    return relationship


def _entity_nodes(state: ArchitectureState) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for node in state.nodes:
        object_id = str(node.get("object_id"))
        if object_id not in nodes:
            nodes[object_id] = node
    return nodes


def _realizations(
    db: Session, state: ArchitectureState, attribute_ids: list[UUID]
) -> dict[UUID, InformationRealization]:
    if not attribute_ids:
        return {}
    edges = list(
        db.scalars(
            select(ArchitectureRelationship).where(
                ArchitectureRelationship.tenant_id == state.workspace_id,
                ArchitectureRelationship.relationship_type == REALIZES_EDGE_TYPE,
                ArchitectureRelationship.source_object_id.in_(attribute_ids),
            )
        )
    )
    result: dict[UUID, InformationRealization] = {}
    for edge in edges:
        if edge.created_in_state_id not in (None, state.id):
            continue
        field_ref = db.get(ArchitectureObject, edge.target_object_id)
        if field_ref is None or field_ref.kind != FIELD_REF_KIND:
            continue
        field = (
            db.get(CatalogField, field_ref.catalog_field_id)
            if field_ref.catalog_field_id
            else None
        )
        object_id = field.object_id if field is not None else None
        catalog_object = db.get(CatalogObject, object_id) if object_id else None
        result[edge.source_object_id] = InformationRealization(
            catalog_object_id=object_id,
            catalog_field_id=field.id if field is not None else None,
            catalog_object_name=catalog_object.name if catalog_object is not None else None,
            catalog_field_name=field.name if field is not None else None,
        )
    return result


def _attribute_response(
    attribute: InformationAttribute,
    overrides: dict,
    realization: InformationRealization | None,
) -> InformationAttributeResponse:
    def effective(field: str):
        return overrides[field] if field in overrides else getattr(attribute, field)

    return InformationAttributeResponse(
        object_id=attribute.object_id,
        entity_object_id=attribute.entity_object_id,
        name=effective("name"),
        data_type=effective("data_type"),
        required=effective("required"),
        nullable=effective("nullable"),
        is_key=effective("is_key"),
        is_identifier=effective("is_identifier"),
        ordinal=effective("ordinal"),
        definition=effective("definition"),
        created_in_state_id=attribute.created_in_state_id,
        realization=realization,
    )


def _effective_attributes(
    db: Session, state: ArchitectureState, entity_ids: list[UUID]
) -> dict[UUID, list[InformationAttributeResponse]]:
    if not entity_ids:
        return {}
    attributes = list(
        db.scalars(
            select(InformationAttribute).where(
                InformationAttribute.tenant_id == state.workspace_id,
                InformationAttribute.entity_object_id.in_(entity_ids),
            )
        )
    )
    members = _state_members(db, state)
    realizations = _realizations(db, state, [attr.object_id for attr in attributes])

    grouped: dict[UUID, list[InformationAttributeResponse]] = {eid: [] for eid in entity_ids}
    for attribute in attributes:
        member = members.get(attribute.object_id)
        if member is not None:
            if member.membership == "excluded":
                continue
        elif attribute.created_in_state_id not in (None, state.id):
            continue
        overrides = member.property_overrides if member is not None else {}
        grouped.setdefault(attribute.entity_object_id, []).append(
            _attribute_response(
                attribute,
                {k: v for k, v in overrides.items() if k in _OVERRIDABLE_FIELDS},
                realizations.get(attribute.object_id),
            )
        )
    for items in grouped.values():
        items.sort(key=lambda item: (item.ordinal, item.name))
    return grouped


def _entity_response(
    db: Session, state: ArchitectureState, registry: ArchitectureObject, node: dict
) -> InformationEntityResponse:
    typed = db.scalar(
        select(InformationObject).where(
            InformationObject.object_id == registry.id,
            InformationObject.tenant_id == state.workspace_id,
        )
    )
    if typed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Information entity not found",
        )
    position = node.get("position") or {}
    authoritative_system = (
        db.get(CatalogSystem, typed.authoritative_system_id)
        if typed.authoritative_system_id
        else None
    )
    return InformationEntityResponse(
        object_id=registry.id,
        occurrence_id=str(node.get("occurrence_id")),
        name=typed.name,
        description=typed.description,
        owner=typed.owner,
        steward=typed.steward,
        authoritative_system_id=typed.authoritative_system_id,
        authoritative_system_name=(
            authoritative_system.name if authoritative_system is not None else None
        ),
        classification=typed.classification,
        sensitivity=typed.sensitivity,
        external_identifier=typed.external_identifier,
        position={"x": float(position.get("x", 0.0)), "y": float(position.get("y", 0.0))},
    )


def _build_model(
    db: Session, workspace: Workspace, state: ArchitectureState
) -> InformationModelResponse:
    nodes = _entity_nodes(state)
    registry_by_object = {
        str(registry.id): registry
        for registry in db.scalars(
            select(ArchitectureObject).where(
                ArchitectureObject.tenant_id == state.workspace_id,
                ArchitectureObject.id.in_([UUID(oid) for oid in nodes]),
            )
        )
    }
    entities: list[InformationEntityResponse] = []
    entity_ids: list[UUID] = []
    for object_id, node in nodes.items():
        registry = registry_by_object.get(object_id)
        if registry is None or registry.kind != ENTITY_KIND:
            continue
        entities.append(_entity_response(db, state, registry, node))
        entity_ids.append(registry.id)

    attributes = _effective_attributes(db, state, entity_ids)
    for entity in entities:
        entity.attributes = attributes.get(entity.object_id, [])

    entity_id_set = set(entity_ids)
    relationships: list[InformationRelationshipResponse] = []
    for edge in db.scalars(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.tenant_id == state.workspace_id,
            ArchitectureRelationship.relationship_type == ER_EDGE_TYPE,
        )
    ):
        if edge.created_in_state_id not in (None, state.id):
            continue
        if edge.source_object_id not in entity_id_set or edge.target_object_id not in entity_id_set:
            continue
        properties = edge.properties or {}
        relationships.append(
            InformationRelationshipResponse(
                id=edge.id,
                source_object_id=edge.source_object_id,
                target_object_id=edge.target_object_id,
                name=properties.get("name"),
                cardinality=properties.get("cardinality", "one_to_many"),
                source_optional=bool(properties.get("source_optional", False)),
                target_optional=bool(properties.get("target_optional", True)),
                source_handle=properties.get("source_handle"),
                target_handle=properties.get("target_handle"),
            )
        )

    return InformationModelResponse(
        state_id=state.id,
        state_type=state.state_type,
        editable=_state_is_editable(state),
        entities=entities,
        relationships=relationships,
    )


@router.get("/model", response_model=InformationModelResponse)
def get_information_model(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationModelResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, state_id)
    return _build_model(db, workspace, state)


@router.post(
    "/entities",
    response_model=InformationEntityCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_information_entity(
    workspace_id: UUID,
    payload: InformationEntityCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationEntityCreatedResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)

    object_id = uuid4()
    registry = ArchitectureObject(
        id=object_id,
        tenant_id=workspace.tenant_id,
        kind=ENTITY_KIND,
    )
    typed = InformationObject(
        object_id=object_id,
        tenant_id=workspace.tenant_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        owner=payload.owner.strip() if payload.owner else None,
        steward=payload.steward.strip() if payload.steward else None,
        authoritative_system_id=payload.authoritative_system_id,
        classification=payload.classification.strip() if payload.classification else None,
        sensitivity=payload.sensitivity.strip() if payload.sensitivity else None,
    )

    node = ArchitectureStateNode(
        occurrence_id=f"occ-{uuid4()}",
        object_id=object_id,
        position=payload.position,
        discipline="information",
    ).model_dump(mode="json")
    nodes = list(state.nodes)
    nodes.append(node)

    db.add(registry)
    db.flush()
    db.add(typed)
    state.nodes = nodes
    state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(registry)
    db.refresh(typed)
    db.refresh(state)
    return InformationEntityCreatedResponse(
        entity=_entity_response(db, state, registry, node),
        state=ArchitectureStateResponse.model_validate(state),
    )


@router.patch("/entities/{entity_id}", response_model=InformationEntityResponse)
def update_information_entity(
    workspace_id: UUID,
    entity_id: UUID,
    payload: InformationEntityUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationEntityResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    registry = _get_entity(db, workspace, entity_id)

    if _present_in_current(db, workspace, entity_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entities present in Current cannot be edited from a candidate state",
        )

    typed = db.scalar(
        select(InformationObject).where(
            InformationObject.object_id == entity_id,
            InformationObject.tenant_id == workspace.tenant_id,
        )
    )
    if typed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Information entity not found",
        )
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        typed.name = changes["name"].strip()
    if "description" in changes:
        typed.description = changes["description"].strip() if changes["description"] else None
    if "owner" in changes:
        owner = changes["owner"]
        typed.owner = owner.strip() if owner else None
    if "steward" in changes:
        steward = changes["steward"]
        typed.steward = steward.strip() if steward else None
    if "authoritative_system_id" in changes:
        typed.authoritative_system_id = changes["authoritative_system_id"]
    if "classification" in changes:
        classification = changes["classification"]
        typed.classification = classification.strip() if classification else None
    if "sensitivity" in changes:
        sensitivity = changes["sensitivity"]
        typed.sensitivity = sensitivity.strip() if sensitivity else None
    db.commit()
    db.refresh(typed)
    authoritative_system = (
        db.get(CatalogSystem, typed.authoritative_system_id)
        if typed.authoritative_system_id
        else None
    )
    return InformationEntityResponse(
        object_id=registry.id,
        occurrence_id="",
        name=typed.name,
        description=typed.description,
        owner=typed.owner,
        steward=typed.steward,
        authoritative_system_id=typed.authoritative_system_id,
        authoritative_system_name=(
            authoritative_system.name if authoritative_system is not None else None
        ),
        classification=typed.classification,
        sensitivity=typed.sensitivity,
        external_identifier=typed.external_identifier,
        position={"x": 0.0, "y": 0.0},
    )


@router.post(
    "/entities/{entity_id}/attributes",
    response_model=InformationAttributeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_information_attribute(
    workspace_id: UUID,
    entity_id: UUID,
    payload: InformationAttributeCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationAttributeResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    _get_entity(db, workspace, entity_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)

    existing = db.scalar(
        select(InformationAttribute).where(
            InformationAttribute.tenant_id == workspace.tenant_id,
            InformationAttribute.entity_object_id == entity_id,
            InformationAttribute.name == payload.name.strip(),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An attribute with this name already exists on the entity",
        )

    object_id = uuid4()
    registry = ArchitectureObject(
        id=object_id,
        tenant_id=workspace.tenant_id,
        kind=ATTRIBUTE_KIND,
    )
    attribute = InformationAttribute(
        object_id=object_id,
        tenant_id=workspace.tenant_id,
        entity_object_id=entity_id,
        name=payload.name.strip(),
        data_type=payload.data_type.strip() or "string",
        required=payload.required,
        nullable=payload.nullable,
        is_key=payload.is_key,
        is_identifier=payload.is_identifier,
        ordinal=payload.ordinal,
        definition=payload.definition,
        created_in_state_id=state.id,
    )
    db.add(registry)
    db.flush()
    db.add(attribute)
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
    db.commit()
    db.refresh(attribute)
    return _attribute_response(attribute, {}, None)


@router.patch("/attributes/{attribute_id}", response_model=InformationAttributeResponse)
def update_information_attribute(
    workspace_id: UUID,
    attribute_id: UUID,
    payload: InformationAttributeUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationAttributeResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    attribute = _get_attribute(db, workspace, attribute_id)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    changes = {k: v for k, v in changes.items() if k in _OVERRIDABLE_FIELDS}

    scope_state = _current_state(db, workspace)
    override_mode = False
    if state_id is not None:
        scope_state = _get_state(db, workspace, state_id)
        _assert_writable(scope_state)
        if attribute.created_in_state_id is None:
            override_mode = _present_in_current(db, workspace, attribute.entity_object_id)

    if override_mode:
        assert scope_state is not None
        overrides = _set_member_override(db, workspace, scope_state, attribute_id, changes)
        db.commit()
        realization = (
            _realizations(db, scope_state, [attribute_id]).get(attribute_id)
            if scope_state is not None
            else None
        )
        return _attribute_response(
            attribute,
            {k: v for k, v in overrides.items() if k in _OVERRIDABLE_FIELDS},
            realization,
        )

    if changes:
        _apply_attribute_changes(db, workspace, attribute, changes)
        db.commit()
        db.refresh(attribute)
    realization = (
        _realizations(db, scope_state, [attribute_id]).get(attribute_id)
        if scope_state is not None
        else None
    )
    return _attribute_response(attribute, {}, realization)


def _apply_attribute_changes(
    db: Session,
    workspace: Workspace,
    attribute: InformationAttribute,
    changes: dict,
) -> None:
    if "name" in changes:
        attribute.name = changes["name"].strip()
    if "data_type" in changes:
        attribute.data_type = changes["data_type"].strip() or "string"
    for field in ("required", "nullable", "is_key", "is_identifier", "ordinal"):
        if field in changes:
            setattr(attribute, field, changes[field])
    if "definition" in changes:
        attribute.definition = changes["definition"]


@router.delete("/attributes/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_information_attribute(
    workspace_id: UUID,
    attribute_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    attribute = _get_attribute(db, workspace, attribute_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)

    if attribute.created_in_state_id == state.id:
        # Evidence is never silently dropped: refuse the removal while it is
        # still supported, so the caller can delete the evidence explicitly.
        assert_no_evidence(
            db,
            workspace.tenant_id,
            [("architecture_object", attribute_id)],
        )
        db.execute(
            delete(ArchitectureStateMember).where(
                ArchitectureStateMember.state_id == state.id,
                ArchitectureStateMember.object_id == attribute_id,
            )
        )
        db.execute(
            delete(ArchitectureRelationship).where(
                ArchitectureRelationship.source_object_id == attribute_id,
                ArchitectureRelationship.relationship_type == REALIZES_EDGE_TYPE,
            )
        )
        db.delete(attribute)
        registry = db.get(ArchitectureObject, attribute_id)
        if registry is not None:
            db.delete(registry)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    _exclude_member(db, workspace, state, attribute_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/attributes/{attribute_id}/realization",
    response_model=InformationRealization,
)
def set_information_realization(
    workspace_id: UUID,
    attribute_id: UUID,
    payload: InformationRealizationRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationRealization:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    _get_attribute(db, workspace, attribute_id)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)

    scope = (None, state.id)
    existing_edges = list(
        db.scalars(
            select(ArchitectureRelationship).where(
                ArchitectureRelationship.tenant_id == workspace.tenant_id,
                ArchitectureRelationship.relationship_type == REALIZES_EDGE_TYPE,
                ArchitectureRelationship.source_object_id == attribute_id,
            )
        )
    )
    for edge in existing_edges:
        if edge.created_in_state_id in scope or edge.created_in_state_id is None:
            db.delete(edge)

    if payload.catalog_field_id is None:
        db.commit()
        return InformationRealization()

    field = db.scalar(
        select(CatalogField).where(
            CatalogField.id == payload.catalog_field_id,
            CatalogField.tenant_id == workspace.tenant_id,
            CatalogField.deleted_at.is_(None),
        )
    )
    if field is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Catalog field not found",
        )
    if payload.catalog_object_id is not None and payload.catalog_object_id != field.object_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Catalog field does not belong to the selected object",
        )

    field_ref = db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.tenant_id == workspace.tenant_id,
            ArchitectureObject.kind == FIELD_REF_KIND,
            ArchitectureObject.catalog_field_id == field.id,
        )
    )
    if field_ref is None:
        field_ref = ArchitectureObject(
            id=uuid4(),
            tenant_id=workspace.tenant_id,
            kind=FIELD_REF_KIND,
            catalog_field_id=field.id,
        )
        db.add(field_ref)
        db.flush()

    db.add(
        ArchitectureRelationship(
            id=uuid4(),
            tenant_id=workspace.tenant_id,
            source_object_id=attribute_id,
            target_object_id=field_ref.id,
            relationship_type=REALIZES_EDGE_TYPE,
            properties={"catalog_object_id": str(field.object_id)},
            created_in_state_id=state.id,
        )
    )
    db.commit()

    catalog_object = db.get(CatalogObject, field.object_id)
    return InformationRealization(
        catalog_object_id=field.object_id,
        catalog_field_id=field.id,
        catalog_object_name=catalog_object.name if catalog_object is not None else None,
        catalog_field_name=field.name,
    )


@router.post(
    "/relationships",
    response_model=InformationRelationshipResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_information_relationship(
    workspace_id: UUID,
    payload: InformationRelationshipCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationRelationshipResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)
    _get_entity(db, workspace, payload.source_object_id)
    _get_entity(db, workspace, payload.target_object_id)
    if payload.source_object_id == payload.target_object_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A relationship must connect two different entities",
        )

    existing = db.scalar(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            ArchitectureRelationship.relationship_type == ER_EDGE_TYPE,
            ArchitectureRelationship.source_object_id == payload.source_object_id,
            ArchitectureRelationship.target_object_id == payload.target_object_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This relationship already exists",
        )

    edge = ArchitectureRelationship(
        id=uuid4(),
        tenant_id=workspace.tenant_id,
        source_object_id=payload.source_object_id,
        target_object_id=payload.target_object_id,
        relationship_type=ER_EDGE_TYPE,
        properties={
            "name": payload.name,
            "cardinality": payload.cardinality,
            "source_optional": payload.source_optional,
            "target_optional": payload.target_optional,
            "source_handle": payload.source_handle,
            "target_handle": payload.target_handle,
        },
        created_in_state_id=state.id,
    )
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return InformationRelationshipResponse(
        id=edge.id,
        source_object_id=edge.source_object_id,
        target_object_id=edge.target_object_id,
        name=payload.name,
        cardinality=payload.cardinality,
        source_optional=payload.source_optional,
        target_optional=payload.target_optional,
        source_handle=payload.source_handle,
        target_handle=payload.target_handle,
    )


@router.patch(
    "/relationships/{relationship_id}",
    response_model=InformationRelationshipResponse,
)
def update_information_relationship(
    workspace_id: UUID,
    relationship_id: UUID,
    state_id: UUID,
    payload: InformationRelationshipUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationRelationshipResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    edge = _get_relationship(db, workspace, relationship_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    # A candidate may only edit relationships it authored; canonical baseline
    # edges (e.g. those visible in Current) must never be mutated from a candidate.
    if edge.created_in_state_id != state.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only relationships created in this state can be edited",
        )

    properties = dict(edge.properties or {})
    changes = payload.model_dump(exclude_unset=True)
    # Reconnection reassigns the endpoint columns rather than edge properties.
    new_source = changes.pop("source_object_id", None)
    new_target = changes.pop("target_object_id", None)
    if new_source is not None or new_target is not None:
        source_id = new_source if new_source is not None else edge.source_object_id
        target_id = new_target if new_target is not None else edge.target_object_id
        if source_id == target_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A relationship must connect two different entities",
            )
        _get_entity(db, workspace, source_id)
        _get_entity(db, workspace, target_id)
        duplicate = db.scalar(
            select(ArchitectureRelationship).where(
                ArchitectureRelationship.tenant_id == workspace.tenant_id,
                ArchitectureRelationship.relationship_type == ER_EDGE_TYPE,
                ArchitectureRelationship.source_object_id == source_id,
                ArchitectureRelationship.target_object_id == target_id,
                ArchitectureRelationship.id != edge.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This relationship already exists",
            )
        edge.source_object_id = source_id
        edge.target_object_id = target_id

    properties.update(changes)
    edge.properties = properties
    db.commit()
    db.refresh(edge)
    properties = edge.properties
    return InformationRelationshipResponse(
        id=edge.id,
        source_object_id=edge.source_object_id,
        target_object_id=edge.target_object_id,
        name=properties.get("name"),
        cardinality=properties.get("cardinality", "one_to_many"),
        source_optional=bool(properties.get("source_optional", False)),
        target_optional=bool(properties.get("target_optional", True)),
        source_handle=properties.get("source_handle"),
        target_handle=properties.get("target_handle"),
    )


@router.delete("/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_information_relationship(
    workspace_id: UUID,
    relationship_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    edge = _get_relationship(db, workspace, relationship_id)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    # Only candidate-authored relationships may be deleted; canonical baseline
    # edges visible in Current are left untouched.
    if edge.created_in_state_id != state.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only relationships created in this state can be deleted",
        )
    db.delete(edge)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Read-only completion projections ----------------------------------------
#
# Conceptual, physical-realization, ownership, lineage and impact views are all
# projections over the canonical information model plus existing catalog and
# integration rows. They create or mutate nothing and reuse canonical ids; any
# comparison that cannot be derived is reported as unsupported rather than
# fabricated.

_ENTITY_COMPARABLE = (
    "name",
    "description",
    "owner",
    "steward",
    "authoritative_system_id",
    "classification",
    "sensitivity",
)
_ATTRIBUTE_COMPARABLE = (
    "name",
    "data_type",
    "required",
    "nullable",
    "is_key",
    "is_identifier",
    "definition",
)
_RELATIONSHIP_COMPARABLE = (
    "name",
    "cardinality",
    "source_optional",
    "target_optional",
    "source_handle",
    "target_handle",
)


def _catalog_field_context(
    db: Session, field_id: UUID
) -> tuple[CatalogField | None, CatalogObject | None, CatalogSystem | None]:
    """Resolve a catalog field to its object and system, treating deleted as missing."""
    field = db.get(CatalogField, field_id)
    if field is None or field.deleted_at is not None:
        return None, None, None
    catalog_object = db.get(CatalogObject, field.object_id)
    system = db.get(CatalogSystem, catalog_object.system_id) if catalog_object is not None else None
    return field, catalog_object, system


def _field_contracts(
    db: Session, workspace: Workspace, field_id: UUID
) -> list[tuple[Integration, str]]:
    """Integrations referencing a catalog field, with the reference direction."""
    refs = db.scalars(
        select(IntegrationFieldRef).where(
            IntegrationFieldRef.tenant_id == workspace.tenant_id,
            IntegrationFieldRef.field_id == field_id,
        )
    )
    seen: dict[UUID, tuple[Integration, str]] = {}
    for ref in refs:
        if ref.integration_id in seen:
            continue
        integration = db.get(Integration, ref.integration_id)
        if integration is not None:
            seen[integration.id] = (integration, ref.direction)
    return list(seen.values())


def _request_graph_flows(graph: dict) -> list[tuple[UUID, UUID, bool]]:
    """Field-to-field flows proven by a contract request graph.

    Returns ``(source_field_id, target_field_id, transformed)`` triples derived
    from real node and edge references. ``transformed`` is true when the path
    passes through a transformation node, so the UI can label it truthfully.
    """
    nodes = graph.get("nodes") or []
    by_id = {node.get("id"): node for node in nodes}
    source = next((node for node in nodes if node.get("type") == "source"), None)
    target = next((node for node in nodes if node.get("type") == "target"), None)
    if source is None or target is None:
        return []
    outgoing: dict[str, list[dict]] = defaultdict(list)
    for edge in graph.get("edges") or []:
        outgoing[edge.get("sourceNodeId")].append(edge)

    def field_of(port) -> UUID | None:
        if isinstance(port, str) and port.startswith("field:"):
            try:
                return UUID(port.removeprefix("field:"))
            except ValueError:
                return None
        return None

    def is_transform(node_id: str) -> bool:
        return (by_id.get(node_id) or {}).get("type") not in ("source", "target")

    results: list[tuple[UUID, UUID, bool]] = []

    def walk(node_id: str, source_field: UUID, transformed: bool) -> None:
        for edge in outgoing.get(node_id, []):
            nxt = edge.get("targetNodeId")
            combined = transformed or is_transform(nxt)
            if nxt == target.get("id"):
                target_field = field_of(edge.get("targetPortId"))
                if target_field is not None:
                    results.append((source_field, target_field, combined))
            else:
                walk(nxt, source_field, combined)

    for edge in outgoing.get(source.get("id"), []):
        source_field = field_of(edge.get("sourcePortId"))
        if source_field is None:
            continue
        nxt = edge.get("targetNodeId")
        if nxt == target.get("id"):
            target_field = field_of(edge.get("targetPortId"))
            if target_field is not None:
                results.append((source_field, target_field, is_transform(nxt)))
        else:
            walk(nxt, source_field, is_transform(nxt))
    return results


@router.get("/conceptual", response_model=InformationConceptualResponse)
def get_information_conceptual(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationConceptualResponse:
    """Business concepts only: no attributes, data types or physical detail."""
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)
    return InformationConceptualResponse(
        state_id=state.id,
        concepts=[
            InformationConcept(
                object_id=entity.object_id,
                name=entity.name,
                description=entity.description,
                owner=entity.owner,
            )
            for entity in model.entities
        ],
        relationships=[
            InformationConceptRelationship(
                id=relationship.id,
                source_object_id=relationship.source_object_id,
                target_object_id=relationship.target_object_id,
                name=relationship.name,
                cardinality=relationship.cardinality,
            )
            for relationship in model.relationships
        ],
    )


@router.get("/physical", response_model=InformationPhysicalResponse)
def get_information_physical(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationPhysicalResponse:
    """Logical-to-physical realization derived from existing realizations."""
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)

    summary = {"realized": 0, "partial": 0, "unmapped": 0, "invalid": 0}
    mappings: list[InformationPhysicalMapping] = []
    for entity in model.entities:
        for attribute in entity.attributes:
            realization = attribute.realization
            status = "unmapped"
            system_id = system_name = None
            catalog_object_id = catalog_object_name = None
            catalog_field_id = catalog_field_name = None
            contracts: list[InformationContractRef] = []
            if realization is not None and realization.catalog_field_id is not None:
                field, catalog_object, system = _catalog_field_context(
                    db, realization.catalog_field_id
                )
                if field is None:
                    status = "invalid"
                else:
                    catalog_field_id = field.id
                    catalog_field_name = field.name
                    catalog_object_id = field.object_id
                    catalog_object_name = catalog_object.name if catalog_object else None
                    system_id = system.id if system else None
                    system_name = system.name if system else None
                    status = "partial" if field.data_type != attribute.data_type else "realized"
                    if system is not None:
                        contracts = [
                            InformationContractRef(
                                id=integration.id, name=integration.name, direction=direction
                            )
                            for integration, direction in _field_contracts(db, workspace, field.id)
                        ]
            summary[status] += 1
            mappings.append(
                InformationPhysicalMapping(
                    entity_object_id=entity.object_id,
                    entity_name=entity.name,
                    attribute_object_id=attribute.object_id,
                    attribute_name=attribute.name,
                    data_type=attribute.data_type,
                    required=attribute.required,
                    status=status,
                    system_id=system_id,
                    system_name=system_name,
                    catalog_object_id=catalog_object_id,
                    catalog_object_name=catalog_object_name,
                    catalog_field_id=catalog_field_id,
                    catalog_field_name=catalog_field_name,
                    contracts=contracts,
                )
            )
    return InformationPhysicalResponse(state_id=state.id, mappings=mappings, summary=summary)


def _ownership_issues(
    entity: InformationEntityResponse, systems: list[str], in_state: bool
) -> list[str]:
    issues: list[str] = []
    if not entity.owner:
        issues.append("missing_owner")
    if not entity.steward:
        issues.append("missing_steward")
    if not entity.authoritative_system_id:
        issues.append("missing_authoritative_system")
    elif not in_state:
        issues.append("authoritative_not_in_state")
    if len(systems) > 1:
        issues.append("multiple_authoritative_sources")
    sensitive = bool(
        entity.sensitivity and entity.sensitivity.strip().lower() not in ("", "none", "low")
    )
    if sensitive and (not entity.owner or not entity.steward):
        issues.append("sensitive_without_ownership")
    return issues


@router.get("/ownership", response_model=InformationOwnershipResponse)
def get_information_ownership(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationOwnershipResponse:
    """Ownership and authority facts plus provable governance gaps."""
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)
    state_object_ids = {str(node.get("object_id")) for node in state.nodes}

    entries: list[InformationOwnershipEntry] = []
    for entity in model.entities:
        systems: list[str] = []
        if entity.authoritative_system_name and entity.authoritative_system_name not in systems:
            systems.append(entity.authoritative_system_name)
        realization_count = 0
        for attribute in entity.attributes:
            realization = attribute.realization
            if realization is None or realization.catalog_field_id is None:
                continue
            realization_count += 1
            _field, _object, system = _catalog_field_context(db, realization.catalog_field_id)
            if system is not None and system.name not in systems:
                systems.append(system.name)
        in_state = bool(
            entity.authoritative_system_id
            and str(entity.authoritative_system_id) in state_object_ids
        )
        entries.append(
            InformationOwnershipEntry(
                object_id=entity.object_id,
                name=entity.name,
                owner=entity.owner,
                steward=entity.steward,
                authoritative_system_id=entity.authoritative_system_id,
                authoritative_system_name=entity.authoritative_system_name,
                authoritative_in_state=in_state,
                classification=entity.classification,
                sensitivity=entity.sensitivity,
                realization_count=realization_count,
                systems=systems,
                issues=_ownership_issues(entity, systems, in_state),
            )
        )
    return InformationOwnershipResponse(state_id=state.id, entries=entries)


@router.get("/lineage", response_model=InformationLineageResponse)
def get_information_lineage(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationLineageResponse:
    """Lineage built only from proven realization and contract references."""
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)

    nodes: dict[str, InformationLineageNode] = {}
    edges: list[InformationLineageEdge] = []
    gaps: list[str] = []

    def add_node(node: InformationLineageNode) -> None:
        nodes.setdefault(node.id, node)

    def add_edge(source: str, target: str, relation: str) -> None:
        edges.append(
            InformationLineageEdge(
                id=f"{source}->{target}:{relation}", source=source, target=target, relation=relation
            )
        )

    def add_field(
        field: CatalogField,
        catalog_object: CatalogObject | None,
        system: CatalogSystem | None,
    ) -> str:
        key = f"field:{field.id}"
        add_node(
            InformationLineageNode(
                id=key,
                kind="catalog_field",
                name=field.name,
                detail=catalog_object.name if catalog_object is not None else None,
                system_name=system.name if system is not None else None,
                catalog_field_id=field.id,
            )
        )
        if system is not None:
            system_key = f"system:{system.id}"
            add_node(
                InformationLineageNode(
                    id=system_key, kind="catalog_system", name=system.name, system_name=system.name
                )
            )
            add_edge(key, system_key, "sourced from")
        return key

    for entity in model.entities:
        entity_key = f"entity:{entity.object_id}"
        for attribute in entity.attributes:
            attribute_key = f"attribute:{attribute.object_id}"
            label = f"{entity.name}.{attribute.name}"
            add_node(
                InformationLineageNode(id=entity_key, kind="information_entity", name=entity.name)
            )
            add_node(
                InformationLineageNode(
                    id=attribute_key,
                    kind="information_attribute",
                    name=label,
                    detail=attribute.data_type,
                )
            )
            add_edge(entity_key, attribute_key, "has attribute")

            realization = attribute.realization
            if realization is None or realization.catalog_field_id is None:
                gaps.append(f"{label} has no physical realization")
                continue
            field, catalog_object, system = _catalog_field_context(db, realization.catalog_field_id)
            if field is None:
                gaps.append(f"{label} references a missing catalog field")
                continue
            field_key = add_field(field, catalog_object, system)
            add_edge(attribute_key, field_key, "realized as")

            for integration, _direction in _field_contracts(db, workspace, field.id):
                contract_key = f"contract:{integration.id}"
                add_node(
                    InformationLineageNode(
                        id=contract_key,
                        kind="contract",
                        name=integration.name,
                        contract_id=integration.id,
                    )
                )
                add_edge(field_key, contract_key, "mapped by")
                for source_field_id, target_field_id, transformed in _request_graph_flows(
                    integration.graph or {}
                ):
                    if source_field_id != field.id:
                        continue
                    target_field, target_object, target_system = _catalog_field_context(
                        db, target_field_id
                    )
                    if target_field is None:
                        gaps.append(f"{integration.name} maps to a missing catalog field")
                        continue
                    target_key = add_field(target_field, target_object, target_system)
                    relation = "transformed by" if transformed else "delivered to"
                    add_edge(contract_key, target_key, relation)

    return InformationLineageResponse(
        state_id=state.id, nodes=list(nodes.values()), edges=edges, gaps=gaps
    )


def _build_information_impact(
    db: Session,
    state: ArchitectureState,
    candidate: InformationModelResponse,
    baseline: InformationModelResponse | None,
    baseline_state: ArchitectureState | None,
) -> InformationImpactResponse:
    if baseline is None or baseline_state is None:
        return InformationImpactResponse(
            state_id=state.id,
            baseline_state_id=None,
            supported=False,
            changes=[],
            unresolved=["No Current baseline state is available for comparison."],
            summary={},
        )

    changes: list[InformationImpactChange] = []
    unresolved: list[str] = []
    base_entities = {entity.object_id: entity for entity in baseline.entities}
    cand_entities = {entity.object_id: entity for entity in candidate.entities}

    for object_id, entity in cand_entities.items():
        base = base_entities.get(object_id)
        if base is None:
            changes.append(
                InformationImpactChange(
                    object_type="entity", object_id=object_id, name=entity.name, change="added"
                )
            )
            continue
        changed = [f for f in _ENTITY_COMPARABLE if getattr(entity, f) != getattr(base, f)]
        changes.append(
            InformationImpactChange(
                object_type="entity",
                object_id=object_id,
                name=entity.name,
                change="changed" if changed else "reused",
                changed_fields=changed,
                reason="entity properties changed" if changed else None,
            )
        )
    for object_id, base in base_entities.items():
        if object_id not in cand_entities:
            changes.append(
                InformationImpactChange(
                    object_type="entity", object_id=object_id, name=base.name, change="removed"
                )
            )

    for object_id, entity in cand_entities.items():
        base = base_entities.get(object_id)
        base_attributes = {a.object_id: a for a in (base.attributes if base is not None else [])}
        for attribute in entity.attributes:
            prior = base_attributes.get(attribute.object_id)
            if prior is None:
                changes.append(
                    InformationImpactChange(
                        object_type="attribute",
                        object_id=attribute.object_id,
                        name=attribute.name,
                        entity_object_id=object_id,
                        entity_name=entity.name,
                        change="added",
                    )
                )
            else:
                changed = [
                    f for f in _ATTRIBUTE_COMPARABLE if getattr(attribute, f) != getattr(prior, f)
                ]
                changes.append(
                    InformationImpactChange(
                        object_type="attribute",
                        object_id=attribute.object_id,
                        name=attribute.name,
                        entity_object_id=object_id,
                        entity_name=entity.name,
                        change="changed" if changed else "reused",
                        changed_fields=changed,
                        reason="attribute properties changed" if changed else None,
                    )
                )

            base_field = prior.realization.catalog_field_id if prior and prior.realization else None
            cand_field = (
                attribute.realization.catalog_field_id if attribute.realization else None
            )
            if cand_field != base_field:
                if base_field is None:
                    change_type = "added"
                elif cand_field is None:
                    change_type = "removed"
                else:
                    change_type = "changed"
                reason = "physical realization changed"
                if cand_field is not None and _catalog_field_context(db, cand_field)[0] is None:
                    reason = "physical realization references a missing catalog field"
                    unresolved.append(
                        f"{entity.name}.{attribute.name} is realized to a missing catalog field"
                    )
                changes.append(
                    InformationImpactChange(
                        object_type="realization",
                        object_id=attribute.object_id,
                        name=attribute.name,
                        entity_object_id=object_id,
                        entity_name=entity.name,
                        change=change_type,
                        reason=reason,
                    )
                )
            elif cand_field is not None and _catalog_field_context(db, cand_field)[0] is None:
                unresolved.append(
                    f"{entity.name}.{attribute.name} realization references a missing catalog field"
                )

    for object_id, base in base_entities.items():
        candidate_entity = cand_entities.get(object_id)
        candidate_attributes = candidate_entity.attributes if candidate_entity is not None else []
        cand_attribute_ids = {a.object_id for a in candidate_attributes}
        for attribute in base.attributes:
            if attribute.object_id not in cand_attribute_ids:
                changes.append(
                    InformationImpactChange(
                        object_type="attribute",
                        object_id=attribute.object_id,
                        name=attribute.name,
                        entity_object_id=object_id,
                        entity_name=base.name,
                        change="removed",
                    )
                )

    base_relationships = {r.id: r for r in baseline.relationships}
    cand_relationships = {r.id: r for r in candidate.relationships}
    for relationship_id, relationship in cand_relationships.items():
        prior = base_relationships.get(relationship_id)
        if prior is None:
            changes.append(
                InformationImpactChange(
                    object_type="relationship",
                    object_id=relationship_id,
                    name=relationship.name or "relationship",
                    change="added",
                )
            )
            continue
        changed = [
            f
            for f in _RELATIONSHIP_COMPARABLE
            if getattr(relationship, f) != getattr(prior, f)
        ]
        changes.append(
            InformationImpactChange(
                object_type="relationship",
                object_id=relationship_id,
                name=relationship.name or "relationship",
                change="changed" if changed else "reused",
                changed_fields=changed,
                reason="relationship properties changed" if changed else None,
            )
        )
    for relationship_id, prior in base_relationships.items():
        if relationship_id not in cand_relationships:
            changes.append(
                InformationImpactChange(
                    object_type="relationship",
                    object_id=relationship_id,
                    name=prior.name or "relationship",
                    change="removed",
                )
            )

    summary = {
        label: sum(1 for change in changes if change.change == label)
        for label in ("added", "removed", "changed", "reused")
    }
    return InformationImpactResponse(
        state_id=state.id,
        baseline_state_id=baseline_state.id,
        supported=True,
        changes=changes,
        unresolved=unresolved,
        summary=summary,
    )


@router.get("/impact", response_model=InformationImpactResponse)
def get_information_impact(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InformationImpactResponse:
    """Current-vs-selected-state comparison over the canonical information model."""
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_information(workspace)
    state = _get_state(db, workspace, state_id)
    candidate = _build_model(db, workspace, state)
    baseline_state = _current_state(db, workspace)
    baseline = _build_model(db, workspace, baseline_state) if baseline_state else None
    return _build_information_impact(db, state, candidate, baseline, baseline_state)
