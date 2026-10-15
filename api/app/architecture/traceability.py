"""Cross-discipline traceability API (Slice 5).

Builds one canonical graph over the shared registry: stored edges from
``architecture_relationships`` plus edges *derived* from parent foreign keys and
authoritative engine tables (attributes, operations, solution membership,
integration field refs, scenario contract references). Nothing here writes to
the database; derived edges are recomputed on read so they can never drift.

Endpoints
    GET ``/architecture-graph``          unified nodes + edges for a state
    GET ``/trace``                       neighbourhood traversal from an object
    GET ``/objects/{object_id}/usages``  grouped usages summary for an object
"""

import logging
from collections import defaultdict, deque
from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    ArchitectureGraphResponse,
    ObjectTraceResponse,
    TraceDirection,
    TraceEdge,
    TraceNeighbor,
    TraceObjectRef,
    TraceResponse,
    TraceStateMembership,
    TraceUsageGroup,
)
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db import get_session
from app.models import (
    ArchitectureInterface,
    ArchitectureObject,
    ArchitecturePrinciple,
    ArchitectureRelationship,
    ArchitectureState,
    ArchitectureStateMember,
    BusinessCapability,
    BusinessGoal,
    BusinessProcess,
    BusinessRequirement,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    DataRepository,
    DeploymentNode,
    InformationAttribute,
    InformationObject,
    Integration,
    IntegrationFieldRef,
    InterfaceOperation,
    OrganizationRole,
    Scenario,
    SolutionBoundary,
    SolutionComponent,
    SolutionMember,
    TrustBoundary,
    Workspace,
)

logger = logging.getLogger("app.architecture.traceability")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}",
    tags=["architecture"],
)

KIND_DISCIPLINE: dict[str, str | None] = {
    "business_requirement": "enterprise",
    "business_capability": "enterprise",
    "business_goal": "enterprise",
    "business_process": "enterprise",
    "architecture_principle": "enterprise",
    "organization_role": "enterprise",
    "information_object": "information",
    "information_attribute": "information",
    "catalog_object_ref": "information",
    "catalog_field_ref": "information",
    "solution_boundary": "solution",
    "component": "solution",
    "interface": "solution",
    "interface_operation": "solution",
    "data_repository": "solution",
    "deployment_node": "solution",
    "trust_boundary": "solution",
    "contract_ref": "integration",
    "scenario_ref": "integration",
    "system": None,
}

# relationship-type -> human label for the usages summary
USAGE_GROUP_LABELS = {
    "has_attribute": "Attributes",
    "has_operation": "Operations & events",
    "contains": "Components",
    "contains_component": "Components",
    "provides": "Provided interfaces",
    "requires": "Required interfaces",
    "has_interface": "Interfaces",
    "has_member": "Member systems",
    "has_repository": "Repositories",
    "has_deployment": "Deployment targets",
    "has_trust_boundary": "Trust boundaries",
    "belongs_to": "Belongs to",
    "realizes": "Physical realization",
    "mapped_by": "Mapped into contracts",
    "verified_by": "Tests & evidence",
    "produces": "Produced by contract",
    "consumes": "Consumed by contract",
    "references": "Entity relationships",
}

ENTERPRISE_TYPED = (
    BusinessRequirement,
    BusinessCapability,
    BusinessGoal,
    BusinessProcess,
    ArchitecturePrinciple,
    OrganizationRole,
)
SOLUTION_TYPED = (
    SolutionBoundary,
    SolutionComponent,
    ArchitectureInterface,
    DataRepository,
    DeploymentNode,
    TrustBoundary,
)

_EXTERNAL_KINDS = {"catalog_object_ref", "catalog_field_ref", "contract_ref", "scenario_ref"}


def _as_uuid(value) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _get_state(db: Session, workspace: Workspace, state_id: UUID) -> ArchitectureState:
    state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture state not found",
        )
    return state


def _load_names(db: Session, workspace: Workspace) -> SimpleNamespace:
    tenant_id = workspace.tenant_id
    names: dict[UUID, tuple[str, str | None]] = {}

    def collect(model) -> None:
        for row in db.scalars(select(model).where(model.tenant_id == tenant_id)):
            names[row.object_id] = (row.name, getattr(row, "description", None))

    for model in (*ENTERPRISE_TYPED, *SOLUTION_TYPED, InformationObject, InformationAttribute):
        collect(model)
    for operation in db.scalars(
        select(InterfaceOperation).where(InterfaceOperation.tenant_id == tenant_id)
    ):
        names[operation.object_id] = (operation.name, operation.description)
    for system in db.scalars(
        select(CatalogSystem).where(CatalogSystem.tenant_id == tenant_id)
    ):
        names[system.id] = (system.name, system.description)

    catalog_objects = {
        row.id: row.name
        for row in db.scalars(select(CatalogObject).where(CatalogObject.tenant_id == tenant_id))
    }
    catalog_fields = {
        row.id: row.name
        for row in db.scalars(select(CatalogField).where(CatalogField.tenant_id == tenant_id))
    }
    integrations = {
        row.id: (row.name, row.description)
        for row in db.scalars(
            select(Integration).where(
                Integration.tenant_id == tenant_id, Integration.deleted_at.is_(None)
            )
        )
    }
    scenarios = {
        row.id: (row.name, row.description)
        for row in db.scalars(
            select(Scenario).where(
                Scenario.tenant_id == tenant_id, Scenario.deleted_at.is_(None)
            )
        )
    }
    return SimpleNamespace(
        names=names,
        catalog_objects=catalog_objects,
        catalog_fields=catalog_fields,
        integrations=integrations,
        scenarios=scenarios,
    )


def _membership(db: Session, workspace: Workspace) -> dict[UUID, TraceStateMembership]:
    """Best membership per object across all live states (target > candidate > current)."""
    priority = {"none": 0, "current": 1, "candidate": 2, "target": 3}
    membership: dict[UUID, TraceStateMembership] = {}
    states = list(
        db.scalars(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == workspace.id,
                ArchitectureState.deleted_at.is_(None),
            )
        )
    )
    for state in states:
        state_type = state.state_type
        if state_type not in ("current", "candidate", "target"):
            state_type = "current"
        ids: set[UUID] = set()
        for node in state.nodes:
            object_id = _as_uuid(node.get("object_id"))
            if object_id is not None:
                ids.add(object_id)
        for member in db.scalars(
            select(ArchitectureStateMember).where(
                ArchitectureStateMember.state_id == state.id,
                ArchitectureStateMember.membership == "included",
            )
        ):
            ids.add(member.object_id)
        for object_id in ids:
            current = membership.get(object_id, "none")
            if priority[state_type] > priority[current]:
                membership[object_id] = state_type  # type: ignore[assignment]
    return membership


def _node_ref(
    object_id: UUID,
    kind: str,
    name: str,
    description: str | None,
    membership: dict[UUID, TraceStateMembership],
) -> TraceObjectRef:
    return TraceObjectRef(
        id=object_id,
        kind=kind,
        name=name or "(unnamed)",
        description=description,
        discipline=KIND_DISCIPLINE.get(kind),
        state_membership=membership.get(object_id, "none"),
        external=kind in _EXTERNAL_KINDS,
    )


def _build_graph(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
) -> tuple[dict[UUID, TraceObjectRef], list[TraceEdge]]:
    tenant_id = workspace.tenant_id
    membership = _membership(db, workspace)
    names = _load_names(db, workspace)

    # Resolve names lazily for registry rows.
    node_names: dict[UUID, tuple[str, str | None]] = {}
    registry_rows = list(
        db.scalars(
            select(ArchitectureObject).where(ArchitectureObject.tenant_id == tenant_id)
        )
    )
    for registry in registry_rows:
        resolved = names.names.get(registry.id)
        if resolved is None:
            if registry.kind == "catalog_object_ref" and registry.catalog_object_id:
                name = names.catalog_objects.get(registry.catalog_object_id)
                resolved = (name or "Catalog object", None)
            elif registry.kind == "catalog_field_ref" and registry.catalog_field_id:
                name = names.catalog_fields.get(registry.catalog_field_id)
                resolved = (name or "Catalog field", None)
            elif registry.kind == "contract_ref" and registry.integration_id:
                resolved = names.integrations.get(registry.integration_id)
            elif registry.kind == "scenario_ref" and registry.scenario_id:
                resolved = names.scenarios.get(registry.scenario_id)
        node_names[registry.id] = resolved or ("(unnamed)", None)

    nodes: dict[UUID, TraceObjectRef] = {}
    for registry in registry_rows:
        name, description = node_names[registry.id]
        nodes[registry.id] = _node_ref(
            registry.id, registry.kind, name, description, membership
        )

    # Synthesize external reference nodes for contracts and scenarios so the
    # graph is complete even before a registry-reference row is materialized.
    for integration in db.scalars(
        select(Integration).where(
            Integration.tenant_id == tenant_id, Integration.deleted_at.is_(None)
        )
    ):
        nodes.setdefault(
            integration.id,
            _node_ref(
                integration.id,
                "contract_ref",
                integration.name,
                integration.description,
                membership,
            ),
        )
    for scenario in db.scalars(
        select(Scenario).where(
            Scenario.tenant_id == tenant_id, Scenario.deleted_at.is_(None)
        )
    ):
        nodes.setdefault(
            scenario.id,
            _node_ref(
                scenario.id,
                "scenario_ref",
                scenario.name,
                scenario.description,
                membership,
            ),
        )

    edges: list[TraceEdge] = []
    seen: set[tuple[UUID, UUID, str]] = set()

    def add_edge(source: UUID | None, target: UUID | None, rel: str, *, derived: bool) -> None:
        if source is None or target is None or source == target:
            return
        if source not in nodes or target not in nodes:
            return
        key = (source, target, rel)
        if key in seen:
            return
        seen.add(key)
        edges.append(
            TraceEdge(
                id=f"{'d' if derived else 's'}-{source}-{target}-{rel}",
                source_object_id=source,
                target_object_id=target,
                relationship_type=rel,
                derived=derived,
            )
        )

    for edge in db.scalars(
        select(ArchitectureRelationship).where(
            ArchitectureRelationship.tenant_id == tenant_id,
            ArchitectureRelationship.created_in_state_id.in_([None, state.id]),
        )
    ):
        add_edge(
            edge.source_object_id,
            edge.target_object_id,
            edge.relationship_type,
            derived=False,
        )

    # --- Derived edges (recomputed each read) ---
    for attribute in db.scalars(
        select(InformationAttribute).where(InformationAttribute.tenant_id == tenant_id)
    ):
        add_edge(attribute.entity_object_id, attribute.object_id, "has_attribute", derived=True)
    for operation in db.scalars(
        select(InterfaceOperation).where(InterfaceOperation.tenant_id == tenant_id)
    ):
        add_edge(operation.interface_object_id, operation.object_id, "has_operation", derived=True)
    for component in db.scalars(
        select(SolutionComponent).where(SolutionComponent.tenant_id == tenant_id)
    ):
        add_edge(
            component.solution_object_id, component.object_id, "contains_component", derived=True
        )
        add_edge(
            component.parent_component_object_id,
            component.object_id,
            "contains_component",
            derived=True,
        )
    for interface in db.scalars(
        select(ArchitectureInterface).where(ArchitectureInterface.tenant_id == tenant_id)
    ):
        link = "requires" if interface.direction == "required" else "provides"
        add_edge(interface.component_object_id, interface.object_id, link, derived=True)
    for member in db.scalars(
        select(SolutionMember).where(SolutionMember.tenant_id == tenant_id)
    ):
        add_edge(member.solution_object_id, member.system_id, "has_member", derived=True)
    for repository in db.scalars(
        select(DataRepository).where(DataRepository.tenant_id == tenant_id)
    ):
        add_edge(
            repository.solution_object_id, repository.object_id, "has_repository", derived=True
        )
    for deployment in db.scalars(
        select(DeploymentNode).where(DeploymentNode.tenant_id == tenant_id)
    ):
        add_edge(
            deployment.solution_object_id, deployment.object_id, "has_deployment", derived=True
        )
    for trust in db.scalars(select(TrustBoundary).where(TrustBoundary.tenant_id == tenant_id)):
        add_edge(
            trust.solution_object_id, trust.object_id, "has_trust_boundary", derived=True
        )

    integ_rows = list(
        db.scalars(
            select(Integration).where(
                Integration.tenant_id == tenant_id, Integration.deleted_at.is_(None)
            )
        )
    )
    for integration in integ_rows:
        add_edge(integration.id, integration.producer_interface_id, "produces", derived=True)
        add_edge(integration.id, integration.consumer_interface_id, "consumes", derived=True)

    field_refs = list(
        db.scalars(
            select(ArchitectureObject).where(
                ArchitectureObject.tenant_id == tenant_id,
                ArchitectureObject.kind == "catalog_field_ref",
            )
        )
    )
    field_ref_by_field: dict[UUID, UUID] = {
        row.catalog_field_id: row.id for row in field_refs if row.catalog_field_id is not None
    }
    for ref in db.scalars(
        select(IntegrationFieldRef).where(IntegrationFieldRef.tenant_id == tenant_id)
    ):
        field_ref_id = field_ref_by_field.get(ref.field_id)
        add_edge(field_ref_id, ref.integration_id, "mapped_by", derived=True)

    valid_integration_ids = {row.id for row in integ_rows}
    for scenario in db.scalars(
        select(Scenario).where(
            Scenario.tenant_id == tenant_id, Scenario.deleted_at.is_(None)
        )
    ):
        document = scenario.document or {}
        contract_ids = [_as_uuid(value) for value in (document.get("contractIds") or [])]
        contract_ids = [cid for cid in contract_ids if cid is not None]
        if scenario.scope_integration_id is not None:
            contract_ids.append(scenario.scope_integration_id)
        for contract_id in set(contract_ids):
            if contract_id in valid_integration_ids:
                add_edge(contract_id, scenario.id, "verified_by", derived=True)

    return nodes, edges


@router.get("/architecture-graph", response_model=ArchitectureGraphResponse)
def architecture_graph(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureGraphResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = _get_state(db, workspace, state_id)
    nodes, edges = _build_graph(db, workspace, state)
    logger.info(
        "architecture graph workspace=%s state=%s nodes=%s edges=%s",
        workspace.id,
        state.id,
        len(nodes),
        len(edges),
    )
    ordered = sorted(
        nodes.values(), key=lambda node: (node.discipline or "~", node.kind, node.name)
    )
    return ArchitectureGraphResponse(state_id=state.id, nodes=ordered, edges=edges)


@router.get("/objects/{object_id}/usages", response_model=ObjectTraceResponse)
def object_usages(
    workspace_id: UUID,
    object_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ObjectTraceResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = _get_state(db, workspace, state_id)
    nodes, edges = _build_graph(db, workspace, state)
    root = nodes.get(object_id)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )

    outgoing: list[TraceNeighbor] = []
    incoming: list[TraceNeighbor] = []
    grouped: dict[str, list[TraceObjectRef]] = defaultdict(list)
    for edge in edges:
        if edge.source_object_id == object_id:
            neighbor = nodes.get(edge.target_object_id)
            if neighbor is not None:
                outgoing.append(
                    TraceNeighbor(
                        relationship_type=edge.relationship_type,
                        direction="outgoing",
                        derived=edge.derived,
                        object=neighbor,
                    )
                )
                grouped[edge.relationship_type].append(neighbor)
        elif edge.target_object_id == object_id:
            neighbor = nodes.get(edge.source_object_id)
            if neighbor is not None:
                incoming.append(
                    TraceNeighbor(
                        relationship_type=edge.relationship_type,
                        direction="incoming",
                        derived=edge.derived,
                        object=neighbor,
                    )
                )
                grouped[edge.relationship_type].append(neighbor)

    def dedupe(items: list[TraceObjectRef]) -> list[TraceObjectRef]:
        seen: dict[UUID, TraceObjectRef] = {}
        for item in items:
            seen.setdefault(item.id, item)
        return sorted(seen.values(), key=lambda item: item.name)

    outgoing = sorted(outgoing, key=lambda item: (item.relationship_type, item.object.name))
    incoming = sorted(incoming, key=lambda item: (item.relationship_type, item.object.name))

    disciplines = {root.discipline} if root.discipline else set()
    disciplines.update(item.object.discipline for item in outgoing if item.object.discipline)
    disciplines.update(item.object.discipline for item in incoming if item.object.discipline)

    groups: list[TraceUsageGroup] = []
    for rel, items in grouped.items():
        label = USAGE_GROUP_LABELS.get(rel, rel.replace("_", " ").capitalize())
        groups.append(TraceUsageGroup(label=label, objects=dedupe(items)))
    groups.sort(key=lambda group: group.label)

    physical_refs = dedupe(
        [
            item.object
            for item in [*outgoing, *incoming]
            if item.object.kind in ("catalog_object_ref", "catalog_field_ref")
        ]
    )
    tests = dedupe(
        [item.object for item in [*outgoing, *incoming] if item.object.kind == "scenario_ref"]
    )
    principles = dedupe(
        [
            item.object
            for item in [*outgoing, *incoming]
            if item.object.kind == "architecture_principle"
        ]
    )

    logger.info(
        "object usages workspace=%s state=%s object=%s outgoing=%s incoming=%s",
        workspace.id,
        state.id,
        object_id,
        len(outgoing),
        len(incoming),
    )
    return ObjectTraceResponse(
        state_id=state.id,
        object=root,
        disciplines=sorted(disciplines),
        outgoing=outgoing,
        incoming=incoming,
        groups=groups,
        physical_refs=physical_refs,
        tests=tests,
        principles=principles,
    )


@router.get("/trace", response_model=TraceResponse)
def trace(
    workspace_id: UUID,
    object_id: UUID,
    state_id: UUID,
    direction: TraceDirection = "both",
    depth: int = Query(default=3, ge=1, le=8),
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> TraceResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = _get_state(db, workspace, state_id)
    nodes, edges = _build_graph(db, workspace, state)
    root = nodes.get(object_id)
    if root is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture object not found",
        )

    adjacency: dict[UUID, list[tuple[UUID, TraceEdge, str]]] = defaultdict(list)
    for edge in edges:
        if direction in ("both", "outgoing"):
            adjacency[edge.source_object_id].append(
                (edge.target_object_id, edge, "outgoing")
            )
        if direction in ("both", "incoming"):
            adjacency[edge.target_object_id].append(
                (edge.source_object_id, edge, "incoming")
            )

    depths: dict[UUID, int] = {object_id: 0}
    collected: dict[UUID, TraceObjectRef] = {object_id: root}
    collected_edges: dict[str, TraceEdge] = {}
    queue: deque[UUID] = deque([object_id])
    while queue:
        current = queue.popleft()
        current_depth = depths[current]
        if current_depth >= depth:
            continue
        for neighbor_id, edge, _dir in adjacency.get(current, []):
            collected_edges.setdefault(edge.id, edge)
            if neighbor_id not in depths:
                depths[neighbor_id] = current_depth + 1
                neighbor = nodes.get(neighbor_id)
                if neighbor is not None:
                    collected[neighbor_id] = neighbor
                queue.append(neighbor_id)

    node_list = sorted(
        collected.values(), key=lambda node: (depths.get(node.id, 0), node.name)
    )
    logger.info(
        "trace workspace=%s state=%s object=%s direction=%s depth=%s nodes=%s",
        workspace.id,
        state.id,
        object_id,
        direction,
        depth,
        len(node_list),
    )
    return TraceResponse(
        state_id=state.id,
        direction=direction,
        max_depth=depth,
        root=root,
        nodes=node_list,
        edges=[edge for edge in collected_edges.values()],
        depths={str(key): value for key, value in depths.items()},
    )
