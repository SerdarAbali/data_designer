"""Shared Current/Candidate/Target state-isolation helpers.

The Enterprise, Information and Solution modules all need the same primitives:
resolve a state, refuse writes against the read-only Current state, locate the
canvas node for an object, read bounded scalar overrides, and upsert child
state-membership rows. Keeping them here means the editing rules are identical
across disciplines and can be documented once (see docs/current-vs-candidate.md).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArchitectureState, ArchitectureStateMember, Workspace


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


def assert_writable(state: ArchitectureState) -> None:
    """The Current state is always read-only; enrich it through include-objects."""
    if state.state_type == "current":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Current architecture state is read-only",
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
