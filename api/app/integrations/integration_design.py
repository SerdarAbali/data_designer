"""Integration Architecture workbench API (Slice 4).

Read-only projections over the existing integration contract engine plus a thin
property editor (pattern, implementation status, resilience/security/routing
specification, interface links). This module deliberately does **not** create a
second contract, schema, mapping, transformation, scenario, or testing model: it
reuses ``integrations``, ``integration_field_refs``, the graph engine, and the
scenario/evaluation engine.

The workbench is workspace-scoped for discipline gating and Current/Candidate
awareness, but the underlying contracts remain tenant-scoped canonical records.
"""

import logging
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db import get_session
from app.integrations.graph import GraphDocument
from app.integrations.schemas import (
    IntegrationConformanceResponse,
    IntegrationContractDetail,
    IntegrationContractSummary,
    IntegrationCoverage,
    IntegrationEndpointRef,
    IntegrationFlowPhase,
    IntegrationFlowTransformation,
    IntegrationInterfaceRef,
    IntegrationInterfaceSummary,
    IntegrationLandscapeResponse,
    IntegrationMessageFlowResponse,
    IntegrationOperationSummary,
    IntegrationScenarioSequence,
    IntegrationScenarioStatus,
    IntegrationSequenceInteraction,
    IntegrationSequenceParticipant,
    IntegrationSequenceResponse,
)
from app.models import (
    ArchitectureInterface,
    ArchitectureState,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
    IntegrationFieldRef,
    InterfaceOperation,
    Scenario,
    SolutionComponent,
    Workspace,
)
from app.scenarios.routes import (
    collect_missing_references,
    evaluate_assertion,
    evaluate_step,
    load_reference_context,
    references_contract,
)
from app.scenarios.schemas import ScenarioDocument

logger = logging.getLogger("app.integrations.integration_design")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/integration-design",
    tags=["architecture"],
)

TARGET_DIRECTIONS = {
    "request": "target",
    "success-response": "response_target",
    "async-response": "response_target",
    "error-response": "error_response_target",
}

# A system counts as an integration runtime only when the modelled data proves it:
# its catalog kind is an explicit runtime kind, or its name names a runtime.
RUNTIME_SYSTEM_KINDS = {"integration_runtime", "integration_runtime_platform", "esb", "runtime"}
EVENT_PATTERNS = {"publish_subscribe", "event_streaming", "message_queue"}
FILE_PATTERNS = {"file_transfer", "batch"}
API_PATTERNS = {"request_reply", "api_gateway", "orchestration", "point_to_point"}
API_PROTOCOLS = {"https", "http", "rest", "grpc", "soap", "graphql"}
FLOW_ROLE_BY_NODE = {"validate": "validation", "ifelse": "routing", "constant": "constant"}


def _is_runtime_system(system: CatalogSystem | None) -> bool:
    if system is None:
        return False
    if (system.kind or "").strip().lower() in RUNTIME_SYSTEM_KINDS:
        return True
    return "runtime" in (system.name or "").strip().lower()


def _channel(
    integration: Integration,
    producer: ArchitectureInterface | None,
    consumer: ArchitectureInterface | None,
) -> tuple[str | None, str | None]:
    """Derive the modelled exchange channel from pattern and interface metadata only."""
    interfaces = [item for item in (producer, consumer) if item is not None]
    kinds = {(item.interface_kind or "").strip().lower() for item in interfaces}
    protocols = {(item.protocol or "").strip().lower() for item in interfaces}
    pattern = integration.pattern
    if pattern in EVENT_PATTERNS or "async" in kinds:
        return "event", "Event / topic"
    if pattern in FILE_PATTERNS:
        return "file", "File exchange"
    if pattern in API_PATTERNS or "sync" in kinds or bool(protocols & API_PROTOCOLS):
        return "api", "API endpoint"
    return None, None


def _flow_role(node_type: str) -> str:
    return FLOW_ROLE_BY_NODE.get(node_type, "transformation")


def _participant_for_system(
    system_by_participant: dict[str, UUID | None], system_id: UUID | None
) -> str | None:
    if system_id is None:
        return None
    for participant_id, candidate in system_by_participant.items():
        if candidate == system_id:
            return participant_id
    return None


def _require_integration(workspace: Workspace) -> None:
    if "integration" not in workspace.disciplines:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This architecture discipline is not enabled for the workspace",
        )


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


def _active_integrations(db: Session, workspace: Workspace, integration_id: UUID | None = None):
    query = select(Integration).where(
        Integration.tenant_id == workspace.tenant_id,
        Integration.deleted_at.is_(None),
    )
    if integration_id is not None:
        query = query.where(Integration.id == integration_id)
    return list(db.scalars(query.order_by(Integration.name, Integration.id)))


def _get_integration(db: Session, workspace: Workspace, integration_id: UUID) -> Integration:
    integration = db.scalar(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == workspace.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return integration


def _interfaces_by_id(db: Session, workspace: Workspace) -> dict[UUID, ArchitectureInterface]:
    rows = list(
        db.scalars(
            select(ArchitectureInterface).where(
                ArchitectureInterface.tenant_id == workspace.tenant_id
            )
        )
    )
    return {row.object_id: row for row in rows}


def _operations_by_interface(
    db: Session, workspace: Workspace
) -> dict[UUID, list[InterfaceOperation]]:
    grouped: dict[UUID, list[InterfaceOperation]] = defaultdict(list)
    for operation in db.scalars(
        select(InterfaceOperation)
        .where(InterfaceOperation.tenant_id == workspace.tenant_id)
        .order_by(InterfaceOperation.ordinal, InterfaceOperation.name)
    ):
        grouped[operation.interface_object_id].append(operation)
    return grouped


def _component_names(db: Session, workspace: Workspace) -> dict[UUID, str]:
    return {
        row.object_id: row.name
        for row in db.scalars(
            select(SolutionComponent).where(SolutionComponent.tenant_id == workspace.tenant_id)
        )
    }


def _interface_ref(
    interfaces: dict[UUID, ArchitectureInterface], interface_id: UUID | None
) -> IntegrationInterfaceRef | None:
    if interface_id is None:
        return None
    iface = interfaces.get(interface_id)
    if iface is None:
        return None
    return IntegrationInterfaceRef(
        object_id=iface.object_id,
        name=iface.name,
        direction=iface.direction,
        interface_kind=iface.interface_kind,
        protocol=iface.protocol,
        technology=iface.technology,
    )


def _interface_summary(
    interfaces: dict[UUID, ArchitectureInterface],
    operations: dict[UUID, list[InterfaceOperation]],
    components: dict[UUID, str],
    contract_ids: dict[UUID, list[UUID]],
    interface_id: UUID,
) -> IntegrationInterfaceSummary:
    iface = interfaces[interface_id]
    return IntegrationInterfaceSummary(
        object_id=iface.object_id,
        name=iface.name,
        description=iface.description,
        direction=iface.direction,
        interface_kind=iface.interface_kind,
        protocol=iface.protocol,
        technology=iface.technology,
        component_object_id=iface.component_object_id,
        component_name=(
            components.get(iface.component_object_id) if iface.component_object_id else None
        ),
        operations=[
            IntegrationOperationSummary(
                object_id=operation.object_id,
                name=operation.name,
                operation_kind=operation.operation_kind,
                description=operation.description,
            )
            for operation in operations.get(interface_id, [])
        ],
        contract_ids=contract_ids.get(interface_id, []),
    )


def _field_refs_by_integration(
    db: Session, workspace: Workspace
) -> dict[UUID, dict[str, set[UUID]]]:
    grouped: dict[UUID, dict[str, set[UUID]]] = defaultdict(lambda: defaultdict(set))
    for ref in db.scalars(
        select(IntegrationFieldRef).where(IntegrationFieldRef.tenant_id == workspace.tenant_id)
    ):
        grouped[ref.integration_id][ref.direction].add(ref.field_id)
    return grouped


def _active_field_names(db: Session, workspace: Workspace, object_id: UUID) -> dict[UUID, str]:
    return {
        field.id: field.name
        for field in db.scalars(
            select(CatalogField).where(
                CatalogField.tenant_id == workspace.tenant_id,
                CatalogField.object_id == object_id,
                CatalogField.deleted_at.is_(None),
            )
        )
    }


def _required_field_names(db: Session, workspace: Workspace, object_id: UUID) -> dict[UUID, str]:
    return {
        field.id: field.name
        for field in db.scalars(
            select(CatalogField).where(
                CatalogField.tenant_id == workspace.tenant_id,
                CatalogField.object_id == object_id,
                CatalogField.deleted_at.is_(None),
                CatalogField.required.is_(True),
            )
        )
    }


def _endpoint(
    systems: dict[UUID, CatalogSystem],
    objects: dict[UUID, CatalogObject],
    system_id: UUID,
    object_id: UUID,
) -> IntegrationEndpointRef:
    system = systems.get(system_id)
    obj = objects.get(object_id)
    return IntegrationEndpointRef(
        system_id=system_id,
        system_name=system.name if system else "Unknown system",
        object_id=object_id,
        object_name=obj.label if obj else "Unknown object",
        system_kind=system.kind if system else None,
        is_runtime=_is_runtime_system(system),
    )


def _contract_status(integration: Integration, mapped: int) -> str:
    base = integration.implementation_status or "draft"
    if base in ("built", "verified") and mapped == 0:
        return "attention"
    return base


def _resolve_idempotency_key_name(
    db: Session,
    workspace: Workspace,
    integration: Integration,
    specification: dict,
) -> str | None:
    """Human-readable name for the configured idempotency key field.

    The specification stores a field id; surfaces that only have the contract
    summary (landscape, resilience, message flow) need the field name so they do
    not display a raw UUID. Resolution is best-effort: an unknown or malformed id
    simply yields ``None`` so the caller falls back to a generic label.
    """

    raw = specification.get("idempotency_key_field_id")
    if not raw:
        return None
    try:
        field_id = UUID(str(raw))
    except (TypeError, ValueError):
        return None
    for object_id in (integration.source_object_id, integration.target_object_id):
        if object_id is None:
            continue
        name = _active_field_names(db, workspace, object_id).get(field_id)
        if name:
            return name
    return None


def _contract_summary(
    db: Session,
    workspace: Workspace,
    integration: Integration,
    *,
    systems: dict[UUID, CatalogSystem],
    objects: dict[UUID, CatalogObject],
    interfaces: dict[UUID, ArchitectureInterface],
    refs: dict[str, set[UUID]],
    scenario_counts: dict[UUID, int],
) -> IntegrationContractSummary:
    target_fields = _active_field_names(db, workspace, integration.target_object_id)
    mapped = refs.get("target", set()) & set(target_fields)
    specification = integration.specification or {}
    idempotency_key_field_name = _resolve_idempotency_key_name(
        db, workspace, integration, specification
    )
    return IntegrationContractSummary(
        id=integration.id,
        name=integration.name,
        description=integration.description,
        interaction_type=integration.interaction_type,
        pattern=integration.pattern,
        implementation_status=integration.implementation_status or "draft",
        revision=integration.revision,
        updated_at=integration.updated_at.isoformat() if integration.updated_at else None,
        status=_contract_status(integration, len(mapped)),
        source=_endpoint(
            systems, objects, integration.source_system_id, integration.source_object_id
        ),
        target=_endpoint(
            systems, objects, integration.target_system_id, integration.target_object_id
        ),
        producer_interface=_interface_ref(interfaces, integration.producer_interface_id),
        consumer_interface=_interface_ref(interfaces, integration.consumer_interface_id),
        has_request_graph=bool((integration.graph or {}).get("nodes")),
        has_response_graph=bool((integration.response_graph or {}).get("nodes")),
        has_error_graph=bool((integration.error_response_graph or {}).get("nodes")),
        specification=specification,
        idempotency_key_field_name=idempotency_key_field_name,
        target_fields_mapped=len(mapped),
        target_fields_total=len(target_fields),
        scenario_count=scenario_counts.get(integration.id, 0),
    )


def _transformation_label(node) -> str:
    config = node.config or {}
    for key in ("function", "separator", "expression", "operator", "source", "field"):
        value = config.get(key)
        if value not in (None, ""):
            return f"{node.type}: {value}"
    return node.type


def _phase(
    phase: str,
    graph: dict,
    *,
    source_fields: dict[UUID, str],
    target_fields: dict[UUID, str],
    target_refs: set[UUID],
    required_target_fields: set[UUID] | None = None,
) -> IntegrationFlowPhase:
    try:
        document = GraphDocument.model_validate(graph or {})
    except ValidationError:
        document = GraphDocument(version=1, nodes=[], edges=[])
    nodes = document.nodes
    transformations = [
        IntegrationFlowTransformation(
            node_id=node.id,
            type=node.type,
            label=_transformation_label(node),
            role=_flow_role(node.type),
            position={
                "x": float(node.position.get("x", 0.0)),
                "y": float(node.position.get("y", 0.0)),
            },
        )
        for node in nodes
        if node.type not in ("source", "target")
    ]
    mapped = target_refs & set(target_fields)
    required = required_target_fields or set()
    unmapped_required = [
        target_fields[field_id]
        for field_id in sorted(target_fields, key=lambda item: target_fields[item])
        if field_id in required and field_id not in mapped
    ]
    return IntegrationFlowPhase(
        phase=phase,
        configured=bool(nodes),
        node_count=len(nodes),
        transformation_count=len(transformations),
        transformations=transformations,
        source_field_count=len(source_fields),
        target_field_count=len(target_fields),
        mapped_target_count=len(mapped),
        target_fields=[target_fields[field_id] for field_id in sorted(mapped, key=str)],
        unmapped_required_fields=unmapped_required,
    )


def _contract_phases(
    db: Session,
    workspace: Workspace,
    integration: Integration,
    refs: dict[str, set[UUID]],
) -> list[IntegrationFlowPhase]:
    source_fields = _active_field_names(db, workspace, integration.source_object_id)
    target_fields = _active_field_names(db, workspace, integration.target_object_id)
    source_required = set(_required_field_names(db, workspace, integration.source_object_id))
    target_required = set(_required_field_names(db, workspace, integration.target_object_id))
    phases: list[IntegrationFlowPhase] = [
        _phase(
            "request",
            integration.graph,
            source_fields=source_fields,
            target_fields=target_fields,
            target_refs=refs.get("target", set()),
            required_target_fields=target_required,
        )
    ]
    if integration.interaction_type == "REQUEST_RESPONSE":
        phases.append(
            _phase(
                "success-response",
                integration.response_graph,
                source_fields=target_fields,
                target_fields=source_fields,
                target_refs=refs.get("response_target", set()),
                required_target_fields=source_required,
            )
        )
    if integration.interaction_type == "ASYNC_CALLBACK":
        phases.append(
            _phase(
                "async-response",
                integration.response_graph,
                source_fields=target_fields,
                target_fields=source_fields,
                target_refs=refs.get("response_target", set()),
                required_target_fields=source_required,
            )
        )
    if integration.error_response_object_id is not None:
        error_fields = _active_field_names(db, workspace, integration.error_response_object_id)
        phases.append(
            _phase(
                "error-response",
                integration.error_response_graph,
                source_fields=error_fields,
                target_fields=source_fields,
                target_refs=refs.get("error_response_target", set()),
                required_target_fields=source_required,
            )
        )
    return phases


def _coverage(
    db: Session, workspace: Workspace, object_id: UUID, refs: set[UUID]
) -> IntegrationCoverage:
    fields = _active_field_names(db, workspace, object_id)
    mapped = refs & set(fields)
    total = len(fields)
    return IntegrationCoverage(
        mapped=len(mapped),
        total=total,
        ratio=round(len(mapped) / total, 3) if total else 0.0,
    )


def _scenario_counts(db: Session, workspace: Workspace, integrations: list[Integration]) -> dict:
    scenarios = list(
        db.scalars(
            select(Scenario).where(
                Scenario.tenant_id == workspace.tenant_id,
                Scenario.deleted_at.is_(None),
            )
        )
    )
    counts: dict[UUID, int] = defaultdict(int)
    for integration in integrations:
        for scenario in scenarios:
            if references_contract(scenario, integration.id):
                counts[integration.id] += 1
    return counts


def _referencing_scenarios(db: Session, workspace: Workspace, integration: Integration):
    scenarios = list(
        db.scalars(
            select(Scenario)
            .where(
                Scenario.tenant_id == workspace.tenant_id,
                Scenario.deleted_at.is_(None),
            )
            .order_by(Scenario.name, Scenario.id)
        )
    )
    return [item for item in scenarios if references_contract(item, integration.id)]


def _is_outdated(scenario: Scenario, integration: Integration) -> bool:
    saved, revised = scenario.updated_at, integration.updated_at
    if saved is None or revised is None:
        return False
    if (saved.tzinfo is None) != (revised.tzinfo is None):
        return False
    return saved < revised


def _scenario_status(
    db: Session, workspace: Workspace, integration: Integration, scenario: Scenario
) -> tuple[str, int, str]:
    try:
        document = ScenarioDocument.model_validate(scenario.document)
    except ValidationError:
        return "failing", 0, "The scenario document is invalid"
    contract_steps = [step for step in document.steps() if step.kind == "contract"]
    field_assertions = [item for item in document.assertions if item.field_id is not None]
    step_count = len(contract_steps)
    if not contract_steps and not field_assertions:
        return "not_run", step_count, "No contract steps or field assertions to evaluate"
    if _is_outdated(scenario, integration):
        return "outdated", step_count, "The contract changed after this scenario was saved"
    context = load_reference_context(
        db, workspace.tenant_id, document, scenario.scope_integration_id
    )
    missing = collect_missing_references(document, context, scenario.scope_integration_id)
    missing_steps = {item.step_id for item in missing if item.step_id}
    by_step = {}
    failing = False
    for step in document.steps():
        result = evaluate_step(step, context, step.id in missing_steps)
        by_step[step.id] = result
        if result.outcome in {"failed", "mismatch", "skipped", "missing_reference"}:
            failing = True
    for assertion in document.assertions:
        if evaluate_assertion(assertion, by_step).status == "failed":
            failing = True
    if missing:
        return "failing", step_count, f"{len(missing)} missing reference(s)"
    return ("failing" if failing else "passing"), step_count, ""


@router.get("/landscape", response_model=IntegrationLandscapeResponse)
def integration_landscape(
    workspace_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> IntegrationLandscapeResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_integration(workspace)
    state = _get_state(db, workspace, state_id)

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
    interfaces = _interfaces_by_id(db, workspace)
    operations = _operations_by_interface(db, workspace)
    components = _component_names(db, workspace)
    refs_by_integration = _field_refs_by_integration(db, workspace)
    integrations = _active_integrations(db, workspace)
    scenario_counts = _scenario_counts(db, workspace, integrations)

    contract_ids_by_interface: dict[UUID, list[UUID]] = defaultdict(list)
    for integration in integrations:
        for interface_id in (
            integration.producer_interface_id,
            integration.consumer_interface_id,
        ):
            if interface_id is not None and interface_id in interfaces:
                contract_ids_by_interface[interface_id].append(integration.id)

    contracts = [
        _contract_summary(
            db,
            workspace,
            integration,
            systems=systems,
            objects=objects,
            interfaces=interfaces,
            refs=refs_by_integration.get(integration.id, {}),
            scenario_counts=scenario_counts,
        )
        for integration in integrations
    ]
    interface_summaries = [
        _interface_summary(
            interfaces, operations, components, contract_ids_by_interface, interface_id
        )
        for interface_id in sorted(interfaces, key=lambda item: interfaces[item].name)
    ]

    logger.info(
        "integration landscape generated workspace=%s state=%s contracts=%s interfaces=%s",
        workspace.id,
        state.id,
        len(contracts),
        len(interface_summaries),
    )
    return IntegrationLandscapeResponse(
        state_id=state.id,
        state_type=state.state_type,
        editable=state.state_type != "current",
        contracts=contracts,
        interfaces=interface_summaries,
    )


@router.get(
    "/contracts/{integration_id}",
    response_model=IntegrationContractDetail,
)
def integration_contract_detail(
    workspace_id: UUID,
    integration_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> IntegrationContractDetail:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_integration(workspace)
    _get_state(db, workspace, state_id)
    integration = _get_integration(db, workspace, integration_id)

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
    interfaces = _interfaces_by_id(db, workspace)
    operations = _operations_by_interface(db, workspace)
    components = _component_names(db, workspace)
    refs = _field_refs_by_integration(db, workspace).get(integration.id, {})
    scenario_counts = _scenario_counts(db, workspace, [integration])

    contract = _contract_summary(
        db,
        workspace,
        integration,
        systems=systems,
        objects=objects,
        interfaces=interfaces,
        refs=refs,
        scenario_counts=scenario_counts,
    )
    contract_ids_by_interface: dict[UUID, list[UUID]] = defaultdict(list)
    for interface_id in (integration.producer_interface_id, integration.consumer_interface_id):
        if interface_id is not None and interface_id in interfaces:
            contract_ids_by_interface[interface_id].append(integration.id)

    def summary_for(interface_id: UUID | None):
        if interface_id is None or interface_id not in interfaces:
            return None
        return _interface_summary(
            interfaces, operations, components, contract_ids_by_interface, interface_id
        )

    logger.info(
        "integration contract detail generated workspace=%s contract=%s",
        workspace.id,
        integration.id,
    )
    return IntegrationContractDetail(
        contract=contract,
        source_interface=summary_for(integration.producer_interface_id),
        target_interface=summary_for(integration.consumer_interface_id),
        phases=_contract_phases(db, workspace, integration, refs),
    )


@router.get(
    "/contracts/{integration_id}/flow",
    response_model=IntegrationMessageFlowResponse,
)
def integration_message_flow(
    workspace_id: UUID,
    integration_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> IntegrationMessageFlowResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_integration(workspace)
    _get_state(db, workspace, state_id)
    integration = _get_integration(db, workspace, integration_id)

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
    interfaces = _interfaces_by_id(db, workspace)
    refs = _field_refs_by_integration(db, workspace).get(integration.id, {})
    scenario_counts = _scenario_counts(db, workspace, [integration])
    contract = _contract_summary(
        db,
        workspace,
        integration,
        systems=systems,
        objects=objects,
        interfaces=interfaces,
        refs=refs,
        scenario_counts=scenario_counts,
    )
    spec = integration.specification or {}
    channel_kind, channel_label = _channel(
        integration,
        interfaces.get(integration.producer_interface_id)
        if integration.producer_interface_id
        else None,
        interfaces.get(integration.consumer_interface_id)
        if integration.consumer_interface_id
        else None,
    )
    logger.info(
        "integration message flow generated workspace=%s contract=%s",
        workspace.id,
        integration.id,
    )
    return IntegrationMessageFlowResponse(
        contract=contract,
        routing=str(spec.get("routing") or ""),
        trigger_config=integration.trigger_config or {},
        channel_kind=channel_kind,
        channel_label=channel_label,
        phases=_contract_phases(db, workspace, integration, refs),
    )


@router.get(
    "/contracts/{integration_id}/conformance",
    response_model=IntegrationConformanceResponse,
)
def integration_conformance(
    workspace_id: UUID,
    integration_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> IntegrationConformanceResponse:
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_integration(workspace)
    _get_state(db, workspace, state_id)
    integration = _get_integration(db, workspace, integration_id)
    refs = _field_refs_by_integration(db, workspace).get(integration.id, {})

    request_coverage = _coverage(
        db, workspace, integration.target_object_id, refs.get("target", set())
    )
    response_coverage = _coverage(
        db, workspace, integration.source_object_id, refs.get("response_target", set())
    )
    if integration.error_response_object_id is not None:
        error_coverage = _coverage(
            db,
            workspace,
            integration.source_object_id,
            refs.get("error_response_target", set()),
        )
    else:
        error_coverage = IntegrationCoverage()

    scenarios = _referencing_scenarios(db, workspace, integration)
    statuses: list[IntegrationScenarioStatus] = []
    summary = {"passing": 0, "failing": 0, "not_run": 0, "outdated": 0}
    for scenario in scenarios:
        status_value, step_count, message = _scenario_status(db, workspace, integration, scenario)
        summary[status_value] += 1
        statuses.append(
            IntegrationScenarioStatus(
                id=scenario.id,
                name=scenario.name,
                category=scenario.category,
                revision=scenario.revision,
                updated_at=scenario.updated_at.isoformat() if scenario.updated_at else None,
                status=status_value,
                step_count=step_count,
                message=message,
            )
        )

    logger.info(
        "integration conformance generated workspace=%s contract=%s scenarios=%s",
        workspace.id,
        integration.id,
        len(statuses),
    )
    return IntegrationConformanceResponse(
        contract_id=integration.id,
        contract_name=integration.name,
        revision=integration.revision,
        updated_at=integration.updated_at.isoformat() if integration.updated_at else None,
        request_coverage=request_coverage,
        response_coverage=response_coverage,
        error_coverage=error_coverage,
        scenarios=statuses,
        summary=summary,
    )


@router.get(
    "/contracts/{integration_id}/sequence",
    response_model=IntegrationSequenceResponse,
)
def integration_sequence(
    workspace_id: UUID,
    integration_id: UUID,
    state_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> IntegrationSequenceResponse:
    """Project referencing scenarios as participants and ordered interactions.

    This reuses the stored ``ScenarioDocument`` engine: it never re-evaluates or
    re-writes a scenario, it only reads the participants and step order that the
    sequence designer already owns.
    """
    workspace = get_accessible_workspace(db, user, workspace_id)
    _require_integration(workspace)
    _get_state(db, workspace, state_id)
    integration = _get_integration(db, workspace, integration_id)

    systems = {
        system.id: system
        for system in db.scalars(
            select(CatalogSystem).where(
                CatalogSystem.tenant_id == workspace.tenant_id,
                CatalogSystem.deleted_at.is_(None),
            )
        )
    }
    contracts_by_id = {item.id: item for item in _active_integrations(db, workspace)}
    scenarios = _referencing_scenarios(db, workspace, integration)

    sequences: list[IntegrationScenarioSequence] = []
    for scenario in scenarios:
        status_value, step_count, _ = _scenario_status(db, workspace, integration, scenario)
        base = {
            "id": scenario.id,
            "name": scenario.name,
            "category": scenario.category,
            "status": status_value,
            "revision": scenario.revision,
            "outdated": _is_outdated(scenario, integration),
            "step_count": step_count,
        }
        try:
            document = ScenarioDocument.model_validate(scenario.document)
        except ValidationError:
            sequences.append(IntegrationScenarioSequence(**base))
            continue

        system_by_participant: dict[str, UUID | None] = {}
        participants: list[IntegrationSequenceParticipant] = []
        for participant in document.participants:
            system = systems.get(participant.system_id) if participant.system_id else None
            system_by_participant[participant.id] = participant.system_id
            participants.append(
                IntegrationSequenceParticipant(
                    id=participant.id,
                    kind=participant.kind,
                    label=participant.label or (system.name if system else participant.id),
                    system_id=participant.system_id,
                    system_name=system.name if system else None,
                    is_runtime=_is_runtime_system(system),
                )
            )

        interactions: list[IntegrationSequenceInteraction] = []
        for step in document.steps():
            if step.kind == "contract":
                referenced = contracts_by_id.get(step.contract_id) if step.contract_id else None
                contract_label = referenced.name if referenced else "Contract"
                interactions.append(
                    IntegrationSequenceInteraction(
                        id=step.id,
                        kind=step.kind,
                        phase=step.phase,
                        from_id=_participant_for_system(
                            system_by_participant,
                            referenced.source_system_id if referenced else None,
                        ),
                        to_id=_participant_for_system(
                            system_by_participant,
                            referenced.target_system_id if referenced else None,
                        ),
                        label=f"{contract_label} · {step.phase or 'request'}",
                        contract_step=True,
                    )
                )
            else:
                interactions.append(
                    IntegrationSequenceInteraction(
                        id=step.id,
                        kind=step.kind,
                        phase=None,
                        from_id=step.from_participant_id,
                        to_id=step.to_participant_id,
                        label=step.label or step.kind,
                        contract_step=False,
                    )
                )
        sequences.append(
            IntegrationScenarioSequence(
                **base, participants=participants, interactions=interactions
            )
        )

    logger.info(
        "integration sequence generated workspace=%s contract=%s scenarios=%s",
        workspace.id,
        integration.id,
        len(sequences),
    )
    return IntegrationSequenceResponse(
        contract_id=integration.id,
        contract_name=integration.name,
        revision=integration.revision,
        scenarios=sequences,
    )
