"""Closed, deterministic resolution of unresolved proposal decisions.

Called only by the authenticated application UI — never by the model tool
registry. Every resolution is a closed discriminated union; there is no generic
JSON editing. Resolution mutates helper change-set rows only: it never touches an
architecture object, state membership, relationship, Catalog record, Contract,
scenario, or test.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.helper_actions import matching, service
from app.helper_actions.context import HelperContext, require_proposal_state
from app.models import HelperChangeOperation, HelperChangeSet

# -- closed request shape --------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=80)


class ChooseCatalogField(_Base):
    kind: Literal["choose_catalog_field"]
    catalog_field_id: str


class ChooseCanonicalObject(_Base):
    kind: Literal["choose_canonical_object"]
    object_id: str


class CreateNewArchitectureObject(_Base):
    kind: Literal["create_new_architecture_object"]
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)


class SetScalar(_Base):
    kind: Literal["set_scalar"]
    field: str = Field(min_length=1, max_length=60)
    value: str | int | float | bool


class ChooseContractIntent(_Base):
    kind: Literal["choose_contract_intent"]
    based_on_contract_id: str | None = None
    proposal_intent: Literal["alternative", "proposed_replacement", "independent"]


class ChooseEvidence(_Base):
    kind: Literal["choose_evidence"]
    interface_ids: list[str] = Field(default_factory=list, max_length=20)
    operation_ids: list[str] = Field(default_factory=list, max_length=20)


class RemoveOperation(_Base):
    kind: Literal["remove_operation"]


ResolutionUnion = (
    ChooseCatalogField
    | ChooseCanonicalObject
    | CreateNewArchitectureObject
    | SetScalar
    | ChooseContractIntent
    | ChooseEvidence
    | RemoveOperation
)

ResolutionItem = Annotated[ResolutionUnion, Field(discriminator="kind")]


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolutions: list[ResolutionItem] = Field(min_length=1, max_length=50)


# -- closed registry -------------------------------------------------------

ALLOWED_RESOLUTIONS: dict[str, set[str]] = {
    "include_object": {
        "create_new_architecture_object",
        "choose_canonical_object",
        "remove_operation",
    },
    "set_realization": {"choose_catalog_field", "remove_operation"},
    "create_mapping": {"choose_catalog_field", "remove_operation"},
    "create_contract": {"choose_contract_intent", "set_scalar", "remove_operation"},
    "configure_resilience": {"choose_contract_intent", "set_scalar", "remove_operation"},
    "create_object": {"set_scalar", "choose_canonical_object", "remove_operation"},
    "create_link": {"choose_evidence", "set_scalar", "remove_operation"},
    "record_interaction": {"choose_evidence", "set_scalar", "remove_operation"},
    "create_scenario": {"set_scalar", "remove_operation"},
    "define_conformance_expectation": {"set_scalar", "remove_operation"},
    "reuse_contract": {"remove_operation"},
    # Slice 7 refinement operations: resolve a registry-backed target or drop it.
    "set_lifecycle": {"choose_canonical_object", "remove_operation"},
    "set_operational_status": {"choose_canonical_object", "remove_operation"},
    "set_environment_scope": {"choose_canonical_object", "remove_operation"},
    "attach_evidence": {"choose_canonical_object", "remove_operation"},
    "associate_contract_with_solution": {"choose_canonical_object", "remove_operation"},
    "create_solution_relationship": {"choose_canonical_object", "remove_operation"},
}

SCALAR_FIELDS: dict[str, set[str]] = {
    "create_contract": {"name", "purpose", "implementation_status"},
    "configure_resilience": {"name"},
    "create_object": {"name", "description"},
    "create_link": {"cardinality", "source_optional", "target_optional"},
    "record_interaction": {"cardinality", "source_optional", "target_optional"},
    "create_scenario": {"name"},
    "define_conformance_expectation": {"coverage_min", "expected_success"},
}


def _load_operation(
    db: Session, change_set: HelperChangeSet, operation_id: str
) -> HelperChangeOperation:
    operation = db.query(HelperChangeOperation).filter(
        HelperChangeOperation.change_set_id == change_set.id,
        HelperChangeOperation.operation_id == operation_id,
    ).one_or_none()
    if operation is None or operation.resolution_state != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Operation not found"
        )
    return operation


def _apply(
    ctx: HelperContext,
    operation: HelperChangeOperation,
    resolution: Any,
) -> None:
    kind = resolution.kind
    allowed = ALLOWED_RESOLUTIONS.get(operation.domain_action, set())
    if kind not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "resolution_not_allowed", "kind": kind},
        )

    proposed = dict(operation.proposed_value or {})

    if kind == "choose_catalog_field":
        field = matching.find_catalog_field_by_id(ctx, _uuid(resolution.catalog_field_id))
        if field is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "unknown_catalog_field"},
            )
        proposed["catalog_field_id"] = str(field.id)
        proposed["unresolved"] = False
        proposed.pop("reason", None)
        proposed.pop("candidates", None)
    elif kind == "choose_canonical_object":
        registry = matching.find_registry(ctx, _uuid(resolution.object_id))
        if registry is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "unknown_object"},
            )
        proposed["existing_object_id"] = str(registry.id)
        proposed["unresolved"] = False
        proposed.pop("reason", None)
    elif kind == "create_new_architecture_object":
        proposed["create_new"] = True
        proposed["name"] = resolution.name
        if resolution.description is not None:
            proposed["description"] = resolution.description
        proposed["unresolved"] = False
        proposed.pop("reason", None)
    elif kind == "set_scalar":
        allowed_fields = SCALAR_FIELDS.get(operation.domain_action, set())
        if resolution.field not in allowed_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "field_not_allowed", "field": resolution.field},
            )
        proposed[resolution.field] = resolution.value
    elif kind == "choose_contract_intent":
        if resolution.based_on_contract_id:
            contract = matching.find_contract(ctx, _uuid(resolution.based_on_contract_id))
            if contract is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "unknown_contract"},
                )
            proposed["based_on_contract_id"] = str(contract.id)
        proposed["proposal_intent"] = resolution.proposal_intent
        proposed["unresolved"] = False
        proposed.pop("reason", None)
    elif kind == "choose_evidence":
        evidence: list[str] = []
        for interface_id in resolution.interface_ids:
            interface = matching.find_interface(ctx, _uuid(interface_id))
            if interface is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "unknown_interface"},
                )
            evidence.append(str(interface.object_id))
        for operation_id in resolution.operation_ids:
            op = matching.find_interface_operation(ctx, _uuid(operation_id))
            if op is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "unknown_operation"},
                )
            evidence.append(str(op.id))
        proposed["evidence_refs"] = evidence
        proposed["unresolved"] = False
        proposed.pop("reason", None)
    elif kind == "remove_operation":
        operation.resolution_state = "removed"

    operation.proposed_value = proposed


def _uuid(value: str | None):
    from uuid import UUID

    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "invalid_id"}
        ) from None


def resolve_change_set(
    ctx: HelperContext, change_set: HelperChangeSet, request: ResolutionRequest
) -> HelperChangeSet:
    require_proposal_state(ctx, change_set.state_id) if change_set.state_id else None
    if change_set.status in {"applied", "undone"} or change_set.applied_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "change_set_immutable", "message": "Applied change sets are read-only"},
        )

    for resolution in request.resolutions:
        operation = _load_operation(ctx.db, change_set, resolution.operation_id)
        _apply(ctx, operation, resolution)

    operations = service.load_operations(ctx.db, change_set.id)
    change_set.proposal_hash = service.compute_proposal_hash(change_set, operations)
    change_set.status = "draft"
    change_set.validated_at = None
    change_set.approved_by = None
    change_set.approved_at = None
    change_set.approved_hash = None
    change_set.validation_summary = {}
    change_set.unresolved_decisions = []
    change_set.unresolved_details = []
    ctx.db.flush()

    from app.assistant.decisions import derive_unresolved_details

    change_set.unresolved_details = derive_unresolved_details(change_set, operations)

    service.add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type="proposal_resolved",
        change_set_id=change_set.id,
        state_id=change_set.state_id,
        summary={
            "kinds": sorted({resolution.kind for resolution in request.resolutions}),
            "operation_ids": sorted(
                {resolution.operation_id for resolution in request.resolutions}
            ),
            "proposal_hash": change_set.proposal_hash,
        },
    )
    ctx.db.commit()
    ctx.db.refresh(change_set)
    return change_set
