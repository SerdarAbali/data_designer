"""Narrow internal API for deterministic helper actions (Slice 1).

Read helpers and proposal helpers are separate from the approval/apply steps.
There is no generic executor, no ORM/SQL exposure, and no arbitrary function
name: helper names come from a closed allowlist.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import get_session
from app.helper_actions import apply, reads, resolution, service
from app.helper_actions.context import HelperContext, resolve_context
from app.helper_actions.schemas import (
    ApplyResponse,
    ChangeSetResponse,
    ChangeSetStatusResponse,
    ReadEnvelope,
    ReadRequest,
    UndoResponse,
)
from app.models import AuthSession

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/helper-actions",
    tags=["helper-actions"],
)


def _detail_code(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("code", "rejected"))
    return "rejected"


def _audit_rejection(
    ctx: HelperContext,
    event_type: str,
    *,
    summary: dict[str, Any] | None = None,
    state_id: UUID | None = None,
    change_set_id: UUID | None = None,
) -> None:
    service.add_audit(
        ctx.db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        event_type=event_type,
        change_set_id=change_set_id,
        state_id=state_id,
        summary=summary or {},
    )
    ctx.db.commit()


def _coerce_state_id(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


@router.post("/reads/{helper_name}", response_model=ReadEnvelope)
def invoke_read(
    workspace_id: UUID,
    helper_name: str,
    payload: ReadRequest,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ReadEnvelope:
    ctx = resolve_context(db, user, workspace_id)
    return reads.run_read(ctx, helper_name, payload)


@router.post(
    "/proposals/{helper_name}",
    response_model=ChangeSetResponse,
    status_code=status.HTTP_201_CREATED,
)
def invoke_proposal(
    workspace_id: UUID,
    helper_name: str,
    payload: dict[str, Any],
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ChangeSetResponse:
    require_csrf(request, auth_session)
    ctx = resolve_context(db, user, workspace_id)
    model = service.PROPOSAL_REQUEST_MODELS.get(helper_name)
    if model is None:
        _audit_rejection(ctx, "proposal_rejected", summary={"code": "unknown_helper"})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown proposal helper")
    try:
        parsed = model.model_validate(payload)
    except ValidationError as exc:
        _audit_rejection(
            ctx,
            "proposal_rejected",
            summary={"code": "invalid_payload", "helper": helper_name},
            state_id=_coerce_state_id(payload.get("state_id")),
        )
        raise RequestValidationError(exc.errors()) from exc
    try:
        change_set = service.run_proposal(ctx, helper_name, parsed)
    except HTTPException as exc:
        _audit_rejection(
            ctx,
            "proposal_rejected",
            summary={"code": _detail_code(exc), "helper": helper_name},
            state_id=parsed.state_id,
        )
        raise
    return service.to_response(ctx, change_set)


@router.get("/change-sets/{change_set_id}", response_model=ChangeSetResponse)
def get_change_set(
    workspace_id: UUID,
    change_set_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ChangeSetResponse:
    ctx = resolve_context(db, user, workspace_id)
    change_set = service.get_change_set(ctx, change_set_id)
    service.sync_staleness(ctx, change_set)
    return service.to_response(ctx, change_set)


@router.get("/change-sets/{change_set_id}/status", response_model=ChangeSetStatusResponse)
def get_change_set_status(
    workspace_id: UUID,
    change_set_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ChangeSetStatusResponse:
    ctx = resolve_context(db, user, workspace_id)
    change_set = service.get_change_set(ctx, change_set_id)
    service.sync_staleness(ctx, change_set)
    operations = service.load_operations(db, change_set.id)
    counts: dict[str, int] = {}
    for op in operations:
        counts[op.validation_status] = counts.get(op.validation_status, 0) + 1
    current_hash = service.compute_proposal_hash(change_set, operations)
    issues = (change_set.validation_summary or {}).get("issues", [])
    return ChangeSetStatusResponse(
        id=change_set.id,
        workspace_id=change_set.workspace_id,
        status=change_set.status,
        proposal_hash=change_set.proposal_hash,
        current_hash=current_hash,
        validated_at=change_set.validated_at,
        approved_by=change_set.approved_by,
        approved_at=change_set.approved_at,
        operation_counts=counts,
        issues=issues,
    )


@router.post("/change-sets/{change_set_id}/resolve", response_model=ChangeSetResponse)
def resolve_change_set_endpoint(
    workspace_id: UUID,
    change_set_id: UUID,
    payload: resolution.ResolutionRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ChangeSetResponse:
    require_csrf(request, auth_session)
    ctx = resolve_context(db, user, workspace_id)
    change_set = service.get_change_set(ctx, change_set_id)
    resolution.resolve_change_set(ctx, change_set, payload)
    return service.to_response(ctx, change_set)


@router.post("/change-sets/{change_set_id}/validate", response_model=ChangeSetResponse)
def validate_change_set(
    workspace_id: UUID,
    change_set_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ChangeSetResponse:
    require_csrf(request, auth_session)
    ctx = resolve_context(db, user, workspace_id)
    change_set = service.get_change_set(ctx, change_set_id)
    service.validate_change_set(ctx, change_set)
    return service.to_response(ctx, change_set)


@router.post("/change-sets/{change_set_id}/approve", response_model=ChangeSetResponse)
def approve_change_set(
    workspace_id: UUID,
    change_set_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ChangeSetResponse:
    require_csrf(request, auth_session)
    ctx = resolve_context(db, user, workspace_id)
    change_set = service.get_change_set(ctx, change_set_id)
    try:
        service.approve_change_set(ctx, change_set)
    except HTTPException as exc:
        _audit_rejection(
            ctx,
            "approval_rejected",
            summary={"code": _detail_code(exc)},
            state_id=change_set.state_id,
            change_set_id=change_set.id,
        )
        raise
    return service.to_response(ctx, change_set)


@router.post("/change-sets/{change_set_id}/apply", response_model=ApplyResponse)
def apply_change_set(
    workspace_id: UUID,
    change_set_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ApplyResponse:
    require_csrf(request, auth_session)
    ctx = resolve_context(db, user, workspace_id)
    change_set = service.get_change_set(ctx, change_set_id)
    result = apply.apply_change_set(ctx, change_set)
    return ApplyResponse(change_set=service.to_response(ctx, change_set), **result)


@router.post("/change-sets/{change_set_id}/undo", response_model=UndoResponse)
def undo_change_set(
    workspace_id: UUID,
    change_set_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> UndoResponse:
    require_csrf(request, auth_session)
    ctx = resolve_context(db, user, workspace_id)
    change_set = service.get_change_set(ctx, change_set_id)
    result = apply.undo_change_set(ctx, change_set)
    return UndoResponse(change_set=service.to_response(ctx, change_set), **result)
