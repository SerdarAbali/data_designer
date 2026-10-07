"""Design-time scenario CRUD and evaluation.

Scenarios reference contracts, systems, objects, and fields by ID. Evaluation reuses the
integration engine helpers and never persists anything or contacts external systems.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.integrations.graph import GraphDocument
from app.integrations.routes import engine_field_specs, run_simulation_graph
from app.models import (
    AuthSession,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Integration,
    Scenario,
)
from app.scenarios.schemas import (
    AssertionEvaluation,
    MissingReference,
    ScenarioCreate,
    ScenarioDocument,
    ScenarioEvaluateRequest,
    ScenarioEvaluateResponse,
    ScenarioResponse,
    ScenarioStep,
    ScenarioUpdate,
    StepEvaluation,
    StepMismatch,
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

PHASES_BY_INTERACTION = {
    "ONE_WAY": {"request"},
    "REQUEST_RESPONSE": {"request", "success-response", "error-response"},
    "ASYNC_CALLBACK": {"request", "async-response"},
}


SCOPE_MISMATCH = "A contract-scoped scenario can only use its own contract"
STATE_OWNER_MISMATCH = "State object does not belong to its participant"
# These are design errors rather than archived references, so they are never tolerated.
STRUCTURAL_MESSAGES = {SCOPE_MISMATCH, STATE_OWNER_MISMATCH}


@dataclass(frozen=True)
class PhaseEndpoints:
    graph: dict
    sender_object_id: UUID
    receiver_object_id: UUID


def phase_endpoints(integration: Integration, phase: str) -> PhaseEndpoints | None:
    """Resolve a contract phase to its graph and sender/receiver objects, or None if absent."""
    if phase not in PHASES_BY_INTERACTION.get(integration.interaction_type, set()):
        return None
    if phase == "request":
        return PhaseEndpoints(
            integration.graph, integration.source_object_id, integration.target_object_id
        )
    if phase == "error-response":
        if integration.error_response_object_id is None:
            return None
        return PhaseEndpoints(
            integration.error_response_graph,
            integration.error_response_object_id,
            integration.source_object_id,
        )
    return PhaseEndpoints(
        integration.response_graph,
        integration.target_object_id,
        integration.source_object_id,
    )


@dataclass
class ReferenceContext:
    integrations: dict[UUID, Integration]
    systems: set[UUID]
    objects: dict[UUID, UUID]
    fields: dict[UUID, dict[UUID, CatalogField]]


def load_reference_context(
    db: Session,
    tenant_id: UUID,
    document: ScenarioDocument,
    scope_integration_id: UUID | None,
) -> ReferenceContext:
    """Load active tenant records referenced by a scenario in a few batched, unlocked queries."""
    contract_ids = set(document.contract_ids)
    contract_ids.update(
        step.contract_id for step in document.steps() if step.contract_id is not None
    )
    if scope_integration_id is not None:
        contract_ids.add(scope_integration_id)
    integrations = {
        item.id: item
        for item in db.scalars(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.deleted_at.is_(None),
                Integration.id.in_(contract_ids),
            )
        )
    } if contract_ids else {}

    system_ids = {
        item.system_id for item in document.participants if item.system_id is not None
    }
    systems = set(
        db.scalars(
            select(CatalogSystem.id).where(
                CatalogSystem.tenant_id == tenant_id,
                CatalogSystem.deleted_at.is_(None),
                CatalogSystem.id.in_(system_ids),
            )
        )
    ) if system_ids else set()

    object_ids = {entry.object_id for entry in document.before_state + document.after_state}
    for integration in integrations.values():
        object_ids.update({integration.source_object_id, integration.target_object_id})
        if integration.error_response_object_id is not None:
            object_ids.add(integration.error_response_object_id)
    objects = {
        row.id: row.system_id
        for row in db.execute(
            select(CatalogObject.id, CatalogObject.system_id).where(
                CatalogObject.tenant_id == tenant_id,
                CatalogObject.deleted_at.is_(None),
                CatalogObject.id.in_(object_ids),
            )
        )
    } if object_ids else {}
    fields: dict[UUID, dict[UUID, CatalogField]] = {object_id: {} for object_id in objects}
    if objects:
        for field in db.scalars(
            select(CatalogField)
            .where(
                CatalogField.tenant_id == tenant_id,
                CatalogField.deleted_at.is_(None),
                CatalogField.object_id.in_(list(objects)),
            )
            .order_by(CatalogField.id)
        ):
            fields[field.object_id][field.id] = field
    return ReferenceContext(integrations, systems, objects, fields)


def document_reference_ids(document: dict | None) -> set[str]:
    """Every UUID-like reference in a stored document, used to tolerate later archives."""
    if not document:
        return set()
    try:
        parsed = ScenarioDocument.model_validate(document)
    except ValidationError:
        return set()
    ids = {str(item) for item in parsed.contract_ids}
    ids.update(str(item.system_id) for item in parsed.participants if item.system_id)
    for entry in parsed.before_state + parsed.after_state:
        ids.add(str(entry.object_id))
        ids.update(entry.values)
    for step in parsed.steps():
        if step.contract_id:
            ids.add(str(step.contract_id))
            ids.add(f"{step.contract_id}:{step.phase}")
        ids.update(step.sample_values)
        ids.update(step.expected_values)
    ids.update(str(item.field_id) for item in parsed.assertions if item.field_id)
    return ids


def collect_missing_references(
    document: ScenarioDocument,
    context: ReferenceContext,
    scope_integration_id: UUID | None,
) -> list[MissingReference]:
    missing: list[MissingReference] = []

    def add(kind, ref_id, message, step_id=None):
        missing.append(
            MissingReference(kind=kind, id=str(ref_id), message=message, step_id=step_id)
        )

    if scope_integration_id is not None and scope_integration_id not in context.integrations:
        add("contract", scope_integration_id, "The scoped contract is missing or archived")
    for contract_id in document.contract_ids:
        if contract_id not in context.integrations:
            add("contract", contract_id, "Participating contract is missing or archived")
    participant_systems = {
        item.id: item.system_id for item in document.participants if item.system_id
    }
    for system_id in participant_systems.values():
        if system_id not in context.systems:
            add("system", system_id, "Participant system is missing or archived")

    for entry in document.before_state + document.after_state:
        if entry.object_id not in context.objects:
            add("object", entry.object_id, "State object is missing or archived")
            continue
        if context.objects[entry.object_id] != participant_systems.get(entry.participant_id):
            add("object", entry.object_id, STATE_OWNER_MISMATCH)
        object_fields = context.fields.get(entry.object_id, {})
        for field_id in entry.values:
            if UUID(field_id) not in object_fields:
                add("field", field_id, "State field is missing or archived")

    receiver_fields_by_step: dict[str, dict[UUID, CatalogField]] = {}
    for step in document.steps():
        if step.kind != "contract":
            continue
        integration = context.integrations.get(step.contract_id)
        if integration is None:
            add("contract", step.contract_id, "Contract is missing or archived", step.id)
            continue
        if scope_integration_id is not None and step.contract_id != scope_integration_id:
            add("contract", step.contract_id, SCOPE_MISMATCH, step.id)
        endpoints = phase_endpoints(integration, step.phase)
        if endpoints is None:
            add(
                "phase",
                f"{step.contract_id}:{step.phase}",
                f"Phase {step.phase} is not configured for this contract",
                step.id,
            )
            continue
        sender = context.fields.get(endpoints.sender_object_id, {})
        receiver = context.fields.get(endpoints.receiver_object_id, {})
        receiver_fields_by_step[step.id] = receiver
        for field_id in step.sample_values:
            if UUID(field_id) not in sender:
                add("field", field_id, "Sample field is not a sender field of this phase", step.id)
        for field_id in step.expected_values:
            if UUID(field_id) not in receiver:
                add(
                    "field",
                    field_id,
                    "Expected field is not a receiver field of this phase",
                    step.id,
                )
    for assertion in document.assertions:
        if assertion.field_id is None or assertion.step_id not in receiver_fields_by_step:
            continue
        if assertion.field_id not in receiver_fields_by_step[assertion.step_id]:
            add(
                "field",
                assertion.field_id,
                "Assertion field is not a receiver field of its step",
                assertion.step_id,
            )
    return missing


def validate_for_save(
    db: Session,
    tenant_id: UUID,
    document: ScenarioDocument,
    scope_integration_id: UUID | None,
    previous_document: dict | None = None,
) -> None:
    """Reject new invalid references; tolerate references already stored and archived since."""
    context = load_reference_context(db, tenant_id, document, scope_integration_id)
    tolerated = document_reference_ids(previous_document)
    if previous_document is not None and scope_integration_id is not None:
        tolerated.add(str(scope_integration_id))
    issues = [
        item
        for item in collect_missing_references(document, context, scope_integration_id)
        if item.id not in tolerated or item.message in STRUCTURAL_MESSAGES
    ]
    if issues:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_scenario_reference",
                "message": issues[0].message,
                "issues": [item.model_dump(mode="json", by_alias=True) for item in issues],
            },
        )


def active_scenario(db: Session, tenant_id: UUID, scenario_id: UUID) -> Scenario:
    scenario = db.scalar(
        select(Scenario).where(
            Scenario.id == scenario_id,
            Scenario.tenant_id == tenant_id,
            Scenario.deleted_at.is_(None),
        )
    )
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")
    return scenario


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An active scenario with this name already exists",
        ) from error


def document_json(document: ScenarioDocument) -> dict:
    return document.model_dump(mode="json", by_alias=True)


def references_contract(scenario: Scenario, integration_id: UUID) -> bool:
    if scenario.scope_integration_id == integration_id:
        return True
    target = str(integration_id)
    document = scenario.document or {}
    if target in (document.get("contractIds") or []):
        return True

    def walk(items) -> bool:
        for item in items or []:
            if item.get("contractId") == target:
                return True
            for operand in item.get("operands") or []:
                if walk(operand.get("items")):
                    return True
        return False

    return walk(document.get("items"))


@router.get("", response_model=list[ScenarioResponse])
def list_scenarios(
    integration_id: UUID | None = Query(default=None),  # noqa: B008
    scope: str = Query(default="all", pattern="^(all|contract|landscape)$"),
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[Scenario]:
    query = select(Scenario).where(
        Scenario.tenant_id == user.tenant_id,
        Scenario.deleted_at.is_(None),
    )
    if scope == "contract":
        query = query.where(Scenario.scope_integration_id.is_not(None))
    elif scope == "landscape":
        query = query.where(Scenario.scope_integration_id.is_(None))
    scenarios = list(db.scalars(query.order_by(Scenario.name, Scenario.id).limit(500)))
    if integration_id is not None:
        scenarios = [item for item in scenarios if references_contract(item, integration_id)]
    return scenarios


@router.post("", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_scenario(
    payload: ScenarioCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Scenario:
    require_csrf(request, auth_session)
    validate_for_save(db, user.tenant_id, payload.document, payload.scope_integration_id)
    scenario = Scenario(
        tenant_id=user.tenant_id,
        scope_integration_id=payload.scope_integration_id,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        document=document_json(payload.document),
        revision=1,
    )
    db.add(scenario)
    commit_or_conflict(db)
    db.refresh(scenario)
    return scenario


@router.post("/evaluate", response_model=ScenarioEvaluateResponse)
def evaluate_scenario(
    payload: ScenarioEvaluateRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ScenarioEvaluateResponse:
    require_csrf(request, auth_session)
    document = payload.document
    context = load_reference_context(db, user.tenant_id, document, payload.scope_integration_id)
    missing = collect_missing_references(document, context, payload.scope_integration_id)
    missing_steps = {item.step_id for item in missing if item.step_id}

    results: list[StepEvaluation] = []
    by_step: dict[str, StepEvaluation] = {}
    for step in document.steps():
        result = evaluate_step(step, context, step.id in missing_steps)
        results.append(result)
        by_step[step.id] = result

    assertions = [evaluate_assertion(item, by_step) for item in document.assertions]
    summary = {
        "steps": len(results),
        "ok": sum(item.outcome == "ok" for item in results),
        "mismatch": sum(item.outcome == "mismatch" for item in results),
        "failed": sum(item.outcome in {"failed", "skipped"} for item in results),
        "missingReferences": len(missing),
        "assertionsPassed": sum(item.status == "passed" for item in assertions),
        "assertionsFailed": sum(item.status == "failed" for item in assertions),
    }
    return ScenarioEvaluateResponse(
        steps=results, assertions=assertions, missing_references=missing, summary=summary
    )


def evaluate_step(
    step: ScenarioStep, context: ReferenceContext, has_missing_reference: bool
) -> StepEvaluation:
    base = {
        "step_id": step.id,
        "contract_id": str(step.contract_id) if step.contract_id else None,
        "phase": step.phase,
    }
    if step.kind != "contract":
        return StepEvaluation(**base, outcome="not_evaluated")
    if has_missing_reference:
        return StepEvaluation(**base, outcome="missing_reference")
    integration = context.integrations[step.contract_id]
    endpoints = phase_endpoints(integration, step.phase)
    sender = context.fields[endpoints.sender_object_id]
    receiver = context.fields[endpoints.receiver_object_id]
    try:
        graph = GraphDocument.model_validate(endpoints.graph)
        simulation = run_simulation_graph(
            graph,
            engine_field_specs(sender),
            engine_field_specs(receiver),
            [{"row_id": step.id, "values": dict(step.sample_values)}],
            include_trace_values=False,
        )
    except ValidationError:
        return StepEvaluation(
            **base,
            outcome="failed",
            errors=[{"code": "invalid_saved_graph", "message": "The phase graph is invalid"}],
        )
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {"message": error.detail}
        return StepEvaluation(
            **base,
            outcome="failed",
            errors=[
                {
                    "code": str(detail.get("code", "evaluation_failed")),
                    "message": str(detail.get("message", "Evaluation failed")),
                }
            ],
        )
    row = simulation.rows[0]
    errors = [
        {"code": item.code, "message": item.message, "nodeId": item.node_id}
        for item in row.errors
    ]
    mismatches = [
        StepMismatch(
            field_id=field_id,
            expected=expected,
            actual=row.target_values.get(field_id),
            present=field_id in row.target_values,
        )
        for field_id, expected in step.expected_values.items()
        if field_id not in row.target_values or row.target_values[field_id] != expected
    ]
    if row.outcome != "ok":
        outcome = "skipped" if row.outcome == "skipped" else "failed"
    else:
        outcome = "mismatch" if mismatches else "ok"
    return StepEvaluation(
        **base,
        outcome=outcome,
        target_values=dict(row.target_values),
        errors=errors,
        mismatches=mismatches,
    )


def evaluate_assertion(assertion, by_step: dict[str, StepEvaluation]) -> AssertionEvaluation:
    if assertion.field_id is None:
        return AssertionEvaluation(
            assertion_id=assertion.id, status="manual", message="Checked by reviewer"
        )
    step = by_step.get(assertion.step_id)
    if step is None or step.outcome in {"missing_reference", "not_evaluated", "failed"}:
        return AssertionEvaluation(
            assertion_id=assertion.id,
            status="not_evaluated",
            message="The referenced step could not be evaluated",
        )
    field_id = str(assertion.field_id)
    if field_id in step.target_values and step.target_values[field_id] == assertion.expected:
        return AssertionEvaluation(assertion_id=assertion.id, status="passed", message="Matched")
    actual = step.target_values.get(field_id, "<not produced>")
    return AssertionEvaluation(
        assertion_id=assertion.id,
        status="failed",
        message=f"Expected {assertion.expected!r}, got {actual!r}",
    )


@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Scenario:
    return active_scenario(db, user.tenant_id, scenario_id)


@router.put("/{scenario_id}", response_model=ScenarioResponse)
def update_scenario(
    scenario_id: UUID,
    payload: ScenarioUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Scenario:
    require_csrf(request, auth_session)
    scenario = active_scenario(db, user.tenant_id, scenario_id)
    if scenario.revision != payload.expected_revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "revision_conflict",
                "message": "The scenario changed; reload it before saving",
                "current_revision": scenario.revision,
            },
        )
    validate_for_save(
        db,
        user.tenant_id,
        payload.document,
        scenario.scope_integration_id,
        previous_document=scenario.document,
    )
    scenario.name = payload.name
    scenario.category = payload.category
    scenario.description = payload.description
    scenario.document = document_json(payload.document)
    scenario.revision += 1
    scenario.updated_at = datetime.now(UTC)
    commit_or_conflict(db)
    db.refresh(scenario)
    return scenario


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_scenario(
    scenario_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    scenario = active_scenario(db, user.tenant_id, scenario_id)
    scenario.deleted_at = scenario.updated_at = datetime.now(UTC)
    scenario.revision += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
