"""Current baseline capture: bounded validation and the irreversible lock.

A workspace's Current state is captured while it is a ``draft`` and becomes the
read-only baseline when a human locks it. This module owns the two halves of that
transition and nothing else:

* :func:`validate_baseline` — a small, bounded check of the captured state.
* :func:`lock_baseline` — the transactional, one-way transition itself.

There is deliberately no unlock, no baseline revision, no approval queue and no
governance workflow here. The write policy the lock activates lives in
:mod:`app.architecture.state_scope`; this module only flips the switch and
records who did it and when.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.architecture.routes import get_accessible_workspace
from app.architecture.schemas import (
    BaselineIssue,
    BaselineLockRequest,
    BaselineLockResponse,
    BaselineValidation,
)
from app.architecture.state_scope import BASELINE_DRAFT, BASELINE_LOCKED
from app.architecture.vocabulary import CONFIRMED_EVIDENCE_CLASSIFICATIONS
from app.auth.dependencies import (
    AuthenticatedUser,
    AuthSession,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.models import (
    ArchitectureEvidence,
    ArchitectureInterface,
    ArchitectureObject,
    ArchitecturePrinciple,
    ArchitectureState,
    BusinessCapability,
    BusinessGoal,
    BusinessProcess,
    BusinessRequirement,
    CatalogSystem,
    DataRepository,
    DeploymentNode,
    InformationAttribute,
    InformationObject,
    Integration,
    IntegrationDependency,
    InterfaceOperation,
    OrganizationRole,
    SolutionBoundary,
    SolutionComponent,
    SolutionIntegration,
    SolutionMember,
    TrustBoundary,
    Workspace,
)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/states", tags=["architecture"])

#: How many offending records one message names before it is truncated.
MAX_ISSUE_SAMPLES = 5
#: How many issues of each kind the response carries.
MAX_ISSUES = 20

#: Registry kind -> the typed record that must exist alongside it.
TYPED_MODELS: dict[str, type] = {
    "information_object": InformationObject,
    "information_attribute": InformationAttribute,
    "solution_boundary": SolutionBoundary,
    "component": SolutionComponent,
    "interface": ArchitectureInterface,
    "interface_operation": InterfaceOperation,
    "data_repository": DataRepository,
    "deployment_node": DeploymentNode,
    "trust_boundary": TrustBoundary,
    "business_goal": BusinessGoal,
    "business_requirement": BusinessRequirement,
    "business_capability": BusinessCapability,
    "business_process": BusinessProcess,
    "architecture_principle": ArchitecturePrinciple,
    "organization_role": OrganizationRole,
}
#: Typed records that name an owner. A blank owner is a warning, never a block.
OWNABLE_KINDS: tuple[str, ...] = ("information_object", "solution_boundary", "data_repository")


@dataclass
class BaselineReport:
    """Blocking errors, non-blocking warnings and a short objective summary."""

    blocking: list[BaselineIssue] = field(default_factory=list)
    warnings: list[BaselineIssue] = field(default_factory=list)
    summary: dict[str, object] = field(default_factory=dict)

    def to_model(self) -> BaselineValidation:
        return BaselineValidation(
            blocking=self.blocking[:MAX_ISSUES],
            warnings=self.warnings[:MAX_ISSUES],
            summary=self.summary,
        )


def _is_uuid(value: object) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _sample(names: list[str]) -> str:
    shown = names[:MAX_ISSUE_SAMPLES]
    suffix = f" and {len(names) - len(shown)} more" if len(names) > len(shown) else ""
    return ", ".join(shown) + suffix


def _node_list(state: ArchitectureState) -> list[dict]:
    return [node for node in (state.nodes or []) if isinstance(node, dict)]


def _relationship_list(state: ArchitectureState) -> list[dict]:
    return [item for item in (state.relationships or []) if isinstance(item, dict)]


def _registry(
    db: Session, workspace: Workspace, object_ids: list[UUID]
) -> dict[UUID, ArchitectureObject]:
    if not object_ids:
        return {}
    return {
        row.id: row
        for row in db.scalars(
            select(ArchitectureObject).where(
                ArchitectureObject.tenant_id == workspace.tenant_id,
                ArchitectureObject.id.in_(object_ids),
            )
        )
    }


def _included_contract_ids(state: ArchitectureState, registry: dict) -> set[UUID]:
    """Contracts the baseline describes: contract references and canvas edges."""
    included = {
        row.integration_id
        for row in registry.values()
        if row.kind == "contract_ref" and row.integration_id is not None
    }
    included.update(
        UUID(str(item["integration_id"]))
        for item in _relationship_list(state)
        if _is_uuid(item.get("integration_id"))
    )
    return {item for item in included if item is not None}


def validate_baseline(
    db: Session, workspace: Workspace, state: ArchitectureState
) -> BaselineReport:
    """Bounded, deterministic baseline validation.

    Blocking issues mean the captured state cannot be trusted as a baseline.
    Warnings are observations a human should see and may accept. Neither set
    requires complete Enterprise, Information, Solution or Integration modeling.
    """
    blocking: list[BaselineIssue] = []
    if state.state_type != "current":
        blocking.append(
            BaselineIssue(
                code="not_current_state",
                message="Only the Current state can be locked as the baseline.",
            )
        )

    nodes = _node_list(state)
    relationships = _relationship_list(state)
    raw_ids = [node.get("object_id") for node in nodes]
    malformed = [value for value in raw_ids if not _is_uuid(value)]
    if malformed:
        blocking.append(
            BaselineIssue(
                code="invalid_state_node",
                message=(
                    f"{len(malformed)} canvas node(s) do not reference an architecture object."
                ),
                count=len(malformed),
            )
        )
    object_ids = [UUID(str(value)) for value in raw_ids if _is_uuid(value)]
    registry = _registry(db, workspace, object_ids)

    missing_objects = [str(item) for item in object_ids if item not in registry]
    if missing_objects:
        blocking.append(
            BaselineIssue(
                code="unknown_state_object",
                message=(
                    "Canvas nodes reference architecture objects that no longer exist in "
                    f"this workspace: {_sample(missing_objects)}."
                ),
                count=len(missing_objects),
            )
        )

    typed_missing = _missing_typed_records(db, workspace, registry)
    if typed_missing:
        blocking.append(
            BaselineIssue(
                code="invalid_architecture_record",
                message=(
                    "Included architecture objects are missing their typed record: "
                    f"{_sample(typed_missing)}."
                ),
                count=len(typed_missing),
            )
        )

    occurrence_ids = {str(node.get("occurrence_id")) for node in nodes}
    dangling = [
        str(item.get("id") or "relationship")
        for item in relationships
        if str(item.get("source_id")) not in occurrence_ids
        or str(item.get("target_id")) not in occurrence_ids
    ]
    if dangling:
        blocking.append(
            BaselineIssue(
                code="invalid_state_relationship",
                message=(
                    "Canvas relationships connect nodes that are not in this state: "
                    f"{_sample(dangling)}."
                ),
                count=len(dangling),
            )
        )

    included_contracts = _included_contract_ids(state, registry)
    active_contracts: dict[UUID, Integration] = {}
    if included_contracts:
        active_contracts = {
            row.id: row
            for row in db.scalars(
                select(Integration).where(
                    Integration.tenant_id == workspace.tenant_id,
                    Integration.deleted_at.is_(None),
                    Integration.id.in_(included_contracts),
                )
            )
        }
        gone = [str(item) for item in included_contracts if item not in active_contracts]
        if gone:
            blocking.append(
                BaselineIssue(
                    code="unknown_state_contract",
                    message=(
                        "Canvas relationships reference contracts that are not active: "
                        f"{_sample(gone)}."
                    ),
                    count=len(gone),
                )
            )

    warnings: list[BaselineIssue] = []
    extra: dict[str, object] = {}
    if state.state_type == "current":
        warnings, extra = _warning_report(
            db, workspace, registry, active_contracts, object_ids
        )

    counts: Counter[str] = Counter()
    for issue in blocking:
        counts[f"blocking:{issue.code}"] += 1
    for issue in warnings:
        counts[f"warning:{issue.code}"] += 1
    return BaselineReport(
        blocking=blocking,
        warnings=warnings,
        summary={
            "node_count": len(nodes),
            "relationship_count": len(relationships),
            "object_count": len(registry),
            "included_contracts": len(active_contracts),
            "baseline_status": state.baseline_status,
            "state_id": str(state.id),
            "issue_counts": dict(sorted(counts.items())),
        },
    )


def _missing_typed_records(
    db: Session, workspace: Workspace, registry: dict[UUID, ArchitectureObject]
) -> list[str]:
    by_kind: dict[str, list[UUID]] = defaultdict(list)
    for row in registry.values():
        if row.kind in TYPED_MODELS:
            by_kind[row.kind].append(row.id)
    typed: set[UUID] = set()
    for kind, ids in by_kind.items():
        model = TYPED_MODELS[kind]
        typed.update(
            db.scalars(
                select(model.object_id).where(
                    model.tenant_id == workspace.tenant_id, model.object_id.in_(ids)
                )
            )
        )
    return [
        str(object_id)
        for ids in by_kind.values()
        for object_id in ids
        if object_id not in typed
    ]


def _warning_report(
    db: Session,
    workspace: Workspace,
    registry: dict[UUID, ArchitectureObject],
    active_contracts: dict[UUID, Integration],
    object_ids: list[UUID],
) -> tuple[list[BaselineIssue], dict[str, object]]:
    """Non-blocking observations about what the captured baseline says."""
    warnings: list[BaselineIssue] = []

    if not registry:
        warnings.append(
            BaselineIssue(
                code="empty_baseline",
                message="This baseline contains no architecture objects.",
            )
        )

    ownable = [row for row in registry.values() if row.kind in OWNABLE_KINDS]
    if ownable:
        owners = _owner_map(db, workspace, ownable)
        missing = [str(row.id) for row in ownable if not (owners.get(row.id) or "").strip()]
        if missing:
            warnings.append(
                BaselineIssue(
                    code="missing_owner",
                    message=f"Some included records have no owner: {_sample(missing)}.",
                    count=len(missing),
                )
            )

    included_systems = [
        row
        for row in db.scalars(
            select(CatalogSystem).where(
                CatalogSystem.tenant_id == workspace.tenant_id,
                CatalogSystem.deleted_at.is_(None),
                CatalogSystem.id.in_(object_ids or [UUID(int=0)]),
            )
        )
    ]
    unspecified = [
        row.name
        for row in included_systems
        if row.lifecycle_stage is None or row.operational_status is None
    ]
    if unspecified:
        warnings.append(
            BaselineIssue(
                code="unspecified_facts",
                message=(
                    "Some included systems have no lifecycle stage or operational status: "
                    f"{_sample(unspecified)}."
                ),
                count=len(unspecified),
            )
        )

    if active_contracts:
        evidenced = set(
            db.scalars(
                select(ArchitectureEvidence.integration_id).where(
                    ArchitectureEvidence.tenant_id == workspace.tenant_id,
                    ArchitectureEvidence.integration_id.in_(list(active_contracts)),
                )
            )
        )
        unevidenced = [
            row.name for row in active_contracts.values() if row.id not in evidenced
        ]
        if unevidenced:
            warnings.append(
                BaselineIssue(
                    code="contract_without_evidence",
                    message=f"Some contracts have no evidence: {_sample(unevidenced)}.",
                    count=len(unevidenced),
                )
            )

    unsettled = _unsettled_evidence(db, workspace, registry, object_ids, active_contracts)
    if unsettled:
        warnings.append(
            BaselineIssue(
                code="unresolved_evidence",
                message=(
                    "Some evidence is unverified or assumed: "
                    f"{_sample(unsettled)}."
                ),
                count=len(unsettled),
            )
        )

    included_boundaries = _included_boundaries(db, workspace, registry)
    if included_boundaries:
        associated = set(
            db.scalars(
                select(SolutionIntegration.solution_object_id).where(
                    SolutionIntegration.tenant_id == workspace.tenant_id,
                    SolutionIntegration.solution_object_id.in_(included_boundaries),
                )
            )
        )
        orphaned = [
            str(object_id)
            for object_id in included_boundaries
            if object_id not in associated
        ]
        if orphaned:
            warnings.append(
                BaselineIssue(
                    code="solution_without_contracts",
                    message=(
                        "Some included solutions have no associated contracts: "
                        f"{_sample(orphaned)}."
                    ),
                    count=len(orphaned),
                )
            )

    return warnings, {"included_systems": len(included_systems)}


def _owner_map(db: Session, workspace: Workspace, rows: list[ArchitectureObject]) -> dict:
    """Owner by object id, read from the typed record that carries the field."""
    owners: dict[UUID, str] = {}
    by_kind: dict[str, list[UUID]] = defaultdict(list)
    for row in rows:
        if row.kind in TYPED_MODELS:
            by_kind[row.kind].append(row.id)
    for kind, ids in by_kind.items():
        model = TYPED_MODELS[kind]
        for record in db.scalars(
            select(model).where(
                model.tenant_id == workspace.tenant_id, model.object_id.in_(ids)
            )
        ):
            owners[record.object_id] = getattr(record, "owner", "") or ""
    return owners


def _unsettled_evidence(
    db: Session,
    workspace: Workspace,
    registry: dict[UUID, ArchitectureObject],
    object_ids: list[UUID],
    active_contracts: dict[UUID, Integration],
) -> list[str]:
    """Evidence attached to the baseline that is not a settled, verified fact."""
    conditions = []
    if object_ids:
        conditions.append(ArchitectureEvidence.architecture_object_id.in_(object_ids))
    if active_contracts:
        contract_ids = list(active_contracts)
        conditions.append(ArchitectureEvidence.integration_id.in_(contract_ids))
        boundary_ids = _included_boundaries(db, workspace, registry)
        if boundary_ids:
            member_ids = list(
                db.scalars(
                    select(SolutionMember.id).where(
                        SolutionMember.tenant_id == workspace.tenant_id,
                        SolutionMember.solution_object_id.in_(boundary_ids),
                    )
                )
            )
            if member_ids:
                conditions.append(ArchitectureEvidence.solution_member_id.in_(member_ids))
        dependency_ids = list(
            db.scalars(
                select(IntegrationDependency.id).where(
                    IntegrationDependency.tenant_id == workspace.tenant_id,
                    IntegrationDependency.upstream_integration_id.in_(contract_ids),
                )
            )
        )
        if dependency_ids:
            conditions.append(
                ArchitectureEvidence.integration_dependency_id.in_(dependency_ids)
            )
    if not conditions:
        return []
    from sqlalchemy import or_

    rows = list(
        db.scalars(
            select(ArchitectureEvidence).where(
                ArchitectureEvidence.tenant_id == workspace.tenant_id,
                ArchitectureEvidence.verification_status != "verified",
                or_(*conditions),
            )
        )
    )
    return [
        row.source_title
        for row in rows
        if row.evidence_classification not in CONFIRMED_EVIDENCE_CLASSIFICATIONS
    ]


def _included_boundaries(
    db: Session, workspace: Workspace, registry: dict[UUID, ArchitectureObject]
) -> list[UUID]:
    if not registry:
        return []
    return list(
        db.scalars(
            select(SolutionBoundary.object_id).where(
                SolutionBoundary.tenant_id == workspace.tenant_id,
                SolutionBoundary.object_id.in_(list(registry)),
            )
        )
    )


def lock_baseline(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    *,
    actor_id: UUID,
    confirm_empty: bool,
) -> BaselineReport:
    """Lock the Current baseline. One transaction; no unlock path exists.

    The caller commits. Every refusal happens before any write, so a rejected
    lock never records metadata.
    """
    if state.state_type != "current":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "not_current_state",
                "message": "Only the Current state can be locked as the baseline.",
            },
        )
    if state.baseline_status != BASELINE_DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "baseline_already_locked",
                "message": "The Current baseline is already locked.",
                "baseline_locked_at": state.baseline_locked_at.isoformat()
                if state.baseline_locked_at
                else None,
                "baseline_locked_by": str(state.baseline_locked_by)
                if state.baseline_locked_by
                else None,
            },
        )

    report = validate_baseline(db, workspace, state)
    if report.blocking:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "baseline_validation_failed",
                "message": "The Current baseline is not valid yet and cannot be locked.",
                "validation": report.to_model().model_dump(),
            },
        )
    is_empty = any(issue.code == "empty_baseline" for issue in report.warnings)
    if is_empty and not confirm_empty:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "baseline_confirmation_required",
                "message": (
                    "This baseline is empty. Confirm that you want to lock an empty "
                    "Current baseline."
                ),
                "validation": report.to_model().model_dump(),
            },
        )

    now = datetime.now(UTC)
    state.baseline_status = BASELINE_LOCKED
    state.baseline_locked_at = now
    state.baseline_locked_by = actor_id
    state.updated_at = now
    db.flush()
    return report


@router.post("/{state_id}/lock-baseline", response_model=BaselineLockResponse)
def lock_baseline_endpoint(
    workspace_id: UUID,
    state_id: UUID,
    payload: BaselineLockRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> BaselineLockResponse:
    """Validate, and optionally lock, the Current baseline.

    ``validate_only`` returns the same bounded report without writing, so the
    dialog can show blocking errors and warnings before the human confirms. This
    is the only baseline endpoint: there is no unlock and no baseline revision.
    """
    require_csrf(request, auth_session)
    workspace = get_accessible_workspace(db, user, workspace_id)
    state = db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Architecture state not found"
        )

    if payload.validate_only:
        report = validate_baseline(db, workspace, state)
        return BaselineLockResponse(state=state, validation=report.to_model(), locked=False)

    report = lock_baseline(
        db, workspace, state, actor_id=user.id, confirm_empty=payload.confirm_empty
    )
    db.commit()
    db.refresh(state)
    return BaselineLockResponse(state=state, validation=report.to_model(), locked=True)
