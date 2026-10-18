"""Slice 7: controlled refinement proposals over already-delivered capabilities.

Six narrowly scoped helpers produce seven closed domain actions:

* ``propose_system_facts`` / ``propose_contract_facts`` -> ``set_lifecycle``,
  ``set_operational_status``, ``set_environment_scope``
* ``propose_contract_mediator`` -> ``set_contract_mediator``
* ``propose_evidence`` -> ``attach_evidence``
* ``propose_solution_contract_association`` -> ``associate_contract_with_solution``
* ``propose_solution_relationship`` -> ``create_solution_relationship``

Every helper is deterministic and read-only against the architecture: it emits
typed operations and never approves, applies, undoes, or touches Current. Target
matching is strictly ordered — explicit id, exact external identifier, exact
normalised name, then an existing closed unresolved decision — and never fuzzy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.architecture.schemas import (
    EvidenceClassification,
    EvidenceConfidence,
    EvidenceSourceType,
    EvidenceTargetKind,
    EvidenceVerificationStatus,
    SolutionIntegrationRole,
    SolutionRelationshipType,
)
from app.architecture.state_scope import contract_anchored_in_current
from app.architecture.vocabulary import (
    EnvironmentScope,
    LifecycleStage,
    OperationalStatus,
)
from app.helper_actions import matching
from app.helper_actions.context import HelperContext
from app.helper_actions.proposals import BuiltOperation, BuiltProposal
from app.models import (
    CatalogSystem,
    Integration,
    SolutionBoundary,
)

FACT_FIELD_LITERAL = Literal["lifecycle_stage", "operational_status", "environment_scope"]
FACT_FIELDS: tuple[str, ...] = ("lifecycle_stage", "operational_status", "environment_scope")

SYSTEM_FACT_ACTIONS = {
    "lifecycle_stage": "set_lifecycle",
    "operational_status": "set_operational_status",
    "environment_scope": "set_environment_scope",
}

EVIDENCE_TARGET_KINDS: tuple[str, ...] = (
    "architecture_object",
    "architecture_relationship",
    "integration",
    "integration_dependency",
    "solution_member",
)

# Registry-backed evidence targets can also be matched by exact name.
REGISTRY_EVIDENCE_TARGETS = {"architecture_object"}


def _reject(code: str, **context: Any) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, **context},
    )


# --- request schemas ----------------------------------------------------------


class _RefinementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: UUID
    summary: str = Field(min_length=1, max_length=2000)


class SystemFactsRequest(_RefinementRequest):
    """Set or clear lifecycle/operational/environment facts on a Catalog system.

    Only Candidate/Target state overrides are written; canonical Current values
    are never modified. ``None`` explicitly clears an override.
    """

    system_id: UUID | None = None
    system_external_id: str | None = Field(default=None, max_length=255)
    system_name: str | None = Field(default=None, max_length=160)
    existing_object_id: UUID | None = None
    lifecycle_stage: LifecycleStage | None = None
    operational_status: OperationalStatus | None = None
    environment_scope: EnvironmentScope | None = None

    @model_validator(mode="after")
    def at_least_one_fact(self) -> SystemFactsRequest:
        if not (self.model_fields_set & set(FACT_FIELDS)):
            raise ValueError("Provide at least one fact to set or clear")
        return self


class ContractFactsRequest(_RefinementRequest):
    """Set or clear lifecycle/operational/environment facts on a Contract."""

    contract_id: UUID | None = None
    contract_external_id: str | None = Field(default=None, max_length=255)
    contract_name: str | None = Field(default=None, max_length=160)
    lifecycle_stage: LifecycleStage | None = None
    operational_status: OperationalStatus | None = None
    environment_scope: EnvironmentScope | None = None

    @model_validator(mode="after")
    def at_least_one_fact(self) -> ContractFactsRequest:
        if not (self.model_fields_set & set(FACT_FIELDS)):
            raise ValueError("Provide at least one fact to set or clear")
        return self


class ContractMediatorRequest(_RefinementRequest):
    """Give a Contract an explicit mediator (canonical, single-mediator overlay)."""

    contract_id: UUID | None = None
    contract_external_id: str | None = Field(default=None, max_length=255)
    contract_name: str | None = Field(default=None, max_length=160)
    mediator_system_id: UUID | None = None
    mediator_system_external_id: str | None = Field(default=None, max_length=255)
    mediator_system_name: str | None = Field(default=None, max_length=160)
    mediator_responsibility: str | None = Field(default=None, max_length=300)


class EvidenceRequest(_RefinementRequest):
    """Attach state-scoped evidence to one supported target."""

    target_kind: EvidenceTargetKind
    target_id: UUID | None = None
    target_name: str | None = Field(default=None, max_length=160)
    existing_object_id: UUID | None = None
    evidence_classification: EvidenceClassification
    source_type: EvidenceSourceType
    source_title: str = Field(min_length=1, max_length=300)
    source_reference: str = Field(min_length=1, max_length=2000)
    source_locator: str | None = Field(default=None, max_length=2000)
    evidence_summary: str = Field(min_length=1, max_length=2000)
    confidence: EvidenceConfidence
    verification_status: EvidenceVerificationStatus = "unverified"


class SolutionContractAssociationRequest(_RefinementRequest):
    """Associate an existing Contract with a Solution Boundary, with a role."""

    solution_object_id: UUID | None = None
    solution_name: str | None = Field(default=None, max_length=160)
    existing_object_id: UUID | None = None
    contract_id: UUID | None = None
    contract_external_id: str | None = Field(default=None, max_length=255)
    contract_name: str | None = Field(default=None, max_length=160)
    role: SolutionIntegrationRole = "owned"
    description: str | None = Field(default=None, max_length=500)


class SolutionRelationshipRequest(_RefinementRequest):
    """Create a typed relationship between two Solution Boundaries."""

    source_object_id: UUID | None = None
    source_name: str | None = Field(default=None, max_length=160)
    existing_object_id: UUID | None = None
    target_object_id: UUID | None = None
    target_name: str | None = Field(default=None, max_length=160)
    relationship_type: SolutionRelationshipType
    description: str | None = Field(default=None, max_length=500)


# --- deterministic target resolution -----------------------------------------


@dataclass
class Resolved:
    """A deterministically resolved target, or a closed unresolved decision."""

    row: Any = None
    kind: str | None = None
    unresolved: bool = False
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.row is not None


def _resolve_contract(
    ctx: HelperContext,
    *,
    contract_id: UUID | None,
    external_id: str | None,
    name: str | None,
) -> Integration:
    if contract_id is not None:
        contract = matching.find_contract(ctx, contract_id)
        if contract is None:
            _reject("unknown_contract", contract_id=str(contract_id))
        return contract
    if external_id:
        contract = matching.find_contract_by_external_id(ctx, external_id)
        if contract is None:
            _reject("unknown_contract", external_id=external_id)
        return contract
    if name:
        target = matching.normalize_name(name)
        for candidate in matching.list_contracts(ctx):
            if matching.normalize_name(candidate.name) == target:
                return candidate
        _reject(
            "unknown_contract",
            message="No active Contract matches that exact name; use an id",
        )
    _reject("missing_contract_reference", message="Provide a Contract id, external id, or name")


def _resolve_system(
    ctx: HelperContext,
    *,
    system_id: UUID | None,
    external_id: str | None,
    name: str | None,
) -> Resolved:
    if system_id is not None:
        system = matching.find_catalog_system(ctx, system_id)
        if system is not None:
            return Resolved(row=system, kind="catalog_system")
        return Resolved(unresolved=True, reason="No active Catalog system has that id")
    if external_id:
        found = ctx.db.scalar(
            select(CatalogSystem).where(
                CatalogSystem.tenant_id == ctx.tenant_id,
                CatalogSystem.deleted_at.is_(None),
                CatalogSystem.external_identifier == external_id,
            )
        )
        if found is not None:
            return Resolved(row=found, kind="catalog_system")
        return Resolved(unresolved=True, reason="No Catalog system has that external id")
    if name:
        system = matching.find_catalog_system(ctx, None, name)
        if system is not None:
            return Resolved(row=system, kind="catalog_system")
        return Resolved(unresolved=True, reason="No Catalog system matches that exact name")
    return Resolved(unresolved=True, reason="No Catalog system reference was supplied")


def _resolve_boundary(
    ctx: HelperContext,
    *,
    object_id: UUID | None,
    existing_object_id: UUID | None,
    name: str | None,
) -> Resolved:
    for candidate in (object_id, existing_object_id):
        if candidate is None:
            continue
        registry = matching.find_registry(ctx, candidate, {"solution_boundary"})
        if registry is None:
            continue
        boundary = ctx.db.scalar(
            select(SolutionBoundary).where(
                SolutionBoundary.object_id == registry.id,
                SolutionBoundary.tenant_id == ctx.tenant_id,
            )
        )
        if boundary is not None:
            return Resolved(row=boundary, kind="solution_boundary")
    if name:
        target = matching.normalize_name(name)
        rows = ctx.db.scalars(
            select(SolutionBoundary)
            .where(SolutionBoundary.tenant_id == ctx.tenant_id)
            .order_by(SolutionBoundary.name, SolutionBoundary.object_id)
        )
        for row in rows:
            if matching.normalize_name(row.name) == target:
                return Resolved(row=row, kind="solution_boundary")
        return Resolved(
            unresolved=True, reason="No Solution Boundary matches that exact name"
        )
    return Resolved(unresolved=True, reason="No Solution Boundary reference was supplied")


def contract_used_by_current(ctx: HelperContext, contract_id: UUID) -> bool:
    """True when the Contract is anchored in the read-only Current state.

    A Contract is anchored when the Current canvas shows it: as a ``contract_ref``
    registry node, or as a state relationship carrying its id (the shape
    ``include-objects`` writes). The mediator is canonical, so changing it for
    such a Contract would silently rewrite what Current describes. The rule
    itself lives in ``state_scope`` so the baseline guard cannot disagree with it.
    """
    return contract_anchored_in_current(ctx.db, ctx.workspace, contract_id)


# --- builder ------------------------------------------------------------------


@dataclass
class _Builder:
    ctx: HelperContext
    helper_name: str

    def __post_init__(self) -> None:
        self.ops: list[BuiltOperation] = []
        self.reused: list[dict[str, Any]] = []
        self.assumptions: list[str] = []
        self.warnings: list[str] = []
        self.unresolved: list[str] = []
        self.metadata: dict[str, Any] = {}
        self._seq = 0

    def emit(
        self,
        domain_action: str,
        target_type: str,
        *,
        target_id: UUID | None = None,
        before_value: dict[str, Any] | None = None,
        proposed_value: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        explanation: str = "",
    ) -> BuiltOperation:
        self._seq += 1
        op = BuiltOperation(
            operation_id=f"op-{self._seq}",
            domain_action=domain_action,
            target_type=target_type,
            target_id=target_id,
            before_value=before_value,
            proposed_value=proposed_value or {},
            depends_on=depends_on or [],
            explanation=explanation,
        )
        self.ops.append(op)
        return op

    def unresolved_op(
        self,
        domain_action: str,
        target_type: str,
        *,
        reason: str,
        proposed_value: dict[str, Any],
        explanation: str,
    ) -> BuiltOperation:
        self.unresolved.append(reason)
        self.warnings.append(reason)
        return self.emit(
            domain_action,
            target_type,
            proposed_value={**proposed_value, "unresolved": True, "reason": reason},
            explanation=explanation,
        )

    def finish(self, state_id: UUID, summary: str) -> BuiltProposal:
        return BuiltProposal(
            helper_name=self.helper_name,
            state_id=state_id,
            summary=summary,
            operations=self.ops,
            reused_objects=self.reused,
            assumptions=self.assumptions,
            unresolved_decisions=self.unresolved,
            warnings=self.warnings,
            input_summary={"operation_count": len(self.ops)},
            metadata=self.metadata,
        )


def _fact_ops(
    builder: _Builder,
    req: Any,
    *,
    kind: str,
    target_id: UUID,
    canonical: dict[str, Any],
    fields: dict[str, Any],
) -> None:
    for field in FACT_FIELDS:
        if field not in fields:
            continue
        value = fields[field]
        builder.emit(
            SYSTEM_FACT_ACTIONS[field],
            kind,
            target_id=target_id,
            before_value={field: canonical.get(field)},
            proposed_value={
                "kind": kind,
                "field": field,
                "value": value,
                "changes": {field: value},
            },
            explanation=(
                f"Set {field} to {value!r} in this state" if value is not None
                else f"Clear the {field} override in this state"
            ),
        )


def build_system_facts(
    ctx: HelperContext, helper_name: str, req: SystemFactsRequest
) -> BuiltProposal:
    builder = _Builder(ctx, helper_name)
    resolved = _resolve_system(
        ctx,
        system_id=req.system_id,
        external_id=req.system_external_id,
        name=req.system_name,
    )
    fields = req.model_dump(exclude_unset=True)
    clean = {field: fields.get(field) for field in FACT_FIELDS if field in fields}
    if not resolved.ok:
        builder.unresolved_op(
            "set_lifecycle",
            "catalog_system",
            reason=resolved.reason or "The Catalog system could not be resolved",
            proposed_value={"kind": "catalog_system", "changes": clean, "facts": clean},
            explanation="Resolve the Catalog system before setting its facts",
        )
        return builder.finish(req.state_id, req.summary)
    system = resolved.row
    builder.reused.append(
        {"target_type": "catalog_system", "target_id": str(system.id), "name": system.name}
    )
    _fact_ops(
        builder,
        req,
        kind="catalog_system",
        target_id=system.id,
        canonical={
            "lifecycle_stage": system.lifecycle_stage,
            "operational_status": system.operational_status,
            "environment_scope": system.environment_scope,
        },
        fields=clean,
    )
    builder.metadata["system_id"] = str(system.id)
    return builder.finish(req.state_id, req.summary)


def build_contract_facts(
    ctx: HelperContext, helper_name: str, req: ContractFactsRequest
) -> BuiltProposal:
    builder = _Builder(ctx, helper_name)
    contract = _resolve_contract(
        ctx,
        contract_id=req.contract_id,
        external_id=req.contract_external_id,
        name=req.contract_name,
    )
    builder.reused.append(
        {"target_type": "contract", "target_id": str(contract.id), "name": contract.name}
    )
    fields = req.model_dump(exclude_unset=True)
    clean = {field: fields.get(field) for field in FACT_FIELDS if field in fields}
    _fact_ops(
        builder,
        req,
        kind="contract",
        target_id=contract.id,
        canonical={
            "lifecycle_stage": contract.lifecycle_stage,
            "operational_status": contract.operational_status,
            "environment_scope": contract.environment_scope,
        },
        fields=clean,
    )
    builder.metadata["contract_id"] = str(contract.id)
    return builder.finish(req.state_id, req.summary)


def build_contract_mediator(
    ctx: HelperContext, helper_name: str, req: ContractMediatorRequest
) -> BuiltProposal:
    builder = _Builder(ctx, helper_name)
    contract = _resolve_contract(
        ctx,
        contract_id=req.contract_id,
        external_id=req.contract_external_id,
        name=req.contract_name,
    )
    if contract_used_by_current(ctx, contract.id):
        _reject(
            "mediator_affects_current",
            message=(
                "This Contract is described by the read-only Current state; its canonical "
                "mediator cannot be changed from a proposal"
            ),
            contract_id=str(contract.id),
        )
    if req.mediator_system_id is None and not req.mediator_system_name:
        _reject("missing_mediator", message="Provide a mediator system id or exact name")
    resolved = _resolve_system(
        ctx,
        system_id=req.mediator_system_id,
        external_id=req.mediator_system_external_id,
        name=req.mediator_system_name,
    )
    if not resolved.ok:
        _reject(
            "unknown_mediator",
            message=resolved.reason or "The mediator system could not be resolved",
        )
    mediator = resolved.row
    if mediator.id == contract.source_system_id:
        _reject("mediator_is_source", message="The mediator cannot be the business source")
    if mediator.id == contract.target_system_id:
        _reject("mediator_is_target", message="The mediator cannot be the business target")
    builder.reused.append(
        {"target_type": "contract", "target_id": str(contract.id), "name": contract.name}
    )
    builder.reused.append(
        {"target_type": "catalog_system", "target_id": str(mediator.id), "name": mediator.name}
    )
    builder.emit(
        "set_contract_mediator",
        "contract",
        target_id=contract.id,
        before_value={
            "mediator_system_id": str(contract.mediator_system_id)
            if contract.mediator_system_id
            else None,
            "mediator_responsibility": contract.mediator_responsibility,
        },
        proposed_value={
            "kind": "contract",
            "mediator_system_id": str(mediator.id),
            "mediator_system_name": mediator.name,
            "mediator_responsibility": req.mediator_responsibility,
        },
        explanation=f"Set the mediator of '{contract.name}' to '{mediator.name}'",
    )
    builder.metadata["contract_id"] = str(contract.id)
    builder.metadata["mediator_system_id"] = str(mediator.id)
    return builder.finish(req.state_id, req.summary)


def build_evidence(ctx: HelperContext, helper_name: str, req: EvidenceRequest) -> BuiltProposal:
    builder = _Builder(ctx, helper_name)
    if req.target_kind not in EVIDENCE_TARGET_KINDS:
        _reject("unsupported_evidence_target", target_kind=req.target_kind)
    target_id = req.target_id
    unresolved_reason: str | None = None
    if target_id is None:
        if req.target_kind in REGISTRY_EVIDENCE_TARGETS:
            resolved = _resolve_boundary(
                ctx, object_id=None, existing_object_id=req.existing_object_id, name=req.target_name
            )
            if resolved.ok:
                target_id = resolved.row.object_id
            else:
                unresolved_reason = resolved.reason
        else:
            _reject(
                "missing_evidence_target",
                message="Provide an explicit target id for this evidence target kind",
            )
    if target_id is None:
        builder.unresolved_op(
            "attach_evidence",
            "evidence",
            reason=unresolved_reason or "The evidence target could not be resolved",
            proposed_value={"target_kind": req.target_kind},
            explanation="Resolve the evidence target before attaching evidence",
        )
        return builder.finish(req.state_id, req.summary)

    payload = {
        "target_kind": req.target_kind,
        "target_id": str(target_id),
        "evidence_classification": req.evidence_classification,
        "source_type": req.source_type,
        "source_title": req.source_title,
        "source_reference": req.source_reference,
        "source_locator": req.source_locator,
        "summary": req.evidence_summary,
        "confidence": req.confidence,
        "verification_status": req.verification_status,
    }
    builder.emit(
        "attach_evidence",
        "evidence",
        target_id=target_id,
        proposed_value=payload,
        explanation=f"Attach {req.evidence_classification.replace('_', ' ')} evidence",
    )
    builder.metadata["evidence_target_kind"] = req.target_kind
    return builder.finish(req.state_id, req.summary)


def build_solution_contract_association(
    ctx: HelperContext, helper_name: str, req: SolutionContractAssociationRequest
) -> BuiltProposal:
    builder = _Builder(ctx, helper_name)
    resolved = _resolve_boundary(
        ctx,
        object_id=req.solution_object_id,
        existing_object_id=req.existing_object_id,
        name=req.solution_name,
    )
    if not resolved.ok:
        builder.unresolved_op(
            "associate_contract_with_solution",
            "solution_integration",
            reason=resolved.reason or "The Solution Boundary could not be resolved",
            proposed_value={"role": req.role},
            explanation="Resolve the Solution Boundary before associating a Contract",
        )
        return builder.finish(req.state_id, req.summary)
    boundary = resolved.row
    contract = _resolve_contract(
        ctx,
        contract_id=req.contract_id,
        external_id=req.contract_external_id,
        name=req.contract_name,
    )
    builder.reused.append(
        {
            "target_type": "solution_boundary",
            "target_id": str(boundary.object_id),
            "name": boundary.name,
        }
    )
    builder.reused.append(
        {"target_type": "contract", "target_id": str(contract.id), "name": contract.name}
    )
    builder.emit(
        "associate_contract_with_solution",
        "solution_integration",
        target_id=boundary.object_id,
        proposed_value={
            "kind": "solution_integration",
            "solution_object_id": str(boundary.object_id),
            "integration_id": str(contract.id),
            "contract_name": contract.name,
            "role": req.role,
            "description": req.description,
        },
        explanation=f"Associate Contract '{contract.name}' with '{boundary.name}' as {req.role}",
    )
    builder.metadata["solution_object_id"] = str(boundary.object_id)
    builder.metadata["integration_id"] = str(contract.id)
    return builder.finish(req.state_id, req.summary)


def build_solution_relationship(
    ctx: HelperContext, helper_name: str, req: SolutionRelationshipRequest
) -> BuiltProposal:
    builder = _Builder(ctx, helper_name)
    source = _resolve_boundary(
        ctx,
        object_id=req.source_object_id,
        existing_object_id=req.existing_object_id,
        name=req.source_name,
    )
    target = _resolve_boundary(
        ctx, object_id=req.target_object_id, existing_object_id=None, name=req.target_name
    )
    if not source.ok or not target.ok:
        builder.unresolved_op(
            "create_solution_relationship",
            "solution_relationship",
            reason=(
                source.reason
                if not source.ok
                else target.reason or "The target Solution Boundary could not be resolved"
            )
            or "The Solution relationship endpoints could not be resolved",
            proposed_value={
                "source_object_id": str(source.row.object_id) if source.ok else None,
                "target_object_id": str(target.row.object_id) if target.ok else None,
                "relationship_type": req.relationship_type,
                "description": req.description,
            },
            explanation="Resolve both Solution Boundaries before creating the relationship",
        )
        return builder.finish(req.state_id, req.summary)
    source_boundary, target_boundary = source.row, target.row
    if source_boundary.object_id == target_boundary.object_id:
        _reject(
            "self_relationship", message="A Solution cannot relate to itself"
        )
    for boundary in (source_boundary, target_boundary):
        builder.reused.append(
            {
                "target_type": "solution_boundary",
                "target_id": str(boundary.object_id),
                "name": boundary.name,
            }
        )
    builder.emit(
        "create_solution_relationship",
        "solution_relationship",
        target_id=source_boundary.object_id,
        proposed_value={
            "kind": "solution_relationship",
            "source_object_id": str(source_boundary.object_id),
            "target_object_id": str(target_boundary.object_id),
            "source_name": source_boundary.name,
            "target_name": target_boundary.name,
            "relationship_type": req.relationship_type,
            "description": req.description,
        },
        explanation=(
            f"Relate '{source_boundary.name}' to '{target_boundary.name}' "
            f"as {req.relationship_type}"
        ),
    )
    builder.metadata["source_object_id"] = str(source_boundary.object_id)
    builder.metadata["target_object_id"] = str(target_boundary.object_id)
    return builder.finish(req.state_id, req.summary)


# --- profiles ------------------------------------------------------------------

REFINEMENT_HELPERS: tuple[tuple[str, str | None], ...] = (
    ("propose_system_facts", None),
    ("propose_contract_facts", "integration"),
    ("propose_contract_mediator", "integration"),
    ("propose_evidence", None),
    ("propose_solution_contract_association", "solution"),
    ("propose_solution_relationship", "solution"),
)

REQUEST_MODELS: dict[str, type] = {
    "propose_system_facts": SystemFactsRequest,
    "propose_contract_facts": ContractFactsRequest,
    "propose_contract_mediator": ContractMediatorRequest,
    "propose_evidence": EvidenceRequest,
    "propose_solution_contract_association": SolutionContractAssociationRequest,
    "propose_solution_relationship": SolutionRelationshipRequest,
}

DISCIPLINES: dict[str, str | None] = dict(REFINEMENT_HELPERS)

BUILDERS = {
    "propose_system_facts": build_system_facts,
    "propose_contract_facts": build_contract_facts,
    "propose_contract_mediator": build_contract_mediator,
    "propose_evidence": build_evidence,
    "propose_solution_contract_association": build_solution_contract_association,
    "propose_solution_relationship": build_solution_relationship,
}

REFINEMENT_ACTIONS = frozenset(
    {
        "set_lifecycle",
        "set_operational_status",
        "set_environment_scope",
        "set_contract_mediator",
        "attach_evidence",
        "associate_contract_with_solution",
        "create_solution_relationship",
    }
)


def build(ctx: HelperContext, helper_name: str, req: Any) -> BuiltProposal:
    return BUILDERS[helper_name](ctx, helper_name, req)
