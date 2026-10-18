"""Shared Current/Candidate/Target state-isolation helpers.

The Enterprise, Information, Solution and Integration modules all need the same
primitives: resolve a state, decide whether it accepts writes, locate the canvas
node for an object, read bounded scalar overrides, and upsert child
state-membership rows. Keeping them here means the editing rules are identical
across disciplines and can be documented once (see docs/current-vs-candidate.md).

**The Current write policy is defined once, here.** A Current state carries a
baseline lifecycle: while it is a ``draft`` it is an editable capture phase, and
once the baseline is locked it is read-only. Candidate and Target states are
always writable. Every guard in the application resolves through
:func:`assert_writable`; no route carries a local rule of its own.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BASELINE_DRAFT,
    BASELINE_LOCKED,
    BASELINE_STATUSES,
    ArchitectureObject,
    ArchitectureState,
    ArchitectureStateMember,
    Integration,
    Workspace,
)

__all__ = [
    "BASELINE_DRAFT",
    "BASELINE_LOCKED",
    "BASELINE_STATUSES",
    "CURRENT_BASELINE_LOCKED",
    "assert_contract_editable",
    "assert_writable",
    "baseline_status_of",
    "assert_contract_editable_for_tenant",
    "contract_anchored_in_current",
    "locked_baseline_anchors_contract",
    "state_anchors_contract",
    "current_state",
    "exclude_member",
    "get_state",
    "locked_current_baseline",
    "node_for_object",
    "node_overrides",
    "present_in_current",
    "set_member_override",
    "state_is_editable",
    "state_is_locked",
    "state_members",
]


def get_state(db: Session, workspace: Workspace, state_id: UUID) -> ArchitectureState:
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


#: The stable code every locked-baseline write refusal carries.
CURRENT_BASELINE_LOCKED = "current_baseline_locked"

_BASELINE_LOCKED_MESSAGE = (
    "The Current baseline is locked, so Current is read-only. "
    "Capture changes in a Candidate state instead."
)


def baseline_status_of(state: ArchitectureState) -> str | None:
    """The baseline lifecycle of a state, or ``None`` for Candidate/Target."""
    return state.baseline_status


def state_is_locked(state: ArchitectureState) -> bool:
    """True only for a Current state whose baseline is locked.

    A Current state with no recorded status fails closed and counts as locked,
    so a row written before the baseline lifecycle existed keeps its protection.
    """
    if state.state_type != "current":
        return False
    return (state.baseline_status or BASELINE_LOCKED) != BASELINE_DRAFT


def state_is_editable(state: ArchitectureState) -> bool:
    """The one editability rule: locked Current is read-only, everything else is not."""
    return not state_is_locked(state)


def assert_writable(state: ArchitectureState) -> None:
    """Refuse a write to a locked Current baseline.

    Draft Current, Candidate and Target states are all writable. Callers keep
    their own tenant, workspace, discipline and state-access checks; this only
    decides whether the resolved state accepts a structural change.
    """
    if state_is_locked(state):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": CURRENT_BASELINE_LOCKED,
                "message": _BASELINE_LOCKED_MESSAGE,
            },
        )


def locked_current_baseline(
    db: Session, workspace: Workspace
) -> ArchitectureState | None:
    """The workspace's Current state when it is locked, otherwise ``None``."""
    current = current_state(db, workspace)
    if current is None or not state_is_locked(current):
        return None
    return current


def state_anchors_contract(
    db: Session, tenant_id: UUID, state: ArchitectureState, integration_id: UUID
) -> bool:
    """The one anchoring predicate: does this state's canvas show the Contract?

    Either a state relationship carries the contract id (the shape
    ``include-objects`` writes, and the shape the demo uses) or a ``contract_ref``
    registry node bound to the contract is present on the canvas. It is stated
    once here so every consumer — the Slice 7 mediator rule, the Slice 8C
    baseline guard and the canonical Contract mutation guard — agrees on what
    "described by Current" means.
    """
    for relationship in state.relationships or []:
        if not isinstance(relationship, dict):
            continue
        if str(relationship.get("integration_id")) == str(integration_id):
            return True
    registry_ids = db.scalars(
        select(ArchitectureObject.id).where(
            ArchitectureObject.tenant_id == tenant_id,
            ArchitectureObject.kind == "contract_ref",
            ArchitectureObject.integration_id == integration_id,
        )
    )
    return any(node_for_object(state, object_id) is not None for object_id in registry_ids)


def contract_anchored_in_current(
    db: Session, workspace: Workspace, integration_id: UUID
) -> bool:
    """True when the workspace's Current canvas shows the Contract."""
    current = current_state(db, workspace)
    if current is None:
        return False
    return state_anchors_contract(db, workspace.tenant_id, current, integration_id)


def locked_baseline_anchors_contract(
    db: Session, tenant_id: UUID, integration_id: UUID
) -> bool:
    """True when a *locked* Current baseline in this tenant shows the Contract.

    Quantified over the tenant's workspaces because the canonical Contract routes
    are tenant-scoped (they carry no workspace id), while the predicate itself is
    the workspace-scoped one.
    """
    states = db.scalars(
        select(ArchitectureState).where(
            ArchitectureState.workspace_id.in_(
                select(Workspace.id).where(
                    Workspace.tenant_id == tenant_id, Workspace.deleted_at.is_(None)
                )
            ),
            ArchitectureState.state_type == "current",
            ArchitectureState.deleted_at.is_(None),
        )
    )
    return any(
        state_is_locked(state)
        and state_anchors_contract(db, tenant_id, state, integration_id)
        for state in states
    )


def _contract_locked_detail() -> dict[str, str]:
    return {
        "code": CURRENT_BASELINE_LOCKED,
        "message": (
            "This Contract is part of the locked Current baseline, so it is "
            "read-only. Change it in a Candidate state, or from a workspace "
            "whose Current baseline is still a draft."
        ),
    }


def assert_contract_editable(
    db: Session, workspace: Workspace, integration: Integration
) -> None:
    """Refuse a canonical Contract edit that a locked Current baseline protects."""
    if locked_current_baseline(db, workspace) is None:
        return
    if not contract_anchored_in_current(db, workspace, integration.id):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=_contract_locked_detail()
    )


def assert_contract_editable_for_tenant(
    db: Session, tenant_id: UUID, integration: Integration
) -> None:
    """The same rule for the tenant-scoped canonical Contract routes.

    These routes carry no workspace id, so they ask whether *any* locked Current
    baseline in the tenant shows the Contract. The predicate and the refusal are
    identical to the workspace-scoped guard.
    """
    if not locked_baseline_anchors_contract(db, tenant_id, integration.id):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=_contract_locked_detail()
    )


def current_state(db: Session, workspace: Workspace) -> ArchitectureState | None:
    return db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.state_type == "current",
            ArchitectureState.deleted_at.is_(None),
        )
    )


def node_for_object(state: ArchitectureState, object_id: UUID) -> dict | None:
    for node in state.nodes:
        if str(node.get("object_id")) == str(object_id):
            return node
    return None


def present_in_current(db: Session, workspace: Workspace, object_id: UUID) -> bool:
    current = current_state(db, workspace)
    return current is not None and node_for_object(current, object_id) is not None


def node_overrides(state: ArchitectureState, object_id: UUID) -> dict:
    node = node_for_object(state, object_id)
    if node is None:
        return {}
    overrides = node.get("candidate_overrides") or {}
    return overrides if isinstance(overrides, dict) else {}


def state_members(db: Session, state: ArchitectureState) -> dict[UUID, ArchitectureStateMember]:
    rows = db.scalars(
        select(ArchitectureStateMember).where(
            ArchitectureStateMember.state_id == state.id,
            ArchitectureStateMember.tenant_id == state.workspace_id,
        )
    )
    return {row.object_id: row for row in rows}


def set_member_override(
    db: Session,
    workspace: Workspace,
    state: ArchitectureState,
    object_id: UUID,
    changes: dict,
) -> dict:
    """Upsert an ``included`` state-member whose bounded scalar overrides apply
    to the object in this state. Returns the effective override mapping."""
    member = db.scalar(
        select(ArchitectureStateMember).where(
            ArchitectureStateMember.state_id == state.id,
            ArchitectureStateMember.object_id == object_id,
        )
    )
    overrides = dict(member.property_overrides) if member is not None else {}
    overrides.update(changes)
    if member is None:
        db.add(
            ArchitectureStateMember(
                id=uuid4(),
                tenant_id=workspace.tenant_id,
                workspace_id=workspace.id,
                state_id=state.id,
                object_id=object_id,
                membership="included",
                property_overrides=overrides,
            )
        )
    else:
        member.membership = "included"
        member.property_overrides = overrides
    return overrides


def exclude_member(
    db: Session, workspace: Workspace, state: ArchitectureState, object_id: UUID
) -> None:
    """Mark a canonical child as excluded from this state without deleting it."""
    member = db.scalar(
        select(ArchitectureStateMember).where(
            ArchitectureStateMember.state_id == state.id,
            ArchitectureStateMember.object_id == object_id,
        )
    )
    if member is None:
        db.add(
            ArchitectureStateMember(
                id=uuid4(),
                tenant_id=workspace.tenant_id,
                workspace_id=workspace.id,
                state_id=state.id,
                object_id=object_id,
                membership="excluded",
            )
        )
    else:
        member.membership = "excluded"
