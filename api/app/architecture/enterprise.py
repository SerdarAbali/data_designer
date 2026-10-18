"""Enterprise Architecture workbench API.

Specialized strategy/capability/process modeler over the shared canonical
registry. Goals, requirements, capabilities, processes, principles, and roles
are canonical objects; cross-object edges (drives, needs, has_process,
supports, satisfies, governed_by, owned_by, depends_on, impacts, affects) live
in ``architecture_relationships``.

Candidate isolation mirrors the Solution Designer: an object authored in a
candidate carries ``created_in_state_id`` and a state node; edits to an object
present in Current are stored as bounded scalar ``candidate_overrides`` on the
candidate node rather than mutating the canonical row.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.architecture.evidence import assert_no_evidence
from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    ApplicationSupportEntry,
    ApplicationSupportResponse,
    ArchitectureStateNode,
    CapabilityMapEntry,
    CapabilityMapResponse,
    EnterpriseApplicationResponse,
    EnterpriseImpactResponse,
    EnterpriseLinkCreate,
    EnterpriseLinkResponse,
    EnterpriseModelResponse,
    EnterpriseObjectCreate,
    EnterpriseObjectResponse,
    EnterpriseObjectUpdate,
    ImpactChange,
    ProcessImpactEntry,
    ProcessImpactResponse,
    StrategyTraceChain,
    StrategyTraceResponse,
    StrategyTraceStep,
)
from app.architecture.state_scope import (
    assert_writable as _assert_writable,
)
from app.architecture.state_scope import (
    current_state as _current_state,
)
from app.architecture.state_scope import (
    get_state as _get_state,
)
from app.architecture.state_scope import (
    node_overrides as _node_overrides,
)
from app.architecture.state_scope import (
    present_in_current as _present_in_current,
)
from app.architecture.state_scope import (
    state_is_editable as _state_is_editable,
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
    ArchitecturePrinciple,
    ArchitectureRelationship,
    ArchitectureState,
    AuthSession,
    BusinessCapability,
    BusinessGoal,
    BusinessProcess,
    BusinessRequirement,
    CatalogSystem,
    OrganizationRole,
    SolutionBoundary,
    Workspace,
)

logger = logging.getLogger("app.architecture.enterprise")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/enterprise",
    tags=["architecture"],
)

OBJECT_TYPE_TO_KIND = {
    "goal": "business_goal",
    "requirement": "business_requirement",
    "capability": "business_capability",
    "process": "business_process",
    "principle": "architecture_principle",
    "role": "organization_role",
}
KIND_TO_OBJECT_TYPE = {kind: obj for obj, kind in OBJECT_TYPE_TO_KIND.items()}
KIND_TABLE = {
    "business_goal": BusinessGoal,
    "business_requirement": BusinessRequirement,
    "business_capability": BusinessCapability,
    "business_process": BusinessProcess,
    "architecture_principle": ArchitecturePrinciple,
    "organization_role": OrganizationRole,
}
ENTERPRISE_OBJECT_KINDS = set(KIND_TABLE)
NEW_KINDS = {
    "business_goal",
    "business_process",
    "architecture_principle",
    "organization_role",
}
APPLICATION_KINDS = {"system", "solution_boundary"}
EXTRA_FIELDS = {
    "goal": ("owner", "outcome_metric", "horizon"),
    "requirement": (),
    "capability": (),
    "process": ("owner", "process_type"),
    "principle": ("principle_type", "rationale"),
    "role": ("role_type",),
}
GROUP_FOR_KIND = {
    "business_goal": "goals",
    "business_requirement": "requirements",
    "business_capability": "capabilities",
    "business_process": "processes",
    "architecture_principle": "principles",
    "organization_role": "roles",
}

LINK_RULES: dict[str, tuple[set[str], set[str]]] = {
    "drives": ({"business_goal"}, {"business_requirement"}),
    "needs": ({"business_requirement"}, {"business_capability"}),
    "has_process": ({"business_capability"}, {"business_process"}),
    "supports": (APPLICATION_KINDS, {"business_capability", "business_process"}),
    "satisfies": (APPLICATION_KINDS, {"business_requirement"}),
    "governed_by": (ENTERPRISE_OBJECT_KINDS, {"architecture_principle"}),
    "owned_by": (ENTERPRISE_OBJECT_KINDS, {"organization_role"}),
    "depends_on": (ENTERPRISE_OBJECT_KINDS, ENTERPRISE_OBJECT_KINDS),
    "impacts": (ENTERPRISE_OBJECT_KINDS, {"business_capability", "business_process"}),
    "affects": (ENTERPRISE_OBJECT_KINDS, {"business_capability", "business_process"}),
}
ENTERPRISE_LINK_TYPES = tuple(LINK_RULES)
COMPARABLE_FIELDS = (
    "name",
    "description",
    "owner",
    "outcome_metric",
    "horizon",
    "process_type",
    "principle_type",
    "rationale",
    "role_type",
)


def _require_enterprise(workspace: Workspace) -> None:
    if "enterprise" not in workspace.disciplines:
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


def _get_registry(
    db: Session, workspace: Workspace, object_id: UUID, allowed: set[str]
) -> ArchitectureObject:
    registry = db.scalar(
        select(ArchitectureObject).where(
            ArchitectureObject.id == object_id,
            ArchitectureObject.tenant_id == workspace.tenant_id,
            ArchitectureObject.kind.in_(allowed),
        )
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )
    return registry


def _get_typed_row(db: Session, workspace: Workspace, registry: ArchitectureObject):
    model = KIND_TABLE.get(registry.kind)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )
    row = db.scalar(
        select(model).where(
            model.object_id == registry.id,
            model.tenant_id == workspace.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )
    return row


def _object_response(
    registry: ArchitectureObject, row, overrides: dict
) -> EnterpriseObjectResponse:
    object_type = KIND_TO_OBJECT_TYPE[registry.kind]

    def effective(field: str):
        if field in overrides:
            return overrides[field]
        return getattr(row, field, None)

    extras = EXTRA_FIELDS[object_type]
    return EnterpriseObjectResponse(
        object_id=registry.id,
        kind=object_type,
        name=effective("name") or "",
        description=effective("description"),
        **{field: (effective(field) if field in extras else None) for field in (
            "owner",
            "outcome_metric",
            "horizon",
            "process_type",
            "principle_type",
            "rationale",
            "role_type",
        )},
        created_in_state_id=getattr(row, "created_in_state_id", None),
    )


def _applications(db: Session, workspace: Workspace) -> list[EnterpriseApplicationResponse]:
    result: list[EnterpriseApplicationResponse] = []
    for system in db.scalars(
        select(CatalogSystem).where(
            CatalogSystem.tenant_id == workspace.tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
    ):
        result.append(
            EnterpriseApplicationResponse(
                object_id=system.id,
                name=system.name,
                kind="system",
                description=system.description,
            )
        )
    for boundary in db.scalars(
        select(SolutionBoundary).where(SolutionBoundary.tenant_id == workspace.tenant_id)
    ):
        result.append(
            EnterpriseApplicationResponse(
                object_id=boundary.object_id,
                name=boundary.name,
                kind="solution_boundary",
                description=boundary.description,
            )
        )
    result.sort(key=lambda item: (item.kind, item.name))
    return result


def _build_model(
    db: Session, workspace: Workspace, state: ArchitectureState
) -> EnterpriseModelResponse:
    nodes = [_as_uuid(node.get("object_id")) for node in state.nodes]
    nodes = [object_id for object_id in nodes if object_id is not None]
    registries = (
        list(
            db.scalars(
                select(ArchitectureObject).where(
                    ArchitectureObject.tenant_id == workspace.tenant_id,
                    ArchitectureObject.id.in_(nodes),
                    ArchitectureObject.kind.in_(ENTERPRISE_OBJECT_KINDS),
                )
            )
        )
        if nodes
        else []
    )
    grouped: dict[str, list[EnterpriseObjectResponse]] = {
        "goals": [],
        "requirements": [],
        "capabilities": [],
        "processes": [],
        "principles": [],
        "roles": [],
    }
    for registry in registries:
        model = KIND_TABLE[registry.kind]
        row = db.scalar(
            select(model).where(
                model.object_id == registry.id,
                model.tenant_id == workspace.tenant_id,
            )
        )
        if row is None:
            continue
        overrides = _node_overrides(state, registry.id)
        grouped[GROUP_FOR_KIND[registry.kind]].append(_object_response(registry, row, overrides))

    for items in grouped.values():
        items.sort(key=lambda item: item.name)

    applications = _applications(db, workspace)
    known_ids = {registry.id for registry in registries}
    known_ids.update(app.object_id for app in applications)

    links: list[EnterpriseLinkResponse] = []
    for edge in db.scalars(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            ArchitectureRelationship.relationship_type.in_(ENTERPRISE_LINK_TYPES),
            or_(
                ArchitectureRelationship.created_in_state_id.is_(None),
                ArchitectureRelationship.created_in_state_id == state.id,
            ),
        )
    ):
        if edge.source_object_id not in known_ids or edge.target_object_id not in known_ids:
            continue
        links.append(
            EnterpriseLinkResponse(
                id=edge.id,
                source_object_id=edge.source_object_id,
                target_object_id=edge.target_object_id,
                relationship_type=edge.relationship_type,
            )
        )
    links.sort(key=lambda item: (item.relationship_type, str(item.source_object_id)))

    return EnterpriseModelResponse(
        state_id=state.id,
        state_type=state.state_type,
        editable=_state_is_editable(state),
        applications=applications,
        links=links,
        **grouped,
    )


def _set_node_overrides(
    state: ArchitectureState, object_id: UUID, changes: dict
) -> None:
    updated: list[dict] = []
    for node in state.nodes:
        if str(node.get("object_id")) == str(object_id):
            node = dict(node)
            overrides = dict(node.get("candidate_overrides") or {})
            overrides.update(changes)
            node["candidate_overrides"] = overrides
        updated.append(node)
    state.nodes = updated
    state.updated_at = datetime.now(UTC)


def _purge_object(db: Session, workspace: Workspace, object_id: UUID) -> None:
    edges = list(
        db.scalars(
            select(ArchitectureRelationship).where(
                ArchitectureRelationship.tenant_id == workspace.tenant_id,
                (ArchitectureRelationship.source_object_id == object_id)
                | (ArchitectureRelationship.target_object_id == object_id),
            )
        )
    )
    # Evidence is never silently dropped: refuse the removal while it is still
    # supported, so the caller can delete the evidence explicitly first.
    assert_no_evidence(
        db,
        workspace.tenant_id,
        [
            ("architecture_object", object_id),
            *(("architecture_relationship", edge.id) for edge in edges),
        ],
    )
    for edge in edges:
        db.delete(edge)
    registry = db.get(ArchitectureObject, object_id)
    if registry is not None:
        db.delete(registry)


def _remove_node(state: ArchitectureState, object_id: UUID) -> None:
    state.nodes = [
        node for node in state.nodes if str(node.get("object_id")) != str(object_id)
    ]
    state.updated_at = datetime.now(UTC)


def _remove_state_links(
    db: Session, workspace: Workspace, state: ArchitectureState, object_id: UUID
):
    db.execute(
        delete(ArchitectureRelationship).where(
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            ArchitectureRelationship.created_in_state_id == state.id,
            (ArchitectureRelationship.source_object_id == object_id)
            | (ArchitectureRelationship.target_object_id == object_id),
        )
    )


@router.get("/model", response_model=EnterpriseModelResponse)
def get_enterprise_model(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EnterpriseModelResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, state_id)
    return _build_model(db, workspace, state)


@router.post(
    "/objects",
    response_model=EnterpriseModelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enterprise_object(
    workspace_id: UUID,
    payload: EnterpriseObjectCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EnterpriseModelResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)

    kind = OBJECT_TYPE_TO_KIND[payload.kind]
    model = KIND_TABLE[kind]
    duplicate = db.scalar(
        select(model.object_id).where(
            model.tenant_id == workspace.tenant_id,
            model.name == payload.name.strip(),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {payload.kind} with this name already exists",
        )

    object_id = uuid4()
    registry = ArchitectureObject(id=object_id, tenant_id=workspace.tenant_id, kind=kind)
    values: dict = {
        "name": payload.name.strip(),
        "description": payload.description.strip() if payload.description else None,
    }
    for field in EXTRA_FIELDS[payload.kind]:
        value = getattr(payload, field)
        values[field] = value.strip() if isinstance(value, str) and value else value
    if kind in NEW_KINDS:
        values["created_in_state_id"] = state.id
    row = model(object_id=object_id, tenant_id=workspace.tenant_id, **values)

    node = ArchitectureStateNode(
        occurrence_id=f"occ-{uuid4()}",
        object_id=object_id,
        position=payload.position or {"x": 0.0, "y": 0.0},
        discipline="enterprise",
    ).model_dump(mode="json")
    nodes = list(state.nodes)
    nodes.append(node)

    db.add(registry)
    db.flush()
    db.add(row)
    state.nodes = nodes
    state.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(state)
    logger.info(
        "enterprise object created workspace=%s kind=%s object=%s state=%s",
        workspace.id,
        payload.kind,
        object_id,
        state.id,
    )
    return _build_model(db, workspace, state)


@router.patch("/objects/{object_id}", response_model=EnterpriseModelResponse)
def update_enterprise_object(
    workspace_id: UUID,
    object_id: UUID,
    payload: EnterpriseObjectUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EnterpriseModelResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    registry = _get_registry(db, workspace, object_id, ENTERPRISE_OBJECT_KINDS)
    row = _get_typed_row(db, workspace, registry)
    changes = payload.model_dump(exclude_unset=True)
    state_id = changes.pop("state_id", None)
    if state_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="state_id is required to scope an edit",
        )
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    object_type = KIND_TO_OBJECT_TYPE[registry.kind]
    allowed = {"name", "description", *EXTRA_FIELDS[object_type]}
    changes = {key: value for key, value in changes.items() if key in allowed}

    if _present_in_current(db, workspace, object_id):
        _set_node_overrides(state, object_id, changes)
    else:
        for field, value in changes.items():
            setattr(row, field, value.strip() if isinstance(value, str) and value else value)
        row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(state)
    logger.info(
        "enterprise object updated workspace=%s object=%s state=%s",
        workspace.id,
        object_id,
        state.id,
    )
    return _build_model(db, workspace, state)


@router.delete("/objects/{object_id}", response_model=EnterpriseModelResponse)
def delete_enterprise_object(
    workspace_id: UUID,
    object_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EnterpriseModelResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    registry = _get_registry(db, workspace, object_id, ENTERPRISE_OBJECT_KINDS)
    row = _get_typed_row(db, workspace, registry)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    if getattr(row, "created_in_state_id", None) == state.id:
        _purge_object(db, workspace, object_id)
    else:
        _remove_state_links(db, workspace, state, object_id)
    _remove_node(state, object_id)
    db.commit()
    db.refresh(state)
    logger.info(
        "enterprise object deleted workspace=%s object=%s state=%s",
        workspace.id,
        object_id,
        state.id,
    )
    return _build_model(db, workspace, state)


@router.post("/links", response_model=EnterpriseModelResponse, status_code=status.HTTP_201_CREATED)
def create_enterprise_link(
    workspace_id: UUID,
    payload: EnterpriseLinkCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EnterpriseModelResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, payload.state_id)
    _assert_writable(state)

    rule = LINK_RULES.get(payload.relationship_type)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown enterprise relationship type",
        )
    if payload.source_object_id == payload.target_object_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A link must connect two different objects",
        )
    source_kinds, target_kinds = rule
    source = _get_registry(
        db, workspace, payload.source_object_id, source_kinds | ENTERPRISE_OBJECT_KINDS
    )
    target = _get_registry(
        db, workspace, payload.target_object_id, target_kinds | ENTERPRISE_OBJECT_KINDS
    )
    if source.kind not in source_kinds or target.kind not in target_kinds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{payload.relationship_type}' cannot connect these object types",
        )
    existing = db.scalar(
        select(ArchitectureRelationship.id).where(
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            ArchitectureRelationship.relationship_type == payload.relationship_type,
            ArchitectureRelationship.source_object_id == payload.source_object_id,
            ArchitectureRelationship.target_object_id == payload.target_object_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This link already exists",
        )
    db.add(
        ArchitectureRelationship(
            id=uuid4(),
            tenant_id=workspace.tenant_id,
            source_object_id=payload.source_object_id,
            target_object_id=payload.target_object_id,
            relationship_type=payload.relationship_type,
            properties={},
            created_in_state_id=state.id,
        )
    )
    db.commit()
    db.refresh(state)
    logger.info(
        "enterprise link created workspace=%s type=%s source=%s target=%s state=%s",
        workspace.id,
        payload.relationship_type,
        payload.source_object_id,
        payload.target_object_id,
        state.id,
    )
    return _build_model(db, workspace, state)


@router.delete("/links/{link_id}", response_model=EnterpriseModelResponse)
def delete_enterprise_link(
    workspace_id: UUID,
    link_id: UUID,
    state_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EnterpriseModelResponse:
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, state_id)
    _assert_writable(state)
    edge = db.scalar(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.id == link_id,
            ArchitectureRelationship.tenant_id == workspace.tenant_id,
            ArchitectureRelationship.relationship_type.in_(ENTERPRISE_LINK_TYPES),
        )
    )
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    if edge.created_in_state_id != state.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This link belongs to another state and cannot be removed here",
        )
    db.delete(edge)
    db.commit()
    db.refresh(state)
    logger.info(
        "enterprise link deleted workspace=%s link=%s state=%s", workspace.id, link_id, state.id
    )
    return _build_model(db, workspace, state)


def _graph(
    model: EnterpriseModelResponse,
) -> tuple[
    dict[UUID, EnterpriseObjectResponse],
    dict[UUID, EnterpriseApplicationResponse],
    dict[UUID, list[EnterpriseLinkResponse]],
    dict[UUID, list[EnterpriseLinkResponse]],
]:
    by_id: dict[UUID, EnterpriseObjectResponse] = {}
    for group in (
        model.goals,
        model.requirements,
        model.capabilities,
        model.processes,
        model.principles,
        model.roles,
    ):
        for obj in group:
            by_id[obj.object_id] = obj
    apps = {app.object_id: app for app in model.applications}
    outgoing: dict[UUID, list[EnterpriseLinkResponse]] = defaultdict(list)
    incoming: dict[UUID, list[EnterpriseLinkResponse]] = defaultdict(list)
    for link in model.links:
        outgoing[link.source_object_id].append(link)
        incoming[link.target_object_id].append(link)
    return by_id, apps, outgoing, incoming


def _targets(
    by_id: dict[UUID, EnterpriseObjectResponse],
    links: list[EnterpriseLinkResponse],
    relationship_type: str,
    key: str,
) -> list[EnterpriseObjectResponse]:
    result = []
    for link in links:
        if link.relationship_type != relationship_type:
            continue
        obj = by_id.get(getattr(link, key))
        if obj is not None:
            result.append(obj)
    return result


def _apps_for(
    apps: dict[UUID, EnterpriseApplicationResponse],
    links: list[EnterpriseLinkResponse],
    relationship_type: str,
    key: str,
) -> list[EnterpriseApplicationResponse]:
    result = []
    for link in links:
        if link.relationship_type != relationship_type:
            continue
        app = apps.get(getattr(link, key))
        if app is not None:
            result.append(app)
    return result


def _dedupe(items: list) -> list:
    seen: dict = {}
    for item in items:
        seen[item.object_id] = item
    return sorted(seen.values(), key=lambda item: item.name)


def _strategy_gaps(model: EnterpriseModelResponse) -> list[str]:
    by_id, apps, outgoing, incoming = _graph(model)
    gaps: list[str] = []
    for goal in model.goals:
        requirements = _targets(by_id, outgoing[goal.object_id], "drives", "target_object_id")
        if not requirements:
            gaps.append(f"Goal '{goal.name}' has no linked requirement")
            continue
        for requirement in requirements:
            capabilities = _targets(
                by_id, outgoing[requirement.object_id], "needs", "target_object_id"
            )
            if not capabilities:
                gaps.append(f"Requirement '{requirement.name}' has no linked capability")
                continue
            for capability in capabilities:
                processes = _targets(
                    by_id, outgoing[capability.object_id], "has_process", "target_object_id"
                )
                if not processes:
                    gaps.append(f"Capability '{capability.name}' has no linked process")
                for process in processes:
                    support = _apps_for(
                        apps, incoming[process.object_id], "supports", "source_object_id"
                    )
                    if not support:
                        gaps.append(f"Process '{process.name}' has no supporting system")
    return gaps


@router.get("/capability-map", response_model=CapabilityMapResponse)
def capability_map(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CapabilityMapResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)
    by_id, apps, outgoing, incoming = _graph(model)
    entries: list[CapabilityMapEntry] = []
    for capability in model.capabilities:
        principles = _targets(
            by_id, outgoing[capability.object_id], "governed_by", "target_object_id"
        )
        owner_roles = _targets(
            by_id, outgoing[capability.object_id], "owned_by", "target_object_id"
        )
        entries.append(
            CapabilityMapEntry(
                capability=capability,
                processes=_dedupe(
                    _targets(
                        by_id, outgoing[capability.object_id], "has_process", "target_object_id"
                    )
                ),
                applications=_dedupe(
                    _apps_for(
                        apps, incoming[capability.object_id], "supports", "source_object_id"
                    )
                ),
                principles=_dedupe(principles),
                owner_role=owner_roles[0] if owner_roles else None,
            )
        )
    logger.info("capability map generated workspace=%s state=%s", workspace.id, state.id)
    return CapabilityMapResponse(state_id=state.id, capabilities=entries)


@router.get("/process-impact", response_model=ProcessImpactResponse)
def process_impact(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ProcessImpactResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)
    by_id, apps, outgoing, incoming = _graph(model)
    entries: list[ProcessImpactEntry] = []
    for process in model.processes:
        capabilities = _dedupe(
            _targets(by_id, incoming[process.object_id], "has_process", "source_object_id")
        )
        requirements: list[EnterpriseObjectResponse] = []
        for capability in capabilities:
            requirements.extend(
                _targets(by_id, incoming[capability.object_id], "needs", "source_object_id")
            )
        governed_by = _dedupe(
            _targets(by_id, outgoing[process.object_id], "governed_by", "target_object_id")
        )
        impacted = any(
            link.relationship_type in ("impacts", "affects") for link in incoming[process.object_id]
        ) or bool(governed_by)
        entries.append(
            ProcessImpactEntry(
                process=process,
                capabilities=capabilities,
                applications=_dedupe(
                    _apps_for(apps, incoming[process.object_id], "supports", "source_object_id")
                ),
                requirements=_dedupe(requirements),
                governed_by=governed_by,
                impacted=impacted,
            )
        )
    logger.info("process impact generated workspace=%s state=%s", workspace.id, state.id)
    return ProcessImpactResponse(state_id=state.id, processes=entries)


@router.get("/application-support", response_model=ApplicationSupportResponse)
def application_support(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ApplicationSupportResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)
    by_id, apps, outgoing, _incoming = _graph(model)
    entries: list[ApplicationSupportEntry] = []
    for application in model.applications:
        supported = _targets(by_id, outgoing[application.object_id], "supports", "target_object_id")
        capabilities = [item for item in supported if item.kind == "capability"]
        processes = [item for item in supported if item.kind == "process"]
        requirements = _targets(
            by_id, outgoing[application.object_id], "satisfies", "target_object_id"
        )
        entries.append(
            ApplicationSupportEntry(
                application=application,
                capabilities=_dedupe(capabilities),
                processes=_dedupe(processes),
                requirements=_dedupe(requirements),
            )
        )
    logger.info("application support generated workspace=%s state=%s", workspace.id, state.id)
    return ApplicationSupportResponse(state_id=state.id, applications=entries)


@router.get("/strategy-trace", response_model=StrategyTraceResponse)
def strategy_trace(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> StrategyTraceResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, state_id)
    model = _build_model(db, workspace, state)
    by_id, apps, outgoing, incoming = _graph(model)
    chains: list[StrategyTraceChain] = []
    linked_requirements: set[UUID] = set()
    for goal in model.goals:
        gaps: list[str] = []
        steps: list[StrategyTraceStep] = []
        requirements = _dedupe(
            _targets(by_id, outgoing[goal.object_id], "drives", "target_object_id")
        )
        if not requirements:
            gaps.append(f"Goal '{goal.name}' has no linked requirement")
        for requirement in requirements:
            linked_requirements.add(requirement.object_id)
            capabilities = _dedupe(
                _targets(by_id, outgoing[requirement.object_id], "needs", "target_object_id")
            )
            if not capabilities:
                gaps.append(f"Requirement '{requirement.name}' has no linked capability")
            processes: list[EnterpriseObjectResponse] = []
            applications: list[EnterpriseApplicationResponse] = []
            for capability in capabilities:
                capability_processes = _dedupe(
                    _targets(
                        by_id, outgoing[capability.object_id], "has_process", "target_object_id"
                    )
                )
                if not capability_processes:
                    gaps.append(f"Capability '{capability.name}' has no linked process")
                processes.extend(capability_processes)
            for process in processes:
                support = _apps_for(
                    apps, incoming[process.object_id], "supports", "source_object_id"
                )
                if not support:
                    gaps.append(f"Process '{process.name}' has no supporting system")
                applications.extend(support)
            applications.extend(
                _apps_for(apps, incoming[requirement.object_id], "satisfies", "source_object_id")
            )
            steps.append(
                StrategyTraceStep(
                    requirement=requirement,
                    capabilities=_dedupe(capabilities),
                    processes=_dedupe(processes),
                    applications=_dedupe(applications),
                )
            )
        chains.append(StrategyTraceChain(goal=goal, steps=steps, gaps=gaps))
    unlinked = [req for req in model.requirements if req.object_id not in linked_requirements]
    logger.info("strategy trace generated workspace=%s state=%s", workspace.id, state.id)
    return StrategyTraceResponse(
        state_id=state.id,
        chains=chains,
        unlinked_requirements=unlinked,
        gaps=_strategy_gaps(model),
    )


def _index_objects(model: EnterpriseModelResponse) -> dict[UUID, EnterpriseObjectResponse]:
    index: dict[UUID, EnterpriseObjectResponse] = {}
    for group in (
        model.goals,
        model.requirements,
        model.capabilities,
        model.processes,
        model.principles,
        model.roles,
    ):
        for obj in group:
            index[obj.object_id] = obj
    return index


@router.get("/impact", response_model=EnterpriseImpactResponse)
def enterprise_impact(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EnterpriseImpactResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_enterprise(workspace)
    state = _get_state(db, workspace, state_id)
    candidate = _build_model(db, workspace, state)
    baseline_state = _current_state(db, workspace)
    baseline = _build_model(db, workspace, baseline_state) if baseline_state else None

    candidate_objects = _index_objects(candidate)
    baseline_objects = _index_objects(baseline) if baseline else {}

    changes: list[ImpactChange] = []
    affected_capabilities: list[EnterpriseObjectResponse] = []
    affected_processes: list[EnterpriseObjectResponse] = []
    changed_ids: set[UUID] = set()

    for object_id, obj in candidate_objects.items():
        base = baseline_objects.get(object_id)
        if base is None:
            changes.append(
                ImpactChange(
                    object_id=object_id, kind=obj.kind, name=obj.name, change="added"
                )
            )
            changed_ids.add(object_id)
            continue
        changed_fields = [
            field
            for field in COMPARABLE_FIELDS
            if getattr(obj, field, None) != getattr(base, field, None)
        ]
        if changed_fields:
            changes.append(
                ImpactChange(
                    object_id=object_id,
                    kind=obj.kind,
                    name=obj.name,
                    change="changed",
                    changed_fields=changed_fields,
                )
            )
            changed_ids.add(object_id)
        else:
            changes.append(
                ImpactChange(object_id=object_id, kind=obj.kind, name=obj.name, change="reused")
            )

    for object_id, obj in baseline_objects.items():
        if object_id not in candidate_objects:
            changes.append(
                ImpactChange(object_id=object_id, kind=obj.kind, name=obj.name, change="removed")
            )
            changed_ids.add(object_id)

    by_id, apps, outgoing, incoming = _graph(candidate)
    removed_ids = {
        object_id
        for object_id in baseline_objects
        if object_id not in candidate_objects
    }
    changed_seed = changed_ids | removed_ids

    for object_id in changed_seed:
        obj = candidate_objects.get(object_id) or baseline_objects.get(object_id)
        if obj is None:
            continue
        if obj.kind == "capability":
            affected_capabilities.append(obj)
        if obj.kind == "process":
            affected_processes.append(obj)
        # Requirement changes ripple to linked capabilities and processes.
        if obj.kind == "requirement":
            for link in outgoing.get(object_id, []):
                if link.relationship_type != "needs":
                    continue
                capability = by_id.get(link.target_object_id)
                if capability is not None:
                    affected_capabilities.append(capability)
                    for cap_link in outgoing.get(capability.object_id, []):
                        if cap_link.relationship_type == "has_process":
                            process = by_id.get(cap_link.target_object_id)
                            if process is not None:
                                affected_processes.append(process)

    affected_object_ids = {
        item.object_id for item in [*affected_capabilities, *affected_processes]
    }

    affected_applications: list[EnterpriseApplicationResponse] = []
    for object_id in affected_object_ids:
        for link in incoming.get(object_id, []):
            if link.relationship_type in ("supports", "satisfies"):
                app = apps.get(link.source_object_id)
                if app is not None:
                    affected_applications.append(app)

    candidate_ids = set(candidate_objects) | set(apps)
    unresolved_dependencies: list[str] = []
    for link in candidate.links:
        if link.relationship_type != "depends_on":
            continue
        if link.target_object_id not in candidate_ids:
            source = candidate_objects.get(link.source_object_id)
            label = source.name if source else "An object"
            unresolved_dependencies.append(f"{label} depends on an object missing from this state")

    unresolved_constraints: list[str] = []
    constraint_ids = {
        principle.object_id
        for principle in candidate.principles
        if principle.principle_type == "constraint"
    }
    governed = {
        link.target_object_id
        for link in candidate.links
        if link.relationship_type == "governed_by"
    }
    for principle in candidate.principles:
        if principle.object_id in constraint_ids and principle.object_id not in governed:
            unresolved_constraints.append(f"Constraint '{principle.name}' governs no object")

    risks = [principle for principle in candidate.principles if principle.principle_type == "risk"]

    logger.info(
        "impact comparison generated workspace=%s state=%s baseline=%s",
        workspace.id,
        state.id,
        baseline_state.id if baseline_state else None,
    )
    return EnterpriseImpactResponse(
        state_id=state.id,
        baseline_state_id=baseline_state.id if baseline_state else None,
        changes=changes,
        affected_applications=_dedupe(affected_applications),
        affected_capabilities=_dedupe(affected_capabilities),
        affected_processes=_dedupe(affected_processes),
        unresolved_dependencies=unresolved_dependencies,
        unresolved_constraints=unresolved_constraints,
        risks=_dedupe(risks),
        gaps=_strategy_gaps(candidate),
    )
