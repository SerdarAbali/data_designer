"""Change-set lifecycle: proposal creation, validation, approval, and audit.

Proposal helpers persist helper lifecycle data only. This module never creates
or modifies architecture objects, state memberships, relationships, Catalog
records, Contracts, mappings, scenarios, or tests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.state_scope import present_in_current
from app.architecture.vocabulary import (
    ENVIRONMENT_SCOPES,
    LIFECYCLE_STAGES,
    OPERATIONAL_STATUSES,
)
from app.engine.operations import NODE_CONFIG_KEYS, OperationFailure, validate_node_config
from app.helper_actions import (
    end_to_end,
    integration_proposals,
    matching,
    proposals,
    refinement_proposals,
)
from app.helper_actions.context import (
    HelperContext,
    require_discipline,
    require_proposal_state,
    resolve_state,
)
from app.helper_actions.schemas import (
    ChangeSetResponse,
    DomainProposalRequest,
    EndToEndRequest,
    FixtureProposalRequest,
    OperationResponse,
)
from app.models import (
    ArchitectureInterface,
    ArchitectureObject,
    ArchitectureRelationship,
    CatalogField,
    CatalogSystem,
    HelperAuditEvent,
    HelperChangeOperation,
    HelperChangeSet,
    Integration,
    IntegrationDependency,
    Scenario,
    SolutionMember,
)
from app.scenarios.schemas import ScenarioDocument

FIXTURE_ACTIONS = {"reuse_existing_object", "reference_object"}
DOMAIN_ACTIONS = {
    "create_object",
    "include_object",
    "override_object",
    "create_link",
    "set_realization",
    "record_interaction",
}
SLICE3_ACTIONS = {
    "reuse_contract",
    "create_contract",
    "create_mapping",
    "create_transformation",
    "configure_resilience",
    "create_scenario",
    "define_conformance_expectation",
}
SLICE7_ACTIONS = set(refinement_proposals.REFINEMENT_ACTIONS)
PROPOSAL_HELPERS = {
    "propose_fixture",
    *proposals.PROFILES,
    *integration_proposals.PROFILES,
    *refinement_proposals.REQUEST_MODELS,
    end_to_end.COMPOSITE_HELPER,
}
PROPOSAL_REQUEST_MODELS: dict[str, type] = {
    "propose_fixture": FixtureProposalRequest,
    **proposals.REQUEST_MODELS,
    **integration_proposals.REQUEST_MODELS,
    **refinement_proposals.REQUEST_MODELS,
    end_to_end.COMPOSITE_HELPER: EndToEndRequest,
}


def _now() -> datetime:
    return datetime.now(UTC)


def load_operations(db: Session, change_set_id: UUID) -> list[HelperChangeOperation]:
    return list(
        db.scalars(
            select(HelperChangeOperation)
            .where(HelperChangeOperation.change_set_id == change_set_id)
            .order_by(HelperChangeOperation.ordinal, HelperChangeOperation.operation_id)
        )
    )


def _operation_fingerprint(op: HelperChangeOperation) -> dict[str, Any]:
    fingerprint = {
        "operation_id": op.operation_id,
        "domain_action": op.domain_action,
        "target_type": op.target_type,
        "target_id": str(op.target_id) if op.target_id else None,
        "temporary_id": op.temporary_id,
        "before_value": op.before_value,
        "proposed_value": op.proposed_value or {},
        "depends_on": sorted(op.depends_on or []),
        "explanation": op.explanation or "",
    }
    # Only a non-active resolution state changes the hash, so every hash stored
    # before this slice stays byte-identical.
    if getattr(op, "resolution_state", "active") != "active":
        fingerprint["resolution_state"] = op.resolution_state
    return fingerprint


def compute_proposal_hash(
    change_set: HelperChangeSet, operations: list[HelperChangeOperation]
) -> str:
    payload = {
        "helper_name": change_set.helper_name,
        "state_id": str(change_set.state_id) if change_set.state_id else None,
        "summary": change_set.summary,
        "assumptions": change_set.assumptions or [],
        "unresolved_decisions": change_set.unresolved_decisions or [],
        "warnings": change_set.warnings or [],
        "operations": [
            _operation_fingerprint(op)
            for op in sorted(operations, key=lambda row: row.operation_id)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def add_audit(
    db: Session,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    user_id: UUID | None,
    event_type: str,
    change_set_id: UUID | None = None,
    state_id: UUID | None = None,
    summary: dict[str, Any] | None = None,
    affected_object_ids: list[str] | None = None,
    affected_contract_ids: list[str] | None = None,
) -> None:
    db.add(
        HelperAuditEvent(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            change_set_id=change_set_id,
            state_id=state_id,
            user_id=user_id,
            event_type=event_type,
            summary=summary or {},
            affected_object_ids=affected_object_ids or [],
            affected_contract_ids=affected_contract_ids or [],
            created_at=_now(),
        )
    )


def create_fixture_proposal(ctx: HelperContext, payload: FixtureProposalRequest) -> HelperChangeSet:
    state = require_proposal_state(ctx, payload.state_id)

    disabled = sorted({d for d in payload.requested_disciplines if d not in ctx.disciplines})
    if disabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "disabled_discipline", "disciplines": disabled},
        )

    operation_ids = [op.operation_id for op in payload.operations]
    duplicates = sorted({oid for oid in operation_ids if operation_ids.count(oid) > 1})
    if duplicates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "duplicate_operation_id", "operation_ids": duplicates},
        )

    change_set = HelperChangeSet(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        state_id=state.id,
        state_type=state.state_type,
        helper_name="propose_fixture",
        status="draft",
        summary=payload.summary,
        input_summary={
            "operation_count": len(payload.operations),
            "summary_length": len(payload.summary),
            "assumptions_count": len(payload.assumptions),
            "unresolved_decisions_count": len(payload.unresolved_decisions),
            "warnings_count": len(payload.warnings),
            "requested_disciplines": list(payload.requested_disciplines),
        },
        assumptions=list(payload.assumptions),
        unresolved_decisions=list(payload.unresolved_decisions),
        warnings=list(payload.warnings),
        proposed_by=ctx.user.id,
        created_at=_now(),
        updated_at=_now(),
    )
    ctx.db.add(change_set)
    ctx.db.flush()

    for ordinal, op in enumerate(payload.operations):
        ctx.db.add(
            HelperChangeOperation(
                change_set_id=change_set.id,
                tenant_id=ctx.tenant_id,
                workspace_id=ctx.workspace_id,
                operation_id=op.operation_id,
                ordinal=ordinal,
                domain_action=op.domain_action,
                target_type=op.target_type,
                target_id=op.target_id,
                temporary_id=op.temporary_id,
                before_value=op.before_value,
                proposed_value=op.proposed_value,
                depends_on=list(op.depends_on),
                validation_status="pending",
                validation_issues=[],
                explanation=op.explanation,
                created_at=_now(),
            )
        )
    ctx.db.flush()

    operations = load_operations(ctx.db, change_set.id)
    reused = {
        (str(op.target_type), str(op.target_id)): {
            "target_type": op.target_type,
            "target_id": str(op.target_id),
        }
        for op in operations
        if op.target_id is not None
    }
    proposed = [
        {"temporary_id": op.temporary_id, "target_type": op.target_type}
        for op in operations
        if op.temporary_id is not None
    ]
    change_set.reused_objects = [reused[key] for key in sorted(reused)]
    change_set.proposed_objects = sorted(proposed, key=lambda item: item["temporary_id"])
    change_set.proposal_hash = compute_proposal_hash(change_set, operations)

    add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type="change_set_created",
        change_set_id=change_set.id,
        state_id=state.id,
        summary={
            "helper": "propose_fixture",
            "status": "draft",
            "operation_count": len(operations),
            "proposal_hash": change_set.proposal_hash,
        },
        affected_object_ids=sorted(
            {str(op.target_id) for op in operations if op.target_id is not None}
        ),
    )
    ctx.db.commit()
    ctx.db.refresh(change_set)
    return change_set


def create_domain_proposal(
    ctx: HelperContext, helper_name: str, payload: DomainProposalRequest
) -> HelperChangeSet:
    """Persist a domain proposal: helper lifecycle rows only.

    Building and persisting a proposal never creates or modifies an architecture
    object, state membership, relationship, Catalog record, Contract, mapping,
    scenario, or test. Only ``apply_change_set`` (a later slice) may do that.
    """
    if helper_name == end_to_end.COMPOSITE_HELPER:
        state = require_proposal_state(ctx, payload.state_id)
        built = end_to_end.build_end_to_end_proposal(ctx, payload)
        discipline = "composite"
    elif helper_name in refinement_proposals.REQUEST_MODELS:
        discipline = refinement_proposals.DISCIPLINES[helper_name]
        require_discipline(ctx, discipline)
        state = require_proposal_state(ctx, payload.state_id)
        built = refinement_proposals.build(ctx, helper_name, payload)
    elif helper_name in proposals.PROFILES:
        profile = proposals.PROFILES[helper_name]
        require_discipline(ctx, profile.discipline)
        state = require_proposal_state(ctx, payload.state_id)
        built = proposals.build_domain_proposal(ctx, helper_name, payload)
        discipline = profile.discipline
    else:
        profile = integration_proposals.PROFILES[helper_name]
        require_discipline(ctx, profile.discipline)
        state = require_proposal_state(ctx, payload.state_id)
        built = integration_proposals.build_integration_proposal(ctx, helper_name, payload)
        discipline = profile.discipline

    change_set = HelperChangeSet(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        state_id=state.id,
        state_type=state.state_type,
        helper_name=helper_name,
        status="draft",
        summary=payload.summary,
        input_summary=built.input_summary,
        assumptions=list(built.assumptions),
        unresolved_decisions=list(built.unresolved_decisions),
        warnings=list(built.warnings),
        proposed_by=ctx.user.id,
        created_at=_now(),
        updated_at=_now(),
    )
    ctx.db.add(change_set)
    ctx.db.flush()

    for ordinal, op in enumerate(built.operations):
        ctx.db.add(
            HelperChangeOperation(
                change_set_id=change_set.id,
                tenant_id=ctx.tenant_id,
                workspace_id=ctx.workspace_id,
                operation_id=op.operation_id,
                ordinal=ordinal,
                domain_action=op.domain_action,
                target_type=op.target_type,
                target_id=op.target_id,
                temporary_id=op.temporary_id,
                before_value=op.before_value,
                proposed_value=op.proposed_value,
                depends_on=list(op.depends_on),
                validation_status="pending",
                validation_issues=[],
                explanation=op.explanation,
                created_at=_now(),
            )
        )
    ctx.db.flush()

    change_set.reused_objects = built.reused_objects
    change_set.proposed_objects = built.proposed_objects
    operations = load_operations(ctx.db, change_set.id)
    change_set.proposal_hash = compute_proposal_hash(change_set, operations)

    add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type="proposal_invoked",
        change_set_id=change_set.id,
        state_id=state.id,
        summary={
            "helper": helper_name,
            "discipline": discipline,
            "status": "draft",
            "operation_count": len(operations),
            "reused_count": len(built.reused_objects),
            "proposed_count": len(built.proposed_objects),
            "unresolved_count": len(built.unresolved_decisions),
            "proposal_hash": change_set.proposal_hash,
        },
        affected_object_ids=sorted(item["target_id"] for item in built.reused_objects),
    )
    if built.reused_objects:
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="objects_reused",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={"count": len(built.reused_objects)},
            affected_object_ids=sorted(item["target_id"] for item in built.reused_objects),
        )
    if built.proposed_objects:
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="objects_proposed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={
                "count": len(built.proposed_objects),
                "temporary_ids": sorted(item["temporary_id"] for item in built.proposed_objects)[
                    :50
                ],
            },
        )
    if built.unresolved_decisions:
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="unresolved_decision",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={
                "count": len(built.unresolved_decisions),
                "decisions": list(built.unresolved_decisions)[:10],
            },
        )
    _emit_slice3_audit(ctx, change_set, state, built)
    if helper_name == end_to_end.COMPOSITE_HELPER:
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="composite_proposal_created",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={
                "disciplines_built": list(built.metadata.get("disciplines_built", [])),
                "operation_count": len(operations),
            },
        )
    ctx.db.commit()
    ctx.db.refresh(change_set)
    return change_set


def _emit_slice3_audit(
    ctx: HelperContext,
    change_set: HelperChangeSet,
    state: Any,
    built: proposals.BuiltProposal,
) -> None:
    """Emit bounded audit events for Slice 3 integration proposals (no payload dumps)."""
    metadata = built.metadata or {}
    if not metadata:
        return
    if metadata.get("contract_reused"):
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="contract_reused",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={
                "matched_by": metadata.get("contract_matched_by"),
                "contract_ids": [item["target_id"] for item in built.reused_objects],
            },
            affected_contract_ids=[item["target_id"] for item in built.reused_objects],
        )
    if metadata.get("contract_proposed"):
        lineage = metadata.get("contract_lineage") or {}
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="contract_proposed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={
                "temporary_ids": [item["temporary_id"] for item in built.proposed_objects][:50],
                "based_on_contract_id": lineage.get("based_on_contract_id"),
                "proposal_intent": lineage.get("proposal_intent"),
            },
            affected_contract_ids=(
                [lineage["based_on_contract_id"]] if lineage.get("based_on_contract_id") else []
            ),
        )
        if lineage:
            add_audit(
                ctx.db,
                tenant_id=ctx.tenant_id,
                workspace_id=ctx.workspace_id,
                user_id=ctx.user.id,
                event_type="contract_lineage",
                change_set_id=change_set.id,
                state_id=state.id,
                summary=dict(lineage),
            )
    if metadata.get("mappings"):
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="mapping_proposed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={"count": metadata.get("mappings")},
        )
    if metadata.get("ambiguous_mappings"):
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="ambiguous_mapping",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={"count": metadata.get("ambiguous_mappings")},
        )
    if metadata.get("transformations"):
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="transformation_proposed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={"count": metadata.get("transformations")},
        )
    if metadata.get("scenarios"):
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="scenario_proposed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={"count": metadata.get("scenarios")},
        )
    if metadata.get("conformance"):
        add_audit(
            ctx.db,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
            event_type="conformance_expectation_proposed",
            change_set_id=change_set.id,
            state_id=state.id,
            summary={"count": metadata.get("conformance")},
        )


def run_proposal(ctx: HelperContext, helper_name: str, payload: Any) -> HelperChangeSet:
    if helper_name == "propose_fixture":
        return create_fixture_proposal(ctx, payload)
    return create_domain_proposal(ctx, helper_name, payload)


def get_change_set(ctx: HelperContext, change_set_id: UUID) -> HelperChangeSet:
    change_set = ctx.db.scalar(
        select(HelperChangeSet).where(
            HelperChangeSet.id == change_set_id,
            HelperChangeSet.workspace_id == ctx.workspace_id,
            HelperChangeSet.tenant_id == ctx.tenant_id,
        )
    )
    if change_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change set not found")
    return change_set


def sync_staleness(ctx: HelperContext, change_set: HelperChangeSet) -> bool:
    """Detect proposal mutation and invalidate validation + approval."""
    operations = load_operations(ctx.db, change_set.id)
    current = compute_proposal_hash(change_set, operations)
    if change_set.proposal_hash and change_set.proposal_hash != current:
        change_set.status = "stale"
        change_set.approved_by = None
        change_set.approved_at = None
        change_set.approved_hash = None
        change_set.validated_at = None
        change_set.updated_at = _now()
        ctx.db.commit()
        return True
    return False


def _target_exists(ctx: HelperContext, op: HelperChangeOperation) -> bool:
    target_id = op.target_id
    if target_id is None:
        return True
    if op.target_type == "architecture_object":
        return (
            ctx.db.scalar(
                select(ArchitectureObject.id).where(
                    ArchitectureObject.id == target_id,
                    ArchitectureObject.tenant_id == ctx.tenant_id,
                )
            )
            is not None
        )
    if op.target_type == "catalog_system":
        return (
            ctx.db.scalar(
                select(CatalogSystem.id).where(
                    CatalogSystem.id == target_id,
                    CatalogSystem.tenant_id == ctx.tenant_id,
                    CatalogSystem.deleted_at.is_(None),
                )
            )
            is not None
        )
    if op.target_type == "catalog_field":
        return (
            ctx.db.scalar(
                select(CatalogField.id).where(
                    CatalogField.id == target_id,
                    CatalogField.tenant_id == ctx.tenant_id,
                    CatalogField.deleted_at.is_(None),
                )
            )
            is not None
        )
    if op.target_type == "contract":
        return (
            ctx.db.scalar(
                select(Integration.id).where(
                    Integration.id == target_id,
                    Integration.tenant_id == ctx.tenant_id,
                    Integration.deleted_at.is_(None),
                )
            )
            is not None
        )
    return False


def _find_cycle(operations: list[HelperChangeOperation]) -> set[str]:
    deps = {op.operation_id: [d for d in (op.depends_on or [])] for op in operations}
    known = set(deps)
    state: dict[str, int] = {}
    cyclic: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dep in deps.get(node, []):
            if dep not in known:
                continue
            if state.get(dep, 0) == 1:
                cyclic.update(stack[stack.index(dep) :])
            elif state.get(dep, 0) == 0:
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in known:
        if state.get(node, 0) == 0:
            visit(node)
    return cyclic


# --- Slice 2 domain validation ----------------------------------------------

PARENT_EXPECTED_KIND = {
    "information_attribute": {"information_object"},
    "interface": {"component"},
    "interface_operation": {"interface"},
    "component": {"solution_boundary"},
    "data_repository": {"solution_boundary"},
    "deployment_node": {"solution_boundary"},
    "trust_boundary": {"solution_boundary"},
}


def _dependency_closure(
    op: HelperChangeOperation, by_id: dict[str, HelperChangeOperation]
) -> set[str]:
    seen: set[str] = set()
    stack = list(op.depends_on or [])
    while stack:
        dep = stack.pop()
        if dep in seen:
            continue
        seen.add(dep)
        parent = by_id.get(dep)
        if parent is not None:
            stack.extend(parent.depends_on or [])
    return seen


def _resolve_ref(
    ctx: HelperContext,
    ref: Any,
    by_temp: dict[str, HelperChangeOperation],
    closure: set[str],
    expected_kinds: set[str] | None = None,
) -> tuple[str, Any, Any]:
    """Resolve a temporary or canonical reference to ``(status, kind, payload)``."""
    if not isinstance(ref, str) or not ref:
        return "error", "missing_reference", None
    if ref.startswith("tmp:"):
        creator = by_temp.get(ref)
        if creator is None:
            return "error", "unknown_temporary_id", None
        if creator.operation_id not in closure:
            return "error", "missing_dependency", None
        kind = proposals.registry_kind(creator.target_type)
        if expected_kinds is not None and kind not in expected_kinds:
            return "error", "reference_kind_mismatch", None
        return "temp", kind, creator
    try:
        object_id = UUID(ref)
    except (ValueError, AttributeError):
        return "error", "invalid_reference", None
    registry = matching.find_registry(ctx, object_id)
    if registry is None:
        return "error", "unknown_target", None
    if expected_kinds is not None and registry.kind not in expected_kinds:
        return "error", "reference_kind_mismatch", None
    return "canonical", registry.kind, registry


def _ref_direction(ctx: HelperContext, status_kind: str, payload: Any) -> str | None:
    if status_kind == "temp":
        return (payload.proposed_value or {}).get("direction", "provided")
    if getattr(payload, "kind", None) != "interface":
        return None
    row = ctx.db.scalar(
        select(ArchitectureInterface).where(
            ArchitectureInterface.object_id == payload.id,
            ArchitectureInterface.tenant_id == ctx.tenant_id,
        )
    )
    return row.direction if row is not None else None


def _validate_link(
    ctx: HelperContext,
    pv: dict[str, Any],
    by_temp: dict[str, HelperChangeOperation],
    closure: set[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    relationship = pv.get("relationship_type")
    if relationship not in proposals.ALL_RELS:
        return [
            {
                "code": "unknown_relationship",
                "message": f"Unknown relationship type {relationship!r}",
            }
        ]
    s_status, s_kind, s_payload = _resolve_ref(ctx, pv.get("source_ref"), by_temp, closure)
    t_status, t_kind, t_payload = _resolve_ref(ctx, pv.get("target_ref"), by_temp, closure)
    if s_status == "error":
        issues.append({"code": s_kind, "message": "Source reference did not resolve"})
    if t_status == "error":
        issues.append({"code": t_kind, "message": "Target reference did not resolve"})
    if issues:
        return issues

    if relationship in proposals.ENTERPRISE_LINK_RULES:
        allowed_source, allowed_target = proposals.ENTERPRISE_LINK_RULES[relationship]
        if s_kind not in allowed_source or t_kind not in allowed_target:
            issues.append(
                {
                    "code": "relationship_direction",
                    "message": f"'{relationship}' cannot connect {s_kind} -> {t_kind}",
                }
            )
    elif relationship == "references":
        if s_kind != "information_object" or t_kind != "information_object":
            issues.append(
                {"code": "relationship_direction", "message": "ER edges connect entities"}
            )
    elif relationship == proposals.USES_REPOSITORY:
        if s_kind != "component" or t_kind != "data_repository":
            issues.append(
                {
                    "code": "relationship_direction",
                    "message": "uses_repository goes component -> repository",
                }
            )
    elif relationship == proposals.DEPLOYED_ON:
        if s_kind != "component" or t_kind != "deployment_node":
            issues.append(
                {
                    "code": "relationship_direction",
                    "message": "deployed_on goes component -> deployment node",
                }
            )
    elif relationship == proposals.CROSSES:
        if s_kind != "interface" or t_kind != "trust_boundary":
            issues.append(
                {
                    "code": "relationship_direction",
                    "message": "crosses goes interface -> trust boundary",
                }
            )
    elif relationship == proposals.CONTAINED_IN:
        if s_kind not in {"component", "system"} or t_kind != "trust_boundary":
            issues.append(
                {
                    "code": "relationship_direction",
                    "message": "contained_in goes component/system -> trust boundary",
                }
            )
    elif relationship == proposals.CONNECTS_TO:
        source_direction = _ref_direction(ctx, s_status, s_payload)
        target_direction = _ref_direction(ctx, t_status, t_payload)
        if (
            s_kind != "interface"
            or t_kind != "interface"
            or source_direction != "required"
            or target_direction != "provided"
        ):
            issues.append(
                {
                    "code": "relationship_direction",
                    "message": "Interface connections must go required -> provided",
                }
            )
    return issues


def _validate_realization(
    ctx: HelperContext,
    pv: dict[str, Any],
    by_temp: dict[str, HelperChangeOperation],
    closure: set[str],
) -> list[dict[str, Any]]:
    if pv.get("unresolved"):
        return []
    issues: list[dict[str, Any]] = []
    status_kind, detail, _ = _resolve_ref(
        ctx, pv.get("attribute_ref"), by_temp, closure, {"information_attribute"}
    )
    if status_kind == "error":
        issues.append({"code": detail, "message": "Attribute reference did not resolve"})
    field_id = pv.get("catalog_field_id")
    resolved_field = None
    if field_id:
        try:
            resolved_field = matching.find_catalog_field_by_id(ctx, UUID(str(field_id)))
        except (ValueError, AttributeError):
            resolved_field = None
    if field_id is None or resolved_field is None:
        issues.append({"code": "unknown_target", "message": "Catalog field not found or inactive"})
    return issues


def _validate_interaction(
    ctx: HelperContext,
    pv: dict[str, Any],
    by_temp: dict[str, HelperChangeOperation],
    closure: set[str],
) -> list[dict[str, Any]]:
    if pv.get("unresolved"):
        return []
    evidence = pv.get("evidence_refs") or []
    if not evidence:
        return [
            {
                "code": "missing_evidence",
                "message": "An interaction needs interface, operation, or connection evidence",
            }
        ]
    issues: list[dict[str, Any]] = []
    for ref in evidence:
        status_kind, detail, _ = _resolve_ref(
            ctx, ref, by_temp, closure, {"interface", "interface_operation"}
        )
        if status_kind == "error":
            issues.append({"code": detail, "message": "Interaction evidence did not resolve"})
    return issues


# --- Slice 3 domain validation ----------------------------------------------


def _as_uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _resolve_contract_ref(
    ctx: HelperContext,
    ref: Any,
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
    closure: set[str],
) -> tuple[str, str, Any]:
    """Resolve a temporary or canonical Contract reference."""
    if not isinstance(ref, str) or not ref:
        return "error", "missing_reference", None
    if ref.startswith("tmp:"):
        creator = by_temp.get(ref)
        if creator is None:
            return "error", "unknown_temporary_id", None
        if creator.operation_id not in closure:
            return "error", "missing_dependency", None
        if creator.target_type != "contract":
            return "error", "reference_kind_mismatch", None
        return "temp", "contract", creator
    contract = matching.find_contract(ctx, _as_uuid(ref))
    if contract is None:
        return "error", "unknown_target", None
    return "canonical", "contract", contract


def _resolve_scenario_ref(
    ctx: HelperContext,
    ref: Any,
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
    closure: set[str],
) -> tuple[str, str, Any]:
    if not isinstance(ref, str) or not ref:
        return "error", "missing_reference", None
    if ref.startswith("tmp:"):
        creator = by_temp.get(ref)
        if creator is None:
            return "error", "unknown_temporary_id", None
        if creator.operation_id not in closure:
            return "error", "missing_dependency", None
        if creator.target_type != "scenario":
            return "error", "reference_kind_mismatch", None
        return "temp", "scenario", creator
    scenario = ctx.db.scalar(
        select(Scenario).where(
            Scenario.id == _as_uuid(ref),
            Scenario.tenant_id == ctx.tenant_id,
            Scenario.deleted_at.is_(None),
        )
    )
    if scenario is None:
        return "error", "unknown_target", None
    return "canonical", "scenario", scenario


def _contract_endpoint_payload(status_kind: str, payload: Any) -> dict[str, Any]:
    if status_kind == "temp":
        return payload.proposed_value or {}
    return {
        "source_object_id": str(payload.source_object_id),
        "target_object_id": str(payload.target_object_id),
        "error_response_object_id": (
            str(payload.error_response_object_id) if payload.error_response_object_id else None
        ),
    }


def _validate_contract_proposal(ctx: HelperContext, pv: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    source_system_id = _as_uuid(pv.get("source_system_id"))
    target_system_id = _as_uuid(pv.get("target_system_id"))
    source_system = (
        matching.find_catalog_system(ctx, source_system_id) if source_system_id else None
    )
    target_system = (
        matching.find_catalog_system(ctx, target_system_id) if target_system_id else None
    )
    if source_system is None:
        issues.append({"code": "unknown_target", "message": "Source system is not active"})
    if target_system is None:
        issues.append({"code": "unknown_target", "message": "Target system is not active"})
    source_object = matching.find_catalog_object(ctx, _as_uuid(pv.get("source_object_id")))
    target_object = matching.find_catalog_object(ctx, _as_uuid(pv.get("target_object_id")))
    if source_object is None:
        issues.append({"code": "unknown_target", "message": "Source Catalog object is not active"})
    elif source_system is not None and source_object.system_id != source_system.id:
        issues.append(
            {"code": "object_system_mismatch", "message": "Source object is not in its system"}
        )
    if target_object is None:
        issues.append({"code": "unknown_target", "message": "Target Catalog object is not active"})
    elif target_system is not None and target_object.system_id != target_system.id:
        issues.append(
            {"code": "object_system_mismatch", "message": "Target object is not in its system"}
        )
    error_id = _as_uuid(pv.get("error_response_object_id"))
    if error_id is not None:
        error_object = matching.find_catalog_object(ctx, error_id)
        if error_object is None:
            issues.append(
                {"code": "unknown_target", "message": "Error response object is not active"}
            )
        elif target_system is not None and error_object.system_id != target_system.id:
            issues.append(
                {
                    "code": "object_system_mismatch",
                    "message": "Error response object is not in the target system",
                }
            )
    producer_id = _as_uuid(pv.get("producer_interface_id"))
    if producer_id is not None:
        producer = matching.find_interface(ctx, producer_id)
        if producer is None:
            issues.append({"code": "unknown_target", "message": "Producer interface not found"})
        elif producer.direction != "provided":
            issues.append(
                {
                    "code": "interface_direction",
                    "message": "The producer interface must be a provided interface",
                }
            )
    consumer_id = _as_uuid(pv.get("consumer_interface_id"))
    if consumer_id is not None:
        consumer = matching.find_interface(ctx, consumer_id)
        if consumer is None:
            issues.append({"code": "unknown_target", "message": "Consumer interface not found"})
        elif consumer.direction != "required":
            issues.append(
                {
                    "code": "interface_direction",
                    "message": "The consumer interface must be a required interface",
                }
            )
    for phase_key in ("request_phase", "success_response_phase", "error_response_phase"):
        phase = pv.get(phase_key)
        if not isinstance(phase, dict):
            continue
        for ref in phase.get("operation_refs") or []:
            operation_id = _as_uuid(ref.get("operation_id"))
            operation = (
                matching.find_interface_operation(ctx, operation_id) if operation_id else None
            )
            if operation_id is not None and operation is None:
                issues.append(
                    {"code": "unknown_target", "message": "A phase operation is not active"}
                )
            elif operation is not None and ref.get("kind"):
                if operation.operation_kind != ref.get("kind"):
                    issues.append(
                        {
                            "code": "operation_kind_mismatch",
                            "message": "The declared operation kind does not match the operation",
                        }
                    )
    if (
        pv.get("interaction_type") == "REQUEST_RESPONSE"
        and pv.get("pattern") not in integration_proposals.API_PATTERNS
    ):
        issues.append(
            {
                "code": "pattern_interaction",
                "message": "Request/reply requires an API-style integration pattern",
            }
        )
    if pv.get("runtime_mediated"):
        runtime_id = _as_uuid(pv.get("runtime_system_id"))
        runtime = matching.find_catalog_system(ctx, runtime_id) if runtime_id else None
        if runtime is None:
            issues.append(
                {
                    "code": "missing_runtime",
                    "message": "Runtime-mediated integration needs a runtime",
                }
            )
        elif not matching.is_runtime_system(runtime):
            issues.append(
                {"code": "not_a_runtime", "message": "The referenced system is not a runtime"}
            )
    specification = pv.get("specification") or {}
    idempotency_key = _as_uuid(specification.get("idempotency_key_field_id"))
    if idempotency_key is not None:
        field = matching.find_catalog_field_by_id(ctx, idempotency_key)
        if field is None:
            issues.append(
                {"code": "idempotency_field", "message": "Idempotency key field is not active"}
            )
        else:
            allowed_objects = {
                item.id for item in (source_object, target_object) if item is not None
            }
            if field.object_id not in allowed_objects:
                issues.append(
                    {
                        "code": "idempotency_field",
                        "message": "Idempotency key field must belong to a contract endpoint",
                    }
                )
    based_on = _as_uuid(pv.get("based_on_contract_id"))
    if based_on is not None and matching.find_contract(ctx, based_on) is None:
        issues.append(
            {"code": "unknown_target", "message": "The based-on Contract no longer exists"}
        )
    return issues


def _validate_mapping(
    ctx: HelperContext,
    pv: dict[str, Any],
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
    closure: set[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if pv.get("unresolved"):
        return issues
    for role in ("source", "target"):
        field_id = _as_uuid(pv.get(f"{role}_field_id"))
        field = matching.find_catalog_field_by_id(ctx, field_id) if field_id else None
        if field is None:
            issues.append({"code": "unknown_target", "message": f"The {role} field is not active"})
            continue
        expected_object = _as_uuid(pv.get(f"{role}_object_id"))
        if expected_object is not None and field.object_id != expected_object:
            issues.append(
                {
                    "code": "mapping_object_mismatch",
                    "message": f"The {role} field does not belong to the mapped object",
                }
            )
    return issues


def _validate_transformation(
    ctx: HelperContext,
    pv: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    node_type = pv.get("node_type")
    if node_type not in NODE_CONFIG_KEYS:
        issues.append(
            {
                "code": "unknown_transformation",
                "message": f"Unsupported transformation {node_type!r}",
            }
        )
    else:
        try:
            validate_node_config({"type": node_type, "config": pv.get("config") or {}}, "node")
        except OperationFailure as error:
            issues.append({"code": error.code, "message": error.message})
    target_field = _as_uuid(pv.get("target_field_id"))
    if target_field is None or matching.find_catalog_field_by_id(ctx, target_field) is None:
        issues.append({"code": "unknown_target", "message": "The target field is not active"})
    for source_id in pv.get("source_field_ids") or []:
        field_id = _as_uuid(source_id)
        if field_id is None or matching.find_catalog_field_by_id(ctx, field_id) is None:
            issues.append({"code": "unknown_target", "message": "A source field is not active"})
    return issues


def _validate_resilience(
    ctx: HelperContext,
    pv: dict[str, Any],
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
    closure: set[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    status_kind, _detail, _payload = _resolve_contract_ref(
        ctx, pv.get("contract_ref"), by_temp, by_id, closure
    )
    if status_kind == "error":
        return issues
    if status_kind == "canonical":
        issues.append(
            {
                "code": "reused_contract_mutation",
                "message": "A reused Contract is read-only; propose a new draft Contract instead",
            }
        )
    idempotency_key = _as_uuid(pv.get("idempotency_key_field_id"))
    if (
        idempotency_key is not None
        and matching.find_catalog_field_by_id(ctx, idempotency_key) is None
    ):
        issues.append(
            {"code": "unknown_target", "message": "The idempotency key field is not active"}
        )
    return issues


def _validate_scenario(
    ctx: HelperContext,
    pv: dict[str, Any],
    ref_status: str,
    ref_payload: Any,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    document = pv.get("document")
    if not isinstance(document, dict):
        return [{"code": "missing_scenario", "message": "A scenario document is required"}]
    try:
        model = ScenarioDocument.model_validate(document)
    except ValidationError:
        return [{"code": "invalid_scenario", "message": "The scenario document is invalid"}]
    endpoints = _contract_endpoint_payload(ref_status, ref_payload)
    allowed: set[UUID] = set()
    for key in ("source_object_id", "target_object_id", "error_response_object_id"):
        object_id = _as_uuid(endpoints.get(key))
        if object_id is not None:
            allowed |= {field.id for field in matching.list_active_fields(ctx, object_id)}
    for step in model.steps():
        for values in (step.sample_values, step.expected_values):
            for field_key in values:
                if _as_uuid(field_key) not in allowed:
                    issues.append(
                        {
                            "code": "unknown_target",
                            "message": "A scenario field is outside the contract endpoints",
                        }
                    )
    return issues


def _validate_conformance(
    ctx: HelperContext,
    pv: dict[str, Any],
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
    closure: set[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    scenario_ref = pv.get("scenario_ref")
    if scenario_ref is not None:
        status_kind, detail, payload = _resolve_scenario_ref(
            ctx, scenario_ref, by_temp, by_id, closure
        )
        if status_kind == "error":
            issues.append({"code": detail, "message": "The scenario reference did not resolve"})
        else:
            scenario_contract = (
                (payload.proposed_value or {}).get("contract_ref")
                if status_kind == "temp"
                else str(payload.scope_integration_id)
                if payload.scope_integration_id
                else None
            )
            if scenario_contract != pv.get("contract_ref"):
                issues.append(
                    {
                        "code": "scenario_contract_mismatch",
                        "message": "The scenario belongs to a different Contract",
                    }
                )
    for field_id in pv.get("field_ids") or []:
        parsed = _as_uuid(field_id)
        if parsed is None or matching.find_catalog_field_by_id(ctx, parsed) is None:
            issues.append(
                {"code": "unknown_target", "message": "A conformance field is not active"}
            )
    return issues


def _validate_slice3_operation(
    ctx: HelperContext,
    op: HelperChangeOperation,
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    pv = op.proposed_value or {}
    closure = _dependency_closure(op, by_id)
    action = op.domain_action

    if action in {
        "create_mapping",
        "create_transformation",
        "configure_resilience",
        "create_scenario",
        "define_conformance_expectation",
    }:
        ref_status, detail, ref_payload = _resolve_contract_ref(
            ctx, pv.get("contract_ref"), by_temp, by_id, closure
        )
        if ref_status == "error":
            issues.append({"code": detail, "message": "Contract reference did not resolve"})
        if action == "create_mapping":
            issues.extend(_validate_mapping(ctx, pv, by_temp, by_id, closure))
        elif action == "create_transformation":
            issues.extend(_validate_transformation(ctx, pv))
        elif action == "configure_resilience":
            issues.extend(_validate_resilience(ctx, pv, by_temp, by_id, closure))
        elif action == "create_scenario":
            if ref_status != "error":
                issues.extend(_validate_scenario(ctx, pv, ref_status, ref_payload))
        elif action == "define_conformance_expectation":
            issues.extend(_validate_conformance(ctx, pv, by_temp, by_id, closure))
        return issues

    if action == "create_contract":
        if op.temporary_id is None:
            issues.append(
                {"code": "missing_temporary_id", "message": "A new Contract needs a temp id"}
            )
        issues.extend(_validate_contract_proposal(ctx, pv))
    elif action == "reuse_contract":
        if op.target_id is None:
            issues.append({"code": "missing_target", "message": "reuse_contract needs a target"})
        elif matching.find_contract(ctx, op.target_id) is None:
            issues.append(
                {"code": "unknown_target", "message": "The reused Contract is not active"}
            )
        if pv.get("changes"):
            issues.append(
                {
                    "code": "reused_contract_mutation",
                    "message": "A reused Contract must be reused unchanged",
                }
            )
    return issues


def _validate_domain_operation(
    ctx: HelperContext,
    op: HelperChangeOperation,
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if op.domain_action in SLICE3_ACTIONS:
        return _validate_slice3_operation(ctx, op, by_temp, by_id)
    if op.domain_action in SLICE7_ACTIONS:
        return _validate_refinement_operation(ctx, op, by_temp, by_id)
    pv = op.proposed_value or {}
    closure = _dependency_closure(op, by_id)
    action = op.domain_action

    if action == "create_object":
        kind = pv.get("kind")
        if kind not in proposals.ALL_KINDS:
            issues.append({"code": "unknown_kind", "message": f"Unknown kind {kind!r}"})
        elif kind not in proposals.CROSS_KINDS:
            discipline = proposals.KIND_DISCIPLINE.get(proposals.registry_kind(kind))
            if discipline not in ctx.disciplines:
                issues.append(
                    {
                        "code": "disabled_discipline",
                        "message": f"{discipline} is not enabled for this workspace",
                    }
                )
        if op.temporary_id is None:
            issues.append(
                {"code": "missing_temporary_id", "message": "A created object needs a temp id"}
            )
        parent_ref = pv.get("parent_ref")
        if parent_ref is not None and kind in PARENT_EXPECTED_KIND:
            status_kind, detail, _ = _resolve_ref(
                ctx, parent_ref, by_temp, closure, PARENT_EXPECTED_KIND[kind]
            )
            if status_kind == "error":
                issues.append({"code": detail, "message": "Parent reference did not resolve"})
    elif action == "include_object":
        kind = pv.get("kind")
        if op.target_id is None:
            issues.append({"code": "missing_target", "message": "include_object needs a target"})
        elif kind == "catalog_field":
            if matching.find_catalog_field_by_id(ctx, op.target_id) is None:
                issues.append({"code": "unknown_target", "message": "Catalog field not found"})
        else:
            expected = {proposals.registry_kind(kind)} if kind else None
            registry = matching.find_registry(ctx, op.target_id, expected)
            if registry is None:
                issues.append({"code": "unknown_target", "message": "Target not found"})
            elif kind not in proposals.CROSS_KINDS:
                discipline = proposals.KIND_DISCIPLINE.get(proposals.registry_kind(kind))
                if discipline not in ctx.disciplines:
                    issues.append(
                        {
                            "code": "disabled_discipline",
                            "message": f"{discipline} is not enabled for this workspace",
                        }
                    )
    elif action == "override_object":
        if op.target_id is None:
            issues.append({"code": "missing_target", "message": "override_object needs a target"})
        elif not present_in_current(ctx.db, ctx.workspace, op.target_id):
            issues.append(
                {
                    "code": "override_not_in_current",
                    "message": "Only objects present in Current may carry Candidate overrides",
                }
            )
    elif action == "create_link":
        issues.extend(_validate_link(ctx, pv, by_temp, closure))
    elif action == "set_realization":
        issues.extend(_validate_realization(ctx, pv, by_temp, closure))
    elif action == "record_interaction":
        issues.extend(_validate_interaction(ctx, pv, by_temp, closure))
    return issues


def _validate_refinement_operation(
    ctx: HelperContext,
    op: HelperChangeOperation,
    by_temp: dict[str, HelperChangeOperation],
    by_id: dict[str, HelperChangeOperation],
) -> list[dict[str, Any]]:
    """Deterministic validation for the Slice 7 refinement operations."""
    issues: list[dict[str, Any]] = []
    pv = op.proposed_value or {}
    action = op.domain_action

    if action in {"set_lifecycle", "set_operational_status", "set_environment_scope"}:
        kind = pv.get("kind")
        if kind == "catalog_system":
            if op.target_id is None or matching.find_catalog_system(ctx, op.target_id) is None:
                issues.append(
                    {"code": "unknown_target", "message": "The Catalog system is not active"}
                )
        elif kind == "contract":
            if op.target_id is None or matching.find_contract(ctx, op.target_id) is None:
                issues.append(
                    {"code": "unknown_target", "message": "The Contract is not active"}
                )
        else:
            issues.append({"code": "unknown_kind", "message": f"Unknown fact target {kind!r}"})
        field = pv.get("field")
        if field not in refinement_proposals.FACT_FIELDS:
            issues.append({"code": "unknown_fact", "message": f"Unknown fact {field!r}"})
        elif field in (pv.get("changes") or {}):
            value = (pv.get("changes") or {})[field]
            allowed = _FACT_VOCABULARIES[field]
            if value is not None and value not in allowed:
                issues.append(
                    {
                        "code": "invalid_fact_value",
                        "message": f"{field} must be one of the approved values",
                    }
                )
        else:
            issues.append(
                {"code": "missing_change", "message": "The operation carries no change"}
            )
        return issues

    if action == "set_contract_mediator":
        if op.target_id is None:
            issues.append(
                {"code": "missing_target", "message": "set_contract_mediator needs a target"}
            )
            return issues
        contract = matching.find_contract(ctx, op.target_id)
        if contract is None:
            issues.append({"code": "unknown_target", "message": "The Contract is not active"})
            return issues
        mediator_id = _as_uuid(pv.get("mediator_system_id"))
        if mediator_id is None:
            issues.append({"code": "missing_mediator", "message": "No mediator was supplied"})
            return issues
        mediator = matching.find_catalog_system(ctx, mediator_id)
        if mediator is None:
            issues.append({"code": "unknown_mediator", "message": "The mediator is not active"})
        elif mediator.id == contract.source_system_id:
            issues.append(
                {"code": "mediator_is_source", "message": "The mediator cannot be the source"}
            )
        elif mediator.id == contract.target_system_id:
            issues.append(
                {"code": "mediator_is_target", "message": "The mediator cannot be the target"}
            )
        # The mediator is canonical, so a Contract described by Current is protected.
        if refinement_proposals.contract_used_by_current(ctx, contract.id):
            issues.append(
                {
                    "code": "mediator_affects_current",
                    "message": (
                        "This Contract is described by the read-only Current state; its "
                        "canonical mediator cannot be changed"
                    ),
                }
            )
        return issues

    if action == "attach_evidence":
        target_kind = pv.get("target_kind")
        if target_kind not in refinement_proposals.EVIDENCE_TARGET_KINDS:
            issues.append(
                {"code": "unsupported_evidence_target", "message": "Unsupported evidence target"}
            )
            return issues
        target_id = _as_uuid(pv.get("target_id")) or op.target_id
        if target_id is None:
            issues.append({"code": "missing_target", "message": "Evidence needs a target"})
        elif not _evidence_target_available(ctx, target_kind, target_id):
            issues.append(
                {
                    "code": "unknown_evidence_target",
                    "message": "The evidence target does not exist in this workspace",
                }
            )
        return issues

    if action == "associate_contract_with_solution":
        if op.target_id is None or matching.find_registry(
            ctx, op.target_id, {"solution_boundary"}
        ) is None:
            issues.append(
                {"code": "unknown_solution", "message": "The Solution Boundary was not found"}
            )
            return issues
        contract = matching.find_contract(ctx, _as_uuid(pv.get("integration_id")))
        if contract is None:
            issues.append(
                {"code": "unknown_contract", "message": "The Contract is not active"}
            )
        if pv.get("role") not in {"owned", "participating", "dependency"}:
            issues.append({"code": "invalid_role", "message": "Unsupported association role"})
        return issues

    if action == "create_solution_relationship":
        source_id = _as_uuid(pv.get("source_object_id"))
        target_id = _as_uuid(pv.get("target_object_id"))
        if source_id is None or target_id is None:
            issues.append(
                {"code": "missing_endpoint", "message": "Both Solutions are required"}
            )
            return issues
        if source_id == target_id:
            issues.append(
                {"code": "self_relationship", "message": "A Solution cannot relate to itself"}
            )
            return issues
        for endpoint in (source_id, target_id):
            if matching.find_registry(ctx, endpoint, {"solution_boundary"}) is None:
                issues.append(
                    {"code": "unknown_solution", "message": "A Solution Boundary was not found"}
                )
        if pv.get("relationship_type") not in SOLUTION_RELATIONSHIP_TYPES:
            issues.append(
                {"code": "invalid_relationship_type", "message": "Unsupported relationship type"}
            )
        return issues

    return issues


_FACT_VOCABULARIES: dict[str, tuple[str, ...]] = {
    "lifecycle_stage": LIFECYCLE_STAGES,
    "operational_status": OPERATIONAL_STATUSES,
    "environment_scope": ENVIRONMENT_SCOPES,
}

# Evidence uses the closed target arc; the API speaks in target kinds.
EVIDENCE_TARGET_MODELS: dict[str, type] = {
    "architecture_object": ArchitectureObject,
    "architecture_relationship": ArchitectureRelationship,
    "integration": Integration,
    "integration_dependency": IntegrationDependency,
    "solution_member": SolutionMember,
}

SOLUTION_RELATIONSHIP_TYPES = (
    "depends_on",
    "uses",
    "provides_to",
    "replaces",
    "transitions_to",
    "shares_information_with",
)


def _evidence_target_available(ctx: HelperContext, target_kind: str, target_id: UUID) -> bool:
    model = EVIDENCE_TARGET_MODELS.get(target_kind)
    if model is None:
        return False
    return (
        ctx.db.scalar(
            select(model.id).where(model.id == target_id, model.tenant_id == ctx.tenant_id)
        )
        is not None
    )


def _duplicate_operations(operations: list[HelperChangeOperation]) -> set[str]:
    seen: dict[tuple, str] = {}
    duplicates: set[str] = set()
    for op in operations:
        pv = op.proposed_value or {}
        if op.domain_action == "create_object":
            key = (
                "create_object",
                pv.get("kind"),
                pv.get("parent_ref"),
                matching.normalize_name(pv.get("name", "")),
            )
        elif op.domain_action == "create_link":
            key = (
                "create_link",
                pv.get("relationship_type"),
                pv.get("source_ref"),
                pv.get("target_ref"),
            )
        elif op.domain_action == "include_object":
            key = ("include_object", str(op.target_id))
        elif op.domain_action == "reuse_contract":
            key = ("reuse_contract", str(op.target_id))
        elif op.domain_action == "create_contract":
            key = ("create_contract", matching.normalize_name(pv.get("name", "")))
        elif op.domain_action == "create_mapping":
            key = (
                "create_mapping",
                pv.get("contract_ref"),
                pv.get("phase"),
                pv.get("source_field_id"),
                pv.get("target_field_id"),
            )
        elif op.domain_action == "create_transformation":
            key = (
                "create_transformation",
                pv.get("contract_ref"),
                pv.get("phase"),
                pv.get("node_type"),
                pv.get("target_field_id"),
            )
        elif op.domain_action == "configure_resilience":
            key = ("configure_resilience", pv.get("contract_ref"))
        elif op.domain_action == "create_scenario":
            key = ("create_scenario", matching.normalize_name(pv.get("name", "")))
        elif op.domain_action == "define_conformance_expectation":
            key = (
                "define_conformance_expectation",
                pv.get("contract_ref"),
                pv.get("expectation_type"),
                pv.get("phase"),
                pv.get("scenario_ref"),
            )
        elif op.domain_action in {
            "set_lifecycle",
            "set_operational_status",
            "set_environment_scope",
        }:
            key = (op.domain_action, pv.get("kind"), str(op.target_id))
        elif op.domain_action == "set_contract_mediator":
            key = ("set_contract_mediator", str(op.target_id))
        elif op.domain_action == "attach_evidence":
            key = ("attach_evidence", str(pv.get("target_kind")), str(op.target_id))
        elif op.domain_action == "associate_contract_with_solution":
            key = ("associate_contract_with_solution", str(pv.get("integration_id")))
        elif op.domain_action == "create_solution_relationship":
            key = (
                "create_solution_relationship",
                pv.get("source_object_id"),
                pv.get("target_object_id"),
                pv.get("relationship_type"),
            )
        else:
            continue
        if key in seen:
            duplicates.add(op.operation_id)
            duplicates.add(seen[key])
        else:
            seen[key] = op.operation_id
    return duplicates


def validate_change_set(ctx: HelperContext, change_set: HelperChangeSet) -> HelperChangeSet:
    if sync_staleness(ctx, change_set):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proposal_stale", "message": "The proposal changed; re-create it"},
        )
    operations = [
        op for op in load_operations(ctx.db, change_set.id) if op.resolution_state == "active"
    ]
    known = {op.operation_id for op in operations}
    issues: dict[str, list[dict[str, Any]]] = {op.operation_id: [] for op in operations}
    aggregate: list[dict[str, Any]] = []

    if change_set.state_id is not None:
        state = resolve_state(ctx, change_set.state_id)
        if state.state_type == "current":
            aggregate.append(
                {"code": "current_target", "message": "Current cannot be a proposal target"}
            )

    by_temp = {op.temporary_id: op for op in operations if op.temporary_id}
    by_id = {op.operation_id: op for op in operations}

    for op in operations:
        if (
            op.domain_action in DOMAIN_ACTIONS
            or op.domain_action in SLICE3_ACTIONS
            or op.domain_action in SLICE7_ACTIONS
        ):
            issues[op.operation_id].extend(_validate_domain_operation(ctx, op, by_temp, by_id))
        elif op.target_id is not None and not _target_exists(ctx, op):
            issues[op.operation_id].append(
                {"code": "unknown_target", "message": f"Target {op.target_id} not found"}
            )
        for dep in op.depends_on or []:
            if dep not in known:
                issues[op.operation_id].append(
                    {"code": "unknown_dependency", "message": f"Dependency {dep} not found"}
                )

    for operation_id in _find_cycle(operations):
        issues[operation_id].append(
            {"code": "dependency_cycle", "message": "Circular dependency detected"}
        )

    for operation_id in _duplicate_operations(operations):
        issues[operation_id].append(
            {"code": "duplicate_operation", "message": "Duplicate operation detected"}
        )

    invalid = {oid for oid, items in issues.items() if items}
    changed = True
    while changed:
        changed = False
        for op in operations:
            if op.operation_id in invalid:
                continue
            if any(dep in invalid for dep in op.depends_on or []):
                issues[op.operation_id].append(
                    {"code": "blocked_dependency", "message": "A dependency is invalid"}
                )
                invalid.add(op.operation_id)
                changed = True

    unresolved_ops: list[HelperChangeOperation] = []
    for op in operations:
        op_issues = issues[op.operation_id]
        op.validation_issues = op_issues
        if op_issues:
            op.validation_status = "invalid"
        elif (op.proposed_value or {}).get("unresolved"):
            op.validation_status = "unresolved"
            unresolved_ops.append(op)
        else:
            op.validation_status = "valid"
        for issue in op_issues:
            aggregate.append({"operation_id": op.operation_id, **issue})

    unresolved_decisions: list[str] = []
    merged_decisions = list(change_set.unresolved_decisions or [])
    for op in unresolved_ops:
        reason = (op.proposed_value or {}).get("reason") or (
            f"Unresolved decision in {op.operation_id}"
        )
        if reason not in merged_decisions:
            merged_decisions.append(reason)
        if reason not in unresolved_decisions:
            unresolved_decisions.append(reason)
    change_set.unresolved_decisions = merged_decisions
    # Optional unresolved mappings may remain documented without blocking approval;
    # required unresolved decisions keep the proposal out of the approvable state.
    blocking_unresolved = [
        op for op in unresolved_ops if (op.proposed_value or {}).get("required_for_approval", True)
    ]
    ready_for_approval = not invalid and not blocking_unresolved

    valid_count = len(operations) - len(invalid) - len(unresolved_ops)
    change_set.validation_summary = {
        "operations": len(operations),
        "valid": valid_count,
        "invalid": len(invalid),
        "unresolved": len(unresolved_ops),
        "blocking_unresolved": len(blocking_unresolved),
        "ready_for_approval": ready_for_approval,
        "unresolved_decisions": unresolved_decisions,
        "issues": aggregate[:200],
        "validated_at": _now().isoformat(),
    }
    if aggregate:
        change_set.status = "validation_failed"
        change_set.validated_at = None
        change_set.approved_by = None
        change_set.approved_at = None
        change_set.approved_hash = None
        event_type = "validation_failed"
    else:
        change_set.status = "validated"
        change_set.validated_at = _now()
        event_type = "validation_passed"
    change_set.updated_at = _now()

    add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type=event_type,
        change_set_id=change_set.id,
        state_id=change_set.state_id,
        summary={
            "operations": len(operations),
            "invalid": len(invalid),
            "unresolved": len(unresolved_ops),
            "ready_for_approval": ready_for_approval,
            "proposal_hash": change_set.proposal_hash,
        },
    )
    ctx.db.commit()
    ctx.db.refresh(change_set)
    return change_set


def approve_change_set(ctx: HelperContext, change_set: HelperChangeSet) -> HelperChangeSet:
    if sync_staleness(ctx, change_set):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proposal_stale", "message": "The proposal changed; re-validate it"},
        )
    if change_set.status != "validated":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "not_validated", "message": "The proposal must be validated first"},
        )
    if not (change_set.validation_summary or {}).get("ready_for_approval", True):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "unresolved_decisions",
                "message": "Required unresolved decisions remain; resolve them before approval",
                "unresolved_decisions": (change_set.validation_summary or {}).get(
                    "unresolved_decisions", []
                ),
            },
        )
    operations = load_operations(ctx.db, change_set.id)
    current = compute_proposal_hash(change_set, operations)
    if change_set.proposal_hash != current:
        change_set.status = "stale"
        ctx.db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proposal_stale", "message": "The proposal hash no longer matches"},
        )

    change_set.status = "approved"
    change_set.approved_by = ctx.user.id
    change_set.approved_at = _now()
    change_set.approved_hash = change_set.proposal_hash
    change_set.updated_at = _now()
    add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type="approved",
        change_set_id=change_set.id,
        state_id=change_set.state_id,
        summary={
            "proposal_hash": change_set.proposal_hash,
            "proposed_by": str(change_set.proposed_by) if change_set.proposed_by else None,
            "approved_by": str(ctx.user.id),
        },
    )
    ctx.db.commit()
    ctx.db.refresh(change_set)
    return change_set


def to_response(ctx: HelperContext, change_set: HelperChangeSet) -> ChangeSetResponse:
    operations = load_operations(ctx.db, change_set.id)
    return ChangeSetResponse(
        id=change_set.id,
        tenant_id=change_set.tenant_id,
        workspace_id=change_set.workspace_id,
        state_id=change_set.state_id,
        state_type=change_set.state_type,
        helper_name=change_set.helper_name,
        status=change_set.status,
        summary=change_set.summary,
        input_summary=change_set.input_summary or {},
        assumptions=change_set.assumptions or [],
        unresolved_decisions=change_set.unresolved_decisions or [],
        unresolved_details=change_set.unresolved_details or [],
        warnings=change_set.warnings or [],
        reused_objects=change_set.reused_objects or [],
        proposed_objects=change_set.proposed_objects or [],
        expected_traceability=change_set.expected_traceability or {},
        validation_summary=change_set.validation_summary or {},
        proposal_hash=change_set.proposal_hash,
        proposed_by=change_set.proposed_by,
        approved_by=change_set.approved_by,
        approved_at=change_set.approved_at,
        approved_hash=change_set.approved_hash,
        validated_at=change_set.validated_at,
        apply_summary=change_set.apply_summary or {},
        undo_summary=change_set.undo_summary or {},
        applied_at=change_set.applied_at,
        undone_at=change_set.undone_at,
        created_at=change_set.created_at,
        updated_at=change_set.updated_at,
        operations=[
            OperationResponse(
                operation_id=op.operation_id,
                ordinal=op.ordinal,
                domain_action=op.domain_action,
                target_type=op.target_type,
                target_id=op.target_id,
                temporary_id=op.temporary_id,
                before_value=op.before_value,
                proposed_value=op.proposed_value or {},
                depends_on=op.depends_on or [],
                validation_status=op.validation_status,
                validation_issues=op.validation_issues or [],
                explanation=op.explanation,
                applied_id=op.applied_id,
                apply_status=op.apply_status,
                ownership=op.ownership or {},
                post_fingerprint=op.post_fingerprint or {},
                undo_status=op.undo_status,
                undo_conflict=op.undo_conflict or {},
                resolution_state=op.resolution_state,
            )
            for op in operations
        ],
    )
