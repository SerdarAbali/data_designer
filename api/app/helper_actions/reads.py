"""Bounded deterministic read helpers.

These wrap existing projections and models. They are strictly read-only, apply
workspace/tenant/discipline scoping, and return capped results with explicit
truncation metadata. They never return unrestricted graphs or workspace dumps.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select

from app.architecture.traceability import (
    KIND_DISCIPLINE,
    _build_graph,
    _load_names,
    _membership,
)
from app.helper_actions.context import (
    HelperContext,
    require_discipline,
    resolve_architecture_object,
    resolve_catalog_system,
    resolve_contract,
    resolve_state,
)
from app.helper_actions.schemas import ReadEnvelope, ReadRequest
from app.integrations.integration_design import _referencing_scenarios, _scenario_status
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
    SolutionBoundary,
    SolutionComponent,
    TrustBoundary,
)

MAX_ITEMS = 100
MAX_TRACE_NODES = 200

_TYPED_DETAIL: dict[str, tuple[Any, tuple[str, ...]]] = {
    "business_goal": (BusinessGoal, ("owner", "outcome_metric", "horizon")),
    "business_requirement": (BusinessRequirement, ()),
    "business_capability": (BusinessCapability, ()),
    "business_process": (BusinessProcess, ("owner", "process_type")),
    "architecture_principle": (ArchitecturePrinciple, ("principle_type", "rationale")),
    "organization_role": (OrganizationRole, ("role_type",)),
    "information_object": (
        InformationObject,
        ("owner", "steward", "authoritative_system_id", "classification", "sensitivity"),
    ),
    "solution_boundary": (SolutionBoundary, ("owner",)),
    "component": (
        SolutionComponent,
        ("component_type", "technology", "responsibility"),
    ),
    "interface": (ArchitectureInterface, ("direction", "interface_kind", "protocol", "technology")),
    "interface_operation": (InterfaceOperation, ("operation_kind", "ordinal")),
    "data_repository": (DataRepository, ("owner", "repository_type", "technology")),
    "deployment_node": (DeploymentNode, ("technology", "environment", "hosting")),
    "trust_boundary": (TrustBoundary, ("security_level",)),
    "information_attribute": (
        InformationAttribute,
        ("data_type", "required", "nullable", "is_key"),
    ),
}


def _cap(limit: int) -> int:
    return max(1, min(limit, MAX_ITEMS))


def _text(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    return value


def _envelope(
    helper: str,
    ctx: HelperContext,
    data: dict[str, Any],
    *,
    truncated: bool = False,
    limit: int | None = None,
    counts: dict[str, int] | None = None,
    notes: list[str] | None = None,
) -> ReadEnvelope:
    return ReadEnvelope(
        helper=helper,
        workspace_id=ctx.workspace_id,
        truncated=truncated,
        limit=limit,
        counts=counts or {},
        notes=notes or [],
        data=data,
    )


def _ref(reg: ArchitectureObject, names, membership) -> dict[str, Any]:
    name, description = names.names.get(reg.id, ("(unnamed)", None))
    return {
        "id": str(reg.id),
        "kind": reg.kind,
        "name": name,
        "description": description,
        "discipline": KIND_DISCIPLINE.get(reg.kind),
        "state_membership": membership.get(reg.id, "none"),
    }


def _object_states(ctx: HelperContext, object_id: UUID) -> list[dict[str, str]]:
    states = list(
        ctx.db.scalars(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == ctx.workspace_id,
                ArchitectureState.deleted_at.is_(None),
            )
        )
    )
    result: list[dict[str, str]] = []
    for state in states:
        present = any(str(node.get("object_id")) == str(object_id) for node in state.nodes)
        if not present:
            member = ctx.db.scalar(
                select(ArchitectureStateMember).where(
                    ArchitectureStateMember.state_id == state.id,
                    ArchitectureStateMember.object_id == object_id,
                    ArchitectureStateMember.membership == "included",
                )
            )
            present = member is not None
        if present:
            result.append({"state_id": str(state.id), "state_type": state.state_type})
    return result


def get_workspace_context(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:  # noqa: ARG001
    states = list(
        ctx.db.scalars(
            select(ArchitectureState)
            .where(
                ArchitectureState.workspace_id == ctx.workspace_id,
                ArchitectureState.deleted_at.is_(None),
            )
            .order_by(ArchitectureState.created_at.asc())
        )
    )
    current = next((s for s in states if s.state_type == "current"), None)
    data = {
        "workspace_id": str(ctx.workspace_id),
        "name": ctx.workspace.name,
        "description": ctx.workspace.description,
        "disciplines": sorted(ctx.disciplines),
        "current_state_id": str(current.id) if current else None,
        "states": [
            {"id": str(s.id), "name": s.name, "state_type": s.state_type} for s in states
        ],
    }
    return _envelope("get_workspace_context", ctx, data, counts={"states": len(states)})


def get_enabled_disciplines(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:  # noqa: ARG001
    disciplines = sorted(ctx.disciplines)
    return _envelope("get_enabled_disciplines", ctx, {"disciplines": disciplines})


def get_architecture_state(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.state_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "state_id is required")
    state = resolve_state(ctx, req.state_id)
    cap = _cap(req.limit)
    nodes = list(state.nodes or [])
    preview = [
        {
            "occurrence_id": node.get("occurrence_id"),
            "object_id": str(node.get("object_id")),
            "discipline": node.get("discipline"),
        }
        for node in nodes[:cap]
    ]
    data = {
        "id": str(state.id),
        "name": state.name,
        "state_type": state.state_type,
        "description": state.description,
        "node_count": len(nodes),
        "relationship_count": len(state.relationships or []),
        "nodes": preview,
    }
    return _envelope(
        "get_architecture_state",
        ctx,
        data,
        truncated=len(nodes) > cap,
        limit=cap,
        counts={"nodes": len(nodes)},
    )


def search_canonical_objects(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    names = _load_names(ctx.db, ctx.workspace)
    membership = _membership(ctx.db, ctx.workspace)
    query = (req.query or "").strip().lower()
    rows = list(
        ctx.db.scalars(
            select(ArchitectureObject).where(ArchitectureObject.tenant_id == ctx.tenant_id)
        )
    )
    items: list[dict[str, Any]] = []
    for reg in rows:
        discipline = KIND_DISCIPLINE.get(reg.kind)
        if discipline is not None and discipline not in ctx.disciplines:
            continue
        if req.kind and reg.kind != req.kind:
            continue
        name = names.names.get(reg.id, ("(unnamed)", None))[0]
        if query and query not in name.lower():
            continue
        items.append(_ref(reg, names, membership))
    items.sort(key=lambda item: (item["discipline"] or "~", item["kind"], item["name"].lower()))
    cap = _cap(req.limit)
    limited = items[:cap]
    return _envelope(
        "search_canonical_objects",
        ctx,
        {"objects": limited},
        truncated=len(items) > cap,
        limit=cap,
        counts={"total": len(items), "returned": len(limited)},
    )


def get_object_details(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.object_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "object_id is required")
    reg = resolve_architecture_object(ctx, req.object_id)
    names = _load_names(ctx.db, ctx.workspace)
    membership = _membership(ctx.db, ctx.workspace)
    name, description = names.names.get(reg.id, ("(unnamed)", None))
    detail: dict[str, Any] = {}
    spec = _TYPED_DETAIL.get(reg.kind)
    if spec is not None:
        model, fields = spec
        row = ctx.db.get(model, reg.id)
        if row is not None:
            detail["name"] = row.name
            detail["description"] = row.description
            for field_name in fields:
                detail[field_name] = _text(getattr(row, field_name, None))
    data = {
        "object": _ref(reg, names, membership),
        "detail": detail,
        "states": _object_states(ctx, reg.id),
    }
    return _envelope("get_object_details", ctx, data)


def get_object_relationships(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.object_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "object_id is required")
    reg = resolve_architecture_object(ctx, req.object_id)
    created_in = [None]
    if req.state_id is not None:
        state = resolve_state(ctx, req.state_id)
        created_in.append(state.id)
    rows = list(
        ctx.db.scalars(
            select(ArchitectureRelationship).where(
                ArchitectureRelationship.tenant_id == ctx.tenant_id,
                ArchitectureRelationship.created_in_state_id.in_(created_in),
                (ArchitectureRelationship.source_object_id == reg.id)
                | (ArchitectureRelationship.target_object_id == reg.id),
            )
        )
    )
    rows.sort(key=lambda r: (r.relationship_type, str(r.source_object_id), str(r.target_object_id)))
    cap = _cap(req.limit)
    limited = [
        {
            "id": str(row.id),
            "relationship_type": row.relationship_type,
            "source_object_id": str(row.source_object_id),
            "target_object_id": str(row.target_object_id),
            "created_in_state_id": (
                str(row.created_in_state_id) if row.created_in_state_id else None
            ),
        }
        for row in rows[:cap]
    ]
    return _envelope(
        "get_object_relationships",
        ctx,
        {"relationships": limited, "object_id": str(reg.id)},
        truncated=len(rows) > cap,
        limit=cap,
        counts={"total": len(rows), "returned": len(limited)},
        notes=["Stored typed relationships only; derived edges appear in usages and trace."],
    )


def _graph(ctx: HelperContext, state_id: UUID):
    state = resolve_state(ctx, state_id)
    return state, _build_graph(ctx.db, ctx.workspace, state)


def _neighbor_groups(object_id: UUID, nodes, edges):
    grouped: dict[str, list] = {}
    outgoing: list[dict[str, Any]] = []
    incoming: list[dict[str, Any]] = []
    for edge in edges:
        if edge.source_object_id == object_id:
            neighbor = nodes.get(edge.target_object_id)
            if neighbor is not None:
                outgoing.append(
                    {
                        "relationship_type": edge.relationship_type,
                        "direction": "outgoing",
                        "derived": edge.derived,
                        "object": neighbor.model_dump(mode="json"),
                    }
                )
                grouped.setdefault(edge.relationship_type, []).append(neighbor)
        elif edge.target_object_id == object_id:
            neighbor = nodes.get(edge.source_object_id)
            if neighbor is not None:
                incoming.append(
                    {
                        "relationship_type": edge.relationship_type,
                        "direction": "incoming",
                        "derived": edge.derived,
                        "object": neighbor.model_dump(mode="json"),
                    }
                )
                grouped.setdefault(edge.relationship_type, []).append(neighbor)
    return outgoing, incoming, grouped


def get_object_usages(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.object_id is None or req.state_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "object_id and state_id are required"
        )
    _state, (nodes, edges) = _graph(ctx, req.state_id)
    root = nodes.get(req.object_id)
    if root is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Architecture object not found")
    outgoing, incoming, grouped = _neighbor_groups(req.object_id, nodes, edges)
    cap = _cap(req.limit)
    groups = []
    for rel, items in sorted(grouped.items()):
        deduped: dict[str, Any] = {}
        for item in items:
            deduped.setdefault(str(item.id), item)
        ordered = sorted(deduped.values(), key=lambda n: n.name)
        groups.append(
            {
                "relationship_type": rel,
                "objects": [n.model_dump(mode="json") for n in ordered[:cap]],
                "truncated": len(ordered) > cap,
            }
        )
    data = {
        "state_id": str(req.state_id),
        "object": root.model_dump(mode="json"),
        "outgoing_count": len(outgoing),
        "incoming_count": len(incoming),
        "groups": groups,
    }
    return _envelope(
        "get_object_usages",
        ctx,
        data,
        counts={"outgoing": len(outgoing), "incoming": len(incoming), "groups": len(groups)},
    )


def trace_architecture_path(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.object_id is None or req.state_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "object_id and state_id are required"
        )
    state, (nodes, edges) = _graph(ctx, req.state_id)
    root = nodes.get(req.object_id)
    if root is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Architecture object not found")

    adjacency: dict[UUID, list[tuple[UUID, Any, str]]] = {}
    for edge in edges:
        if req.direction in ("both", "outgoing"):
            adjacency.setdefault(edge.source_object_id, []).append(
                (edge.target_object_id, edge, "outgoing")
            )
        if req.direction in ("both", "incoming"):
            adjacency.setdefault(edge.target_object_id, []).append(
                (edge.source_object_id, edge, "incoming")
            )

    depth = min(req.depth, 4)
    depths: dict[UUID, int] = {req.object_id: 0}
    collected: dict[UUID, Any] = {req.object_id: root}
    collected_edges: dict[str, Any] = {}
    queue: deque[UUID] = deque([req.object_id])
    truncated = False
    while queue:
        current = queue.popleft()
        current_depth = depths[current]
        if current_depth >= depth:
            continue
        for neighbor_id, edge, _dir in adjacency.get(current, []):
            collected_edges.setdefault(edge.id, edge)
            if neighbor_id not in depths:
                if len(depths) >= MAX_TRACE_NODES:
                    truncated = True
                    continue
                depths[neighbor_id] = current_depth + 1
                neighbor = nodes.get(neighbor_id)
                if neighbor is not None:
                    collected[neighbor_id] = neighbor
                queue.append(neighbor_id)
    node_list = sorted(collected.values(), key=lambda n: (depths.get(n.id, 0), n.name))
    data = {
        "state_id": str(state.id),
        "root": root.model_dump(mode="json"),
        "max_depth": depth,
        "nodes": [n.model_dump(mode="json") for n in node_list],
        "edges": [e.model_dump(mode="json") for e in collected_edges.values()],
        "depths": {str(k): v for k, v in depths.items()},
    }
    return _envelope(
        "trace_architecture_path",
        ctx,
        data,
        truncated=truncated,
        limit=MAX_TRACE_NODES,
        counts={"nodes": len(node_list), "edges": len(collected_edges)},
    )


def _state_object_ids(ctx: HelperContext, state: ArchitectureState) -> set[UUID]:
    ids: set[UUID] = set()
    for node in state.nodes or []:
        try:
            ids.add(UUID(str(node.get("object_id"))))
        except (ValueError, TypeError):
            continue
    members = ctx.db.scalars(
        select(ArchitectureStateMember).where(
            ArchitectureStateMember.state_id == state.id,
            ArchitectureStateMember.membership == "included",
        )
    )
    for member in members:
        ids.add(member.object_id)
    return ids


def compare_current_candidate(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.state_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "state_id is required")
    candidate = resolve_state(ctx, req.state_id)
    if req.baseline_state_id is not None:
        baseline = resolve_state(ctx, req.baseline_state_id)
    else:
        baseline = ctx.db.scalar(
            select(ArchitectureState).where(
                ArchitectureState.workspace_id == ctx.workspace_id,
                ArchitectureState.state_type == "current",
                ArchitectureState.deleted_at.is_(None),
            )
        )
        if baseline is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "No current state to compare against"
            )
    names = _load_names(ctx.db, ctx.workspace)
    membership = _membership(ctx.db, ctx.workspace)

    def refs(ids: set[UUID]) -> list[dict[str, Any]]:
        rows = list(
            ctx.db.scalars(
                select(ArchitectureObject).where(
                    ArchitectureObject.tenant_id == ctx.tenant_id,
                    ArchitectureObject.id.in_(ids),
                )
            )
        )
        return sorted(
            (_ref(reg, names, membership) for reg in rows),
            key=lambda item: (item["discipline"] or "~", item["name"].lower()),
        )

    base_ids = _state_object_ids(ctx, baseline)
    cand_ids = _state_object_ids(ctx, candidate)
    added = cand_ids - base_ids
    removed = base_ids - cand_ids
    common = cand_ids & base_ids
    cap = _cap(req.limit)
    data = {
        "state_id": str(candidate.id),
        "baseline_state_id": str(baseline.id),
        "added": refs(added)[:cap],
        "removed": refs(removed)[:cap],
        "common_count": len(common),
    }
    truncated = len(added) > cap or len(removed) > cap
    return _envelope(
        "compare_current_candidate",
        ctx,
        data,
        truncated=truncated,
        limit=cap,
        counts={"added": len(added), "removed": len(removed), "common": len(common)},
    )


def list_catalog_systems(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    rows = list(
        ctx.db.scalars(
            select(CatalogSystem)
            .where(
                CatalogSystem.tenant_id == ctx.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
            .order_by(CatalogSystem.name, CatalogSystem.id)
        )
    )
    cap = _cap(req.limit)
    limited = [
        {"id": str(row.id), "name": row.name, "kind": row.kind, "description": row.description}
        for row in rows[:cap]
    ]
    return _envelope(
        "list_catalog_systems",
        ctx,
        {"systems": limited},
        truncated=len(rows) > cap,
        limit=cap,
        counts={"total": len(rows), "returned": len(limited)},
    )


def _fields_for_object(ctx: HelperContext, object_id: UUID, cap: int) -> tuple[list[dict], int]:
    rows = list(
        ctx.db.scalars(
            select(CatalogField)
            .where(
                CatalogField.tenant_id == ctx.tenant_id,
                CatalogField.object_id == object_id,
                CatalogField.deleted_at.is_(None),
            )
            .order_by(CatalogField.position, CatalogField.name, CatalogField.id)
        )
    )
    limited = [
        {
            "id": str(row.id),
            "name": row.name,
            "label": row.label,
            "data_type": row.data_type,
            "required": row.required,
            "nullable": row.nullable,
        }
        for row in rows[:cap]
    ]
    return limited, len(rows)


def inspect_catalog_schema(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    cap = _cap(req.limit)
    if req.object_id is not None:
        obj = ctx.db.scalar(
            select(CatalogObject).where(
                CatalogObject.id == req.object_id,
                CatalogObject.tenant_id == ctx.tenant_id,
                CatalogObject.deleted_at.is_(None),
            )
        )
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalog object not found")
        fields, field_total = _fields_for_object(ctx, obj.id, cap)
        data = {
            "object": {"id": str(obj.id), "name": obj.name, "label": obj.label},
            "fields": fields,
        }
        return _envelope(
            "inspect_catalog_schema",
            ctx,
            data,
            truncated=field_total > cap,
            limit=cap,
            counts={"fields": field_total},
        )
    if req.system_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "system_id or object_id is required"
        )
    system = resolve_catalog_system(ctx, req.system_id)
    objects = list(
        ctx.db.scalars(
            select(CatalogObject)
            .where(
                CatalogObject.tenant_id == ctx.tenant_id,
                CatalogObject.system_id == system.id,
                CatalogObject.deleted_at.is_(None),
            )
            .order_by(CatalogObject.position, CatalogObject.name, CatalogObject.id)
        )
    )
    truncated = len(objects) > cap
    entries = []
    for obj in objects[:cap]:
        fields, field_total = _fields_for_object(ctx, obj.id, cap)
        entries.append(
            {
                "id": str(obj.id),
                "name": obj.name,
                "label": obj.label,
                "fields": fields,
                "field_count": field_total,
            }
        )
        truncated = truncated or field_total > cap
    data = {
        "system": {"id": str(system.id), "name": system.name, "kind": system.kind},
        "objects": entries,
    }
    return _envelope(
        "inspect_catalog_schema",
        ctx,
        data,
        truncated=truncated,
        limit=cap,
        counts={"objects": len(objects)},
    )


def _contract_payload(ctx: HelperContext, integration: Integration) -> dict[str, Any]:
    refs = list(
        ctx.db.scalars(
            select(IntegrationFieldRef).where(
                IntegrationFieldRef.tenant_id == ctx.tenant_id,
                IntegrationFieldRef.integration_id == integration.id,
            )
        )
    )
    direction_counts: dict[str, int] = {}
    for ref in refs:
        direction_counts[ref.direction] = direction_counts.get(ref.direction, 0) + 1
    target_fields = 0
    if integration.target_object_id is not None:
        target_fields = len(
            list(
                ctx.db.scalars(
                    select(CatalogField.id).where(
                        CatalogField.tenant_id == ctx.tenant_id,
                        CatalogField.object_id == integration.target_object_id,
                        CatalogField.deleted_at.is_(None),
                    )
                )
            )
        )
    mapped_target = direction_counts.get("target", 0)
    return {
        "id": str(integration.id),
        "name": integration.name,
        "description": integration.description,
        "interaction_type": integration.interaction_type,
        "pattern": integration.pattern,
        "implementation_status": integration.implementation_status,
        "revision": integration.revision,
        "source_system_id": str(integration.source_system_id),
        "source_object_id": str(integration.source_object_id),
        "target_system_id": str(integration.target_system_id),
        "target_object_id": str(integration.target_object_id),
        "producer_interface_id": _text(integration.producer_interface_id),
        "consumer_interface_id": _text(integration.consumer_interface_id),
        "target_fields_total": target_fields,
        "target_fields_mapped": mapped_target,
    }


def list_integration_contracts(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    rows = list(
        ctx.db.scalars(
            select(Integration)
            .where(
                Integration.tenant_id == ctx.tenant_id,
                Integration.deleted_at.is_(None),
            )
            .order_by(Integration.name, Integration.id)
        )
    )
    cap = _cap(req.limit)
    limited = [
        {
            "id": str(row.id),
            "name": row.name,
            "interaction_type": row.interaction_type,
            "pattern": row.pattern,
            "implementation_status": row.implementation_status,
            "revision": row.revision,
        }
        for row in rows[:cap]
    ]
    return _envelope(
        "list_integration_contracts",
        ctx,
        {"contracts": limited},
        truncated=len(rows) > cap,
        limit=cap,
        counts={"total": len(rows), "returned": len(limited)},
    )


def inspect_contract(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.contract_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "contract_id is required")
    integration = resolve_contract(ctx, req.contract_id)
    data = {"contract": _contract_payload(ctx, integration)}
    scenarios = _referencing_scenarios(ctx.db, ctx.workspace, integration)
    data["scenario_count"] = len(scenarios)
    return _envelope(
        "inspect_contract", ctx, data, counts={"scenarios": len(scenarios)}
    )


def inspect_mapping_coverage(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.contract_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "contract_id is required")
    integration = resolve_contract(ctx, req.contract_id)
    payload = _contract_payload(ctx, integration)
    refs = list(
        ctx.db.scalars(
            select(IntegrationFieldRef).where(
                IntegrationFieldRef.tenant_id == ctx.tenant_id,
                IntegrationFieldRef.integration_id == integration.id,
            )
        )
    )
    directions: dict[str, int] = {}
    for ref in refs:
        directions[ref.direction] = directions.get(ref.direction, 0) + 1
    total = payload["target_fields_total"]
    mapped = payload["target_fields_mapped"]
    data = {
        "contract_id": str(integration.id),
        "target_fields_total": total,
        "target_fields_mapped": mapped,
        "target_fields_unresolved": max(total - mapped, 0),
        "direction_counts": directions,
    }
    return _envelope(
        "inspect_mapping_coverage",
        ctx,
        data,
        counts={"mapped": mapped, "unresolved": max(total - mapped, 0)},
        notes=[
            "Coverage counts existing Catalog-field references only. "
            "Ambiguous mappings stay unresolved."
        ],
    )


def inspect_scenarios_and_conformance(ctx: HelperContext, req: ReadRequest) -> ReadEnvelope:
    if req.contract_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "contract_id is required")
    integration = resolve_contract(ctx, req.contract_id)
    scenarios = _referencing_scenarios(ctx.db, ctx.workspace, integration)
    cap = _cap(req.limit)
    entries = []
    summary: dict[str, int] = {}
    for scenario in scenarios[:cap]:
        status_value, step_count, message = _scenario_status(
            ctx.db, ctx.workspace, integration, scenario
        )
        summary[status_value] = summary.get(status_value, 0) + 1
        entries.append(
            {
                "id": str(scenario.id),
                "name": scenario.name,
                "category": scenario.category,
                "revision": scenario.revision,
                "status": status_value,
                "step_count": step_count,
                "message": message,
            }
        )
    data = {
        "contract_id": str(integration.id),
        "contract_name": integration.name,
        "contract_revision": integration.revision,
        "scenarios": entries,
        "summary": summary,
    }
    return _envelope(
        "inspect_scenarios_and_conformance",
        ctx,
        data,
        truncated=len(scenarios) > cap,
        limit=cap,
        counts={"scenarios": len(scenarios)},
        notes=["Read-only projection. No scenario is executed by this helper."],
    )


READ_HELPERS: dict[str, tuple[str | None, Callable[[HelperContext, ReadRequest], ReadEnvelope]]] = {
    "get_workspace_context": (None, get_workspace_context),
    "get_enabled_disciplines": (None, get_enabled_disciplines),
    "get_architecture_state": (None, get_architecture_state),
    "search_canonical_objects": (None, search_canonical_objects),
    "get_object_details": (None, get_object_details),
    "get_object_relationships": (None, get_object_relationships),
    "get_object_usages": (None, get_object_usages),
    "trace_architecture_path": (None, trace_architecture_path),
    "compare_current_candidate": (None, compare_current_candidate),
    "list_catalog_systems": (None, list_catalog_systems),
    "inspect_catalog_schema": (None, inspect_catalog_schema),
    "list_integration_contracts": ("integration", list_integration_contracts),
    "inspect_contract": ("integration", inspect_contract),
    "inspect_mapping_coverage": ("integration", inspect_mapping_coverage),
    "inspect_scenarios_and_conformance": ("integration", inspect_scenarios_and_conformance),
}


def run_read(ctx: HelperContext, helper_name: str, req: ReadRequest) -> ReadEnvelope:
    entry = READ_HELPERS.get(helper_name)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown read helper"
        )
    discipline, fn = entry
    require_discipline(ctx, discipline)
    return fn(ctx, req)
