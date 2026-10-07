from collections import deque
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.engine import (
    EngineError,
    EngineLimitError,
    EngineLimits,
    EngineValidationError,
    FieldSpec,
    run_graph,
)
from app.integrations.graph import GraphDocument, GraphValidationError, validate_graph
from app.integrations.schemas import (
    ArchitectureAnalysisResponse,
    ArchitectureConflictField,
    ArchitectureFieldConflictResponse,
    ArchitectureIntegrationRef,
    ArchitectureIntegrationResponse,
    ArchitectureStatus,
    DependencyCreate,
    DependencyResponse,
    GraphUpdate,
    IntegrationCreate,
    IntegrationResponse,
    IntegrationUpdate,
    SampleRow,
    SimulationRequest,
    SimulationResponse,
)
from app.models import (
    AuthSession,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
    IntegrationDependency,
    IntegrationFieldRef,
    Tenant,
)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def active_integration(
    db: Session, tenant_id: UUID, integration_id: UUID, *, lock: bool = False
) -> Integration:
    query = select(Integration).where(
        Integration.id == integration_id,
        Integration.tenant_id == tenant_id,
        Integration.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    integration = db.scalar(query)
    if integration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration not found")
    return integration


def resolve_endpoint(
    db: Session,
    tenant_id: UUID,
    system_id: UUID,
    object_id: UUID,
) -> CatalogObject:
    system = db.scalar(
        select(CatalogSystem)
        .where(
            CatalogSystem.id == system_id,
            CatalogSystem.tenant_id == tenant_id,
            CatalogSystem.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if system is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Each integration endpoint must be an active object in its stated system",
        )
    obj = db.scalar(
        select(CatalogObject)
        .where(
            CatalogObject.id == object_id,
            CatalogObject.system_id == system_id,
            CatalogObject.tenant_id == tenant_id,
            CatalogObject.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if obj is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Each integration endpoint must be an active object in its stated system",
        )
    return obj


def active_fields(db: Session, tenant_id: UUID, object_id: UUID) -> dict[UUID, CatalogField]:
    fields = list(
        db.scalars(
            select(CatalogField)
            .where(
                CatalogField.tenant_id == tenant_id,
                CatalogField.object_id == object_id,
                CatalogField.deleted_at.is_(None),
            )
            .order_by(CatalogField.id)
            .with_for_update()
        )
    )
    return {field.id: field for field in fields}


def graph_references(
    db: Session,
    tenant_id: UUID,
    source_object_id: UUID,
    target_object_id: UUID,
    graph: GraphDocument,
    *,
    response: bool = False,
    response_phase: str = "response",
) -> set[tuple[UUID, str, UUID]]:
    object_ids = {source_object_id, target_object_id}
    fields = list(
        db.scalars(
            select(CatalogField)
            .where(
                CatalogField.tenant_id == tenant_id,
                CatalogField.object_id.in_(object_ids),
                CatalogField.deleted_at.is_(None),
            )
            .order_by(CatalogField.id)
            .with_for_update()
        )
    )
    source_fields = {
        field.id: field for field in fields if field.object_id == source_object_id
    }
    target_fields = {
        field.id: field for field in fields if field.object_id == target_object_id
    }
    graph_source_fields = target_fields if response else source_fields
    graph_target_fields = source_fields if response else target_fields
    try:
        refs = validate_graph(
            graph,
            {field_id: field.data_type for field_id, field in graph_source_fields.items()},
            {field_id: field.data_type for field_id, field in graph_target_fields.items()},
        )
    except GraphValidationError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[issue.model_dump() for issue in error.issues],
        ) from error
    return {
        (
            field_id,
            f"{response_phase}_{direction}" if response else direction,
            (
                (
                    target_object_id if direction == "source" else source_object_id
                )
                if response
                else (
                    source_object_id if direction == "source" else target_object_id
                )
            ),
        )
        for field_id, direction in refs
    }


def validate_sample_rows(
    rows,
    source_field_ids: set[UUID],
    *,
    label: str = "sample_rows",
    field_description: str = "active source",
) -> list[dict]:
    normalized: list[dict] = []
    for row_index, row in enumerate(rows):
        values: dict[str, object] = {}
        for raw_field_id, value in row.values.items():
            try:
                field_id = UUID(raw_field_id)
            except ValueError as error:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "invalid_sample_field_id",
                        "path": f"{label}[{row_index}].values.{raw_field_id}",
                        "message": f"Row keys must be active {field_description} field UUIDs",
                    },
                ) from error
            normalized_field_id = str(field_id)
            if normalized_field_id in values:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "duplicate_sample_field",
                        "path": f"{label}[{row_index}].values",
                        "message": "A sample row cannot contain the same field UUID more than once",
                    },
                )
            if field_id not in source_field_ids:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "unknown_sample_field",
                        "path": f"{label}[{row_index}].values.{raw_field_id}",
                        "message": f"Row keys must be active {field_description} field UUIDs",
                    },
                )
            values[normalized_field_id] = value
        normalized.append({"row_id": row.row_id, "values": values})
    return normalized


def sample_field_references(
    rows: list[dict], source_object_id: UUID
) -> set[tuple[UUID, str, UUID]]:
    return {
        (UUID(field_id), "source", source_object_id)
        for row in rows
        for field_id in row["values"]
    }


def replace_field_refs(
    db: Session,
    integration: Integration,
    refs: set[tuple[UUID, str, UUID]],
) -> None:
    db.execute(
        delete(IntegrationFieldRef).where(
            IntegrationFieldRef.integration_id == integration.id,
            IntegrationFieldRef.tenant_id == integration.tenant_id,
        )
    )
    db.add_all(
        [
            IntegrationFieldRef(
                integration_id=integration.id,
                tenant_id=integration.tenant_id,
                field_id=field_id,
                direction=direction,
                object_id=object_id,
            )
            for field_id, direction, object_id in refs
        ]
    )


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The integration change conflicts with existing data",
        ) from error


def check_revision(integration: Integration, expected_revision: int) -> None:
    if integration.revision != expected_revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "revision_conflict",
                "message": "The integration changed; reload it before saving",
                "current_revision": integration.revision,
            },
        )


def json_graph(graph: GraphDocument) -> dict:
    return graph.model_dump(mode="json", by_alias=True)


def engine_field_specs(fields: dict[UUID, CatalogField]) -> list[FieldSpec]:
    return [
        FieldSpec(
            id=str(field.id),
            data_type=field.data_type,
            required=field.required,
            nullable=field.nullable,
            has_default=field.default_value is not None,
            default_value=field.default_value,
        )
        for field in fields.values()
    ]


def run_simulation_graph(
    graph: GraphDocument,
    source_fields: list[FieldSpec],
    target_fields: list[FieldSpec],
    rows: list[dict],
    *,
    include_trace_values: bool,
):
    try:
        return run_graph(
            json_graph(graph),
            source_fields,
            target_fields,
            rows,
            limits=EngineLimits(include_trace_values=include_trace_values),
        )
    except EngineValidationError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": error.code,
                "message": error.message,
                "issues": [issue.to_dict() for issue in error.issues],
            },
        ) from error
    except EngineLimitError as error:
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if error.code in {"input_size_limit", "graph_size_limit", "output_limit"}
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    except EngineError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": error.code, "message": error.message},
        ) from error


@router.get("", response_model=list[IntegrationResponse])
def list_integrations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[Integration]:
    return list(
        db.scalars(
            select(Integration)
            .where(
                Integration.tenant_id == user.tenant_id,
                Integration.deleted_at.is_(None),
            )
            .order_by(Integration.name, Integration.id)
            .offset(offset)
            .limit(limit)
        )
    )


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
def create_integration(
    payload: IntegrationCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Integration:
    require_csrf(request, auth_session)
    endpoints = sorted(
        (
            (payload.source_system_id, payload.source_object_id),
            (payload.target_system_id, payload.target_object_id),
        ),
        key=lambda endpoint: (str(endpoint[0]), str(endpoint[1])),
    )
    for system_id, object_id in endpoints:
        resolve_endpoint(db, user.tenant_id, system_id, object_id)
    refs = graph_references(
        db,
        user.tenant_id,
        payload.source_object_id,
        payload.target_object_id,
        payload.graph,
    )
    response_refs = graph_references(
        db,
        user.tenant_id,
        payload.source_object_id,
        payload.target_object_id,
        payload.response_graph,
        response=True,
    )
    refs.update(response_refs)
    if payload.error_response_object_id is not None:
        resolve_endpoint(
            db,
            user.tenant_id,
            payload.target_system_id,
            payload.error_response_object_id,
        )
        refs.update(
            graph_references(
                db,
                user.tenant_id,
                payload.source_object_id,
                payload.error_response_object_id,
                payload.error_response_graph,
                response=True,
                response_phase="error_response",
            )
        )
    elif payload.error_response_graph.nodes or payload.error_response_graph.edges:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "An error response schema is required for its graph",
        )
    source_fields = active_fields(db, user.tenant_id, payload.source_object_id)
    sample_rows = validate_sample_rows(payload.sample_rows, set(source_fields))
    refs.update(sample_field_references(sample_rows, payload.source_object_id))

    integration = Integration(
        tenant_id=user.tenant_id,
        source_system_id=payload.source_system_id,
        source_object_id=payload.source_object_id,
        target_system_id=payload.target_system_id,
        target_object_id=payload.target_object_id,
        name=payload.name,
        description=payload.description,
        trigger_config=payload.trigger_config,
        graph=json_graph(payload.graph),
        response_graph=json_graph(payload.response_graph),
        error_response_graph=json_graph(payload.error_response_graph),
        error_response_object_id=payload.error_response_object_id,
        interaction_type=payload.interaction_type,
        sample_rows=sample_rows,
        revision=1,
    )
    db.add(integration)
    db.flush()
    replace_field_refs(db, integration, refs)
    commit_or_conflict(db)
    db.refresh(integration)
    return integration


@router.get("/architecture", response_model=ArchitectureAnalysisResponse)
def architecture_analysis(
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ArchitectureAnalysisResponse:
    integrations = list(
        db.scalars(
            select(Integration)
            .where(
                Integration.tenant_id == user.tenant_id,
                Integration.deleted_at.is_(None),
            )
            .order_by(Integration.name, Integration.id)
        )
    )
    integration_by_id = {item.id: item for item in integrations}
    integration_ids = set(integration_by_id)
    if not integration_ids:
        return ArchitectureAnalysisResponse(integrations=[], conflicts=[])

    target_refs = list(
        db.scalars(
            select(IntegrationFieldRef).where(
                IntegrationFieldRef.tenant_id == user.tenant_id,
                IntegrationFieldRef.direction.in_(
                    ("target", "response_target", "error_response_target")
                ),
                IntegrationFieldRef.integration_id.in_(integration_ids),
            )
        )
    )
    field_ids = {ref.field_id for ref in target_refs}
    fields = {
        field.id: field
        for field in db.scalars(
            select(CatalogField).where(
                CatalogField.tenant_id == user.tenant_id,
                CatalogField.id.in_(field_ids),
            )
        )
    } if field_ids else {}
    object_ids = {field.object_id for field in fields.values()}
    objects = {
        obj.id: obj
        for obj in db.scalars(
            select(CatalogObject).where(
                CatalogObject.tenant_id == user.tenant_id,
                CatalogObject.id.in_(object_ids),
            )
        )
    } if object_ids else {}

    writers: dict[tuple[UUID, UUID], set[UUID]] = {}
    target_mapping_count = {integration_id: 0 for integration_id in integration_ids}
    for ref in target_refs:
        key = (ref.object_id, ref.field_id)
        writers.setdefault(key, set()).add(ref.integration_id)
        target_mapping_count[ref.integration_id] += 1

    conflict_integration_keys: dict[UUID, list[tuple[UUID, UUID]]] = {
        integration_id: [] for integration_id in integration_ids
    }
    conflict_responses: list[ArchitectureFieldConflictResponse] = []
    for (object_id, field_id), writer_ids in sorted(
        writers.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
    ):
        if len(writer_ids) < 2:
            continue
        field = fields.get(field_id)
        obj = objects.get(object_id)
        if field is None or obj is None:
            continue
        conflict_integration_keys_for_field = (object_id, field_id)
        for integration_id in writer_ids:
            conflict_integration_keys[integration_id].append(
                conflict_integration_keys_for_field
            )
        conflict_responses.append(
            ArchitectureFieldConflictResponse(
                object_id=object_id,
                object_label=obj.label,
                field_id=field_id,
                field_label=field.label,
                integrations=[
                    ArchitectureIntegrationRef(
                        id=integration_id,
                        name=integration_by_id[integration_id].name,
                        status="attention",
                    )
                    for integration_id in sorted(
                        writer_ids,
                        key=lambda item_id: (
                            integration_by_id[item_id].name.casefold(),
                            str(item_id),
                        ),
                    )
                ],
            )
        )

    dependencies = list(
        db.scalars(
            select(IntegrationDependency).where(
                IntegrationDependency.tenant_id == user.tenant_id,
                IntegrationDependency.upstream_integration_id.in_(integration_ids),
                IntegrationDependency.downstream_integration_id.in_(integration_ids),
            )
        )
    )
    upstream_by_id: dict[UUID, set[UUID]] = {
        integration_id: set() for integration_id in integration_ids
    }
    for dependency in dependencies:
        upstream_by_id[dependency.downstream_integration_id].add(
            dependency.upstream_integration_id
        )

    downstream_by_id: dict[UUID, set[UUID]] = {
        integration_id: set() for integration_id in integration_ids
    }
    remaining_upstream_count = {
        integration_id: len(upstream_ids)
        for integration_id, upstream_ids in upstream_by_id.items()
    }
    for downstream_id, upstream_ids in upstream_by_id.items():
        for upstream_id in upstream_ids:
            downstream_by_id[upstream_id].add(downstream_id)
    ready = deque(
        sorted(
            (item_id for item_id, count in remaining_upstream_count.items() if count == 0),
            key=str,
        )
    )
    topological_order = []
    while ready:
        current = ready.popleft()
        topological_order.append(current)
        for downstream_id in sorted(downstream_by_id[current], key=str):
            remaining_upstream_count[downstream_id] -= 1
            if remaining_upstream_count[downstream_id] == 0:
                ready.append(downstream_id)

    status_by_id: dict[UUID, ArchitectureStatus] = {}
    for integration_id in topological_order:
        unhealthy_upstream = any(
            status_by_id[upstream_id] != "healthy"
            for upstream_id in upstream_by_id[integration_id]
        )
        if conflict_integration_keys[integration_id] or unhealthy_upstream:
            status_by_id[integration_id] = "attention"
        elif target_mapping_count[integration_id] == 0:
            status_by_id[integration_id] = "draft"
        else:
            status_by_id[integration_id] = "healthy"
    cycle_affected_ids = integration_ids - set(topological_order)
    for integration_id in cycle_affected_ids:
        status_by_id[integration_id] = "attention"

    analysis = []
    for integration in integrations:
        upstream_ids = sorted(
            upstream_by_id[integration.id],
            key=lambda item_id: (
                integration_by_id[item_id].name.casefold(),
                str(item_id),
            ),
        )
        upstream = [
            ArchitectureIntegrationRef(
                id=upstream_id,
                name=integration_by_id[upstream_id].name,
                status=status_by_id[upstream_id],
            )
            for upstream_id in upstream_ids
        ]
        status_value = status_by_id[integration.id]
        reasons = []
        if integration.id in cycle_affected_ids:
            reasons.append("A dependency cycle prevents reliable health analysis.")
        if target_mapping_count[integration.id] == 0:
            reasons.append("No target fields are mapped.")
        if conflict_integration_keys[integration.id]:
            reasons.append("One or more target fields have multiple active writers.")
        unhealthy_names = [item.name for item in upstream if item.status != "healthy"]
        if unhealthy_names:
            reasons.append(
                "Depends on unhealthy upstream integration(s): "
                + ", ".join(unhealthy_names)
                + "."
            )
        conflict_fields = [
            ArchitectureConflictField(
                object_id=object_id,
                object_label=objects[object_id].label,
                field_id=field_id,
                field_label=fields[field_id].label,
            )
            for object_id, field_id in conflict_integration_keys[integration.id]
            if object_id in objects and field_id in fields
        ]
        analysis.append(
            ArchitectureIntegrationResponse(
                id=integration.id,
                name=integration.name,
                status=status_value,
                reasons=reasons,
                target_mapping_count=target_mapping_count[integration.id],
                conflict_fields=conflict_fields,
                upstream=upstream,
            )
        )
    return ArchitectureAnalysisResponse(
        integrations=analysis,
        conflicts=conflict_responses,
    )


@router.get("/{integration_id}", response_model=IntegrationResponse)
def get_integration(
    integration_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Integration:
    return active_integration(db, user.tenant_id, integration_id)


@router.patch("/{integration_id}", response_model=IntegrationResponse)
def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Integration:
    require_csrf(request, auth_session)
    integration = active_integration(db, user.tenant_id, integration_id, lock=True)
    check_revision(integration, payload.expected_revision)
    updates = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if "sample_rows" in updates:
        source_fields = active_fields(db, user.tenant_id, integration.source_object_id)
        updates["sample_rows"] = validate_sample_rows(
            payload.sample_rows or [], set(source_fields)
        )
        refs = graph_references(
            db,
            user.tenant_id,
            integration.source_object_id,
            integration.target_object_id,
            GraphDocument.model_validate(integration.graph),
        )
        refs.update(
            graph_references(
                db,
                user.tenant_id,
                integration.source_object_id,
                integration.target_object_id,
                GraphDocument.model_validate(integration.response_graph),
                response=True,
            )
        )
        if integration.error_response_object_id is not None:
            refs.update(
                graph_references(
                    db,
                    user.tenant_id,
                    integration.source_object_id,
                    integration.error_response_object_id,
                    GraphDocument.model_validate(integration.error_response_graph),
                    response=True,
                    response_phase="error_response",
                )
            )
        refs.update(sample_field_references(updates["sample_rows"], integration.source_object_id))
        replace_field_refs(db, integration, refs)
    for key, value in updates.items():
        if key == "sample_rows":
            integration.sample_rows = value
        else:
            setattr(integration, key, value)
    integration.revision += 1
    integration.updated_at = datetime.now(UTC)
    commit_or_conflict(db)
    db.refresh(integration)
    return integration


@router.put("/{integration_id}/graph", response_model=IntegrationResponse)
def save_integration_graph(
    integration_id: UUID,
    payload: GraphUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Integration:
    require_csrf(request, auth_session)
    integration = active_integration(db, user.tenant_id, integration_id, lock=True)
    check_revision(integration, payload.expected_revision)
    refs = graph_references(
        db,
        user.tenant_id,
        integration.source_object_id,
        integration.target_object_id,
        payload.graph,
    )
    response_graph = payload.response_graph or GraphDocument.model_validate(
        integration.response_graph
    )
    refs.update(
        graph_references(
            db,
            user.tenant_id,
            integration.source_object_id,
            integration.target_object_id,
            response_graph,
            response=True,
        )
    )
    error_response_object_id = (
        payload.error_response_object_id
        if "error_response_object_id" in payload.model_fields_set
        else integration.error_response_object_id
    )
    error_response_graph = (
        payload.error_response_graph
        or GraphDocument.model_validate(integration.error_response_graph)
    )
    if error_response_object_id is None:
        if error_response_graph.nodes or error_response_graph.edges:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "An error response schema is required for its graph",
            )
        error_response_graph = GraphDocument(version=1, nodes=[], edges=[])
    else:
        resolve_endpoint(
            db,
            user.tenant_id,
            integration.target_system_id,
            error_response_object_id,
        )
        refs.update(
            graph_references(
                db,
                user.tenant_id,
                integration.source_object_id,
                error_response_object_id,
                error_response_graph,
                response=True,
                response_phase="error_response",
            )
        )
    sample_rows = integration.sample_rows
    if payload.sample_rows is not None:
        source_fields = active_fields(db, user.tenant_id, integration.source_object_id)
        sample_rows = validate_sample_rows(payload.sample_rows, set(source_fields))
    refs.update(sample_field_references(sample_rows, integration.source_object_id))
    integration.graph = json_graph(payload.graph)
    integration.response_graph = json_graph(response_graph)
    integration.error_response_graph = json_graph(error_response_graph)
    integration.error_response_object_id = error_response_object_id
    if payload.interaction_type is not None:
        integration.interaction_type = payload.interaction_type
    if payload.name is not None:
        integration.name = payload.name
    integration.sample_rows = sample_rows
    integration.revision += 1
    integration.updated_at = datetime.now(UTC)
    replace_field_refs(db, integration, refs)
    commit_or_conflict(db)
    db.refresh(integration)
    return integration


@router.post(
    "/{integration_id}/dry-run",
    response_model=SimulationResponse,
)
def simulate_integration(
    integration_id: UUID,
    payload: SimulationRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SimulationResponse:
    require_csrf(request, auth_session)
    integration = active_integration(db, user.tenant_id, integration_id, lock=True)
    if (
        payload.expected_revision is not None
        and payload.expected_revision != integration.revision
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "revision_conflict",
                "message": "The integration changed; reload it before simulating",
                "current_revision": integration.revision,
            },
        )

    try:
        graph = payload.graph or GraphDocument.model_validate(integration.graph)
        response_graph = payload.response_graph or GraphDocument.model_validate(
            integration.response_graph
        )
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_saved_graph",
                "message": "A saved graph is invalid",
            },
        ) from error

    for graph_to_validate, is_response in ((graph, False), (response_graph, True)):
        try:
            graph_references(
                db,
                user.tenant_id,
                integration.source_object_id,
                integration.target_object_id,
                graph_to_validate,
                response=is_response,
            )
        except HTTPException as error:
            if error.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "invalid_response_graph" if is_response else "invalid_graph",
                        "message": (
                            "Response graph validation failed"
                            if is_response
                            else "Graph validation failed"
                        ),
                        "issues": error.detail if isinstance(error.detail, list) else [],
                    },
                ) from error
            raise
    source_fields = active_fields(db, user.tenant_id, integration.source_object_id)
    target_fields = active_fields(db, user.tenant_id, integration.target_object_id)

    requested_rows = payload.rows
    if requested_rows is None:
        try:
            requested_rows = [SampleRow.model_validate(row) for row in integration.sample_rows]
        except ValidationError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "invalid_saved_sample_rows",
                    "message": "The saved sample rows are invalid",
                },
            ) from error

    rows = validate_sample_rows(requested_rows, set(source_fields))
    response_rows = (
        validate_sample_rows(
            payload.response_payload,
            set(target_fields),
            label="response_payload",
            field_description="active response",
        )
        if payload.response_payload is not None
        else []
    )
    engine_source_fields = engine_field_specs(source_fields)
    engine_target_fields = engine_field_specs(target_fields)

    result = run_simulation_graph(
        graph,
        engine_source_fields,
        engine_target_fields,
        rows,
        include_trace_values=payload.options.include_trace_values,
    )
    response_result = None
    if integration.interaction_type != "ONE_WAY" and payload.response_payload is not None:
        response_result = run_simulation_graph(
            response_graph,
            engine_target_fields,
            engine_source_fields,
            response_rows,
            include_trace_values=payload.options.include_trace_values,
        )

    request_outcomes = result.to_dict()["rows"]
    response_outcomes = response_result.to_dict()["rows"] if response_result else []
    return SimulationResponse(
        integration_id=integration.id,
        version=result.version,
        revision=integration.revision,
        summary=result.summary,
        rows=request_outcomes,
        trace_truncated=result.trace_truncated,
        request_outcomes=request_outcomes,
        response_outcomes=response_outcomes,
        response_summary=(
            response_result.summary
            if response_result
            else {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
        ),
        response_trace_truncated=(
            response_result.trace_truncated if response_result else False
        ),
    )


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_integration(
    integration_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    integration = active_integration(db, user.tenant_id, integration_id, lock=True)
    integration.deleted_at = integration.updated_at = datetime.now(UTC)
    integration.revision += 1
    db.execute(
        delete(IntegrationFieldRef).where(
            IntegrationFieldRef.integration_id == integration.id,
            IntegrationFieldRef.tenant_id == user.tenant_id,
        )
    )
    db.execute(
        delete(IntegrationDependency).where(
            IntegrationDependency.tenant_id == user.tenant_id,
            (
                IntegrationDependency.upstream_integration_id == integration.id
            )
            | (IntegrationDependency.downstream_integration_id == integration.id),
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{integration_id}/dependencies",
    response_model=list[DependencyResponse],
)
def list_dependencies(
    integration_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[IntegrationDependency]:
    active_integration(db, user.tenant_id, integration_id)
    return list(
        db.scalars(
            select(IntegrationDependency)
            .where(
                IntegrationDependency.tenant_id == user.tenant_id,
                IntegrationDependency.upstream_integration_id == integration_id,
            )
            .order_by(IntegrationDependency.downstream_integration_id)
        )
    )


@router.post(
    "/{integration_id}/dependencies",
    response_model=DependencyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dependency(
    integration_id: UUID,
    payload: DependencyCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> IntegrationDependency:
    require_csrf(request, auth_session)
    db.scalar(select(Tenant.id).where(Tenant.id == user.tenant_id).with_for_update())
    integration_ids = sorted(
        {integration_id, payload.downstream_integration_id}, key=str
    )
    locked = {
        item_id: active_integration(db, user.tenant_id, item_id, lock=True)
        for item_id in integration_ids
    }
    upstream = locked[integration_id]
    downstream = locked[payload.downstream_integration_id]
    if upstream.id == downstream.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "An integration cannot depend on itself",
        )

    existing_edges = list(
        db.execute(
            select(
                IntegrationDependency.upstream_integration_id,
                IntegrationDependency.downstream_integration_id,
            ).where(IntegrationDependency.tenant_id == user.tenant_id)
        )
    )
    adjacency: dict[UUID, set[UUID]] = {}
    for source_id, target_id in existing_edges:
        adjacency.setdefault(source_id, set()).add(target_id)
    pending = [downstream.id]
    seen: set[UUID] = set()
    while pending:
        current = pending.pop()
        if current == upstream.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "dependency_cycle",
                    "message": "This dependency would create a cycle",
                },
            )
        if current not in seen:
            seen.add(current)
            pending.extend(adjacency.get(current, ()))

    dependency = IntegrationDependency(
        tenant_id=user.tenant_id,
        upstream_integration_id=upstream.id,
        downstream_integration_id=downstream.id,
    )
    db.add(dependency)
    commit_or_conflict(db)
    db.refresh(dependency)
    return dependency


@router.delete(
    "/{integration_id}/dependencies/{downstream_integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dependency(
    integration_id: UUID,
    downstream_integration_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    active_integration(db, user.tenant_id, integration_id)
    result = db.execute(
        delete(IntegrationDependency).where(
            IntegrationDependency.tenant_id == user.tenant_id,
            IntegrationDependency.upstream_integration_id == integration_id,
            IntegrationDependency.downstream_integration_id == downstream_integration_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration dependency not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
