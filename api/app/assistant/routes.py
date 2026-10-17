"""Architecture Assistant routes.

Three surfaces:

* ``/api/assistant`` — the application-owned runtime status (Slice B).
* ``/api/workspaces/{workspace_id}/assistant`` — cookie + CSRF authenticated
  conversations, messages, scope, cancellation, deletion, and SSE streaming.
* ``/internal/assistant`` — plugin-only tool manifest, scope, and dispatch,
  guarded by a static service token. Never reachable from the browser.

The model may read and explain the architecture. There is no proposal,
validation, approval, apply, undo, or write route anywhere on this surface.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant import gateway, service, tools
from app.assistant import runtime as runtime_module
from app.assistant.probe import AssistantRuntimeStatus, get_assistant_status
from app.assistant.schemas import (
    AssistantSettingsResponse,
    AssistantSettingsUpdate,
    AssistantStatusResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    InternalScopeResponse,
    InternalToolCallRequest,
    InternalToolCallResponse,
    MessageCreate,
    MessageResponse,
    ProposalEventRequest,
    ScopeUpdate,
    ToolManifestResponse,
    WorkspaceAssistantSettings,
)
from app.assistant.settings import get_assistant_settings
from app.auth.dependencies import (
    AuthenticatedUser,
    get_auth_session,
    get_current_user,
    require_csrf,
)
from app.db import SessionLocal, get_session
from app.helper_actions.context import resolve_context
from app.models import ArchitectureState, AuthSession, Tenant, Workspace

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
workspace_router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/assistant", tags=["assistant"]
)
internal_router = APIRouter(prefix="/internal/assistant", tags=["assistant-internal"])

SSE_HEARTBEAT_SECONDS = 15.0


def _workspace(db: Session, user: AuthenticatedUser, workspace_id: UUID) -> Workspace:
    return resolve_context(db, user, workspace_id).workspace


def _require_ready(status_dep: AssistantRuntimeStatus) -> None:
    result = status_dep.refresh()
    if not result.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": result.reason_code, "message": "Assistant runtime is not ready"},
        )


def _is_owner(db: Session, user: AuthenticatedUser, workspace: Workspace) -> bool:
    tenant = db.get(Tenant, workspace.tenant_id)
    return tenant is not None and tenant.owner_id == user.id


def _require_privacy(db: Session, workspace: Workspace) -> None:
    """Refuse when the configured provider may not be used for this tenant's data."""
    from app.assistant import model_settings

    settings = model_settings.get_settings(db, workspace.tenant_id)
    allowed, reason = model_settings.privacy_decision(settings)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": reason, "message": "The configured provider is not permitted"},
        )


def _resolve_state(
    db: Session, workspace: Workspace, state_id: UUID | None
) -> ArchitectureState | None:
    if state_id is None:
        return db.scalar(
            select(ArchitectureState)
            .where(
                ArchitectureState.workspace_id == workspace.id,
                ArchitectureState.state_type == "current",
                ArchitectureState.deleted_at.is_(None),
            )
            .order_by(ArchitectureState.created_at.asc())
        )
    return db.scalar(
        select(ArchitectureState).where(
            ArchitectureState.id == state_id,
            ArchitectureState.workspace_id == workspace.id,
            ArchitectureState.deleted_at.is_(None),
        )
    )


# -- application-owned runtime status --------------------------------------


@router.get("/status")
def assistant_status(
    _user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    status_dep: AssistantRuntimeStatus = Depends(get_assistant_status),  # noqa: B008
) -> dict[str, Any]:
    return status_dep.public_snapshot()


@workspace_router.get("/status", response_model=AssistantStatusResponse)
def workspace_assistant_status(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
    status_dep: AssistantRuntimeStatus = Depends(get_assistant_status),  # noqa: B008
) -> AssistantStatusResponse:
    workspace = _workspace(db, user, workspace_id)
    snapshot = status_dep.public_snapshot()
    snapshot["workspace_enabled"] = service.workspace_enabled(workspace)
    snapshot["is_owner"] = _is_owner(db, user, workspace)
    return AssistantStatusResponse(**snapshot)


# -- provider/model settings (tenant owner only) ---------------------------


@workspace_router.get(
    "/settings", response_model=AssistantSettingsResponse, response_model_exclude_none=True
)
def get_workspace_assistant_settings(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> AssistantSettingsResponse:
    from app.assistant import model_settings

    workspace = _workspace(db, user, workspace_id)
    owner = _is_owner(db, user, workspace)
    settings = model_settings.get_settings(db, workspace.tenant_id)
    payload = model_settings.public_settings(settings, owner=owner)
    payload["workspace_enabled"] = service.workspace_enabled(workspace)
    payload["is_owner"] = owner
    return AssistantSettingsResponse(**payload)


@workspace_router.put(
    "/settings/model", response_model=AssistantSettingsResponse, response_model_exclude_none=True
)
def update_assistant_settings(
    workspace_id: UUID,
    payload: AssistantSettingsUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> AssistantSettingsResponse:
    from app.assistant import model_settings

    require_csrf(request, auth_session)
    workspace = _workspace(db, user, workspace_id)
    if not _is_owner(db, user, workspace):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can change assistant settings",
        )
    settings = model_settings.get_settings(db, workspace.tenant_id)
    model_settings.apply_owner_update(
        settings, payload.model_dump(exclude_unset=True), updated_by=user.id
    )
    db.commit()

    # Provider/model changes dispose affected sessions so future turns cannot
    # silently continue with the previous provider. Conversation history is kept.
    if payload.model_dump(exclude_unset=True).keys() & {"provider", "model_id", "model_variant"}:
        _dispose_tenant_sessions(db, workspace.tenant_id)

    response = model_settings.public_settings(settings, owner=True)
    response["workspace_enabled"] = service.workspace_enabled(workspace)
    response["is_owner"] = True
    return AssistantSettingsResponse(**response)


def _dispose_tenant_sessions(db: Session, tenant_id: UUID) -> None:
    from app.models import AssistantConversation

    conversations = list(
        db.scalars(
            select(AssistantConversation).where(
                AssistantConversation.tenant_id == tenant_id,
                AssistantConversation.opencode_session_id.is_not(None),
            )
        )
    )
    if not conversations:
        return
    runtime = None
    try:
        runtime = runtime_module.build_runtime()
    except Exception:  # noqa: BLE001 - disposal is best effort
        runtime = None
    for conversation in conversations:
        session_id = conversation.opencode_session_id
        if runtime is not None and session_id:
            try:
                runtime.delete_session(session_id)
            except Exception:  # noqa: BLE001
                pass
        conversation.opencode_session_id = None
    if runtime is not None:
        runtime.close()
    db.commit()


# -- workspace opt-in (tenant owner only) ----------------------------------


@workspace_router.put("/settings", response_model=WorkspaceAssistantSettings)
def update_workspace_settings(
    workspace_id: UUID,
    payload: WorkspaceAssistantSettings,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> WorkspaceAssistantSettings:
    require_csrf(request, auth_session)
    workspace = _workspace(db, user, workspace_id)
    tenant = db.get(Tenant, workspace.tenant_id)
    if tenant is None or tenant.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can change assistant settings",
        )
    workspace.assistant_enabled = payload.assistant_enabled
    db.commit()
    return WorkspaceAssistantSettings(assistant_enabled=workspace.assistant_enabled)


# -- conversations ---------------------------------------------------------


@workspace_router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> list[dict[str, Any]]:
    _workspace(db, user, workspace_id)
    conversations = service.list_conversations(db, user, workspace_id)
    return [service.conversation_summary(item) for item in conversations]


@workspace_router.post(
    "/conversations", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    workspace_id: UUID,
    payload: ConversationCreate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
    status_dep: AssistantRuntimeStatus = Depends(get_assistant_status),  # noqa: B008
) -> dict[str, Any]:
    require_csrf(request, auth_session)
    workspace = _workspace(db, user, workspace_id)
    if not service.workspace_enabled(workspace):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The assistant is not enabled for this workspace",
        )
    _require_privacy(db, workspace)
    _require_ready(status_dep)
    state = _resolve_state(db, workspace, payload.state_id)
    conversation = service.create_conversation(
        db,
        user,
        workspace,
        title=payload.title,
        state_id=state.id if state else None,
        state_type=state.state_type if state else None,
        discipline=payload.discipline,
        workbench_view=payload.workbench_view,
        selection_ids=payload.selection_ids,
    )
    db.commit()
    return service.conversation_summary(conversation)


@workspace_router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    workspace_id: UUID,
    conversation_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _workspace(db, user, workspace_id)
    conversation = service.get_conversation(db, user, workspace_id, conversation_id)
    return service.conversation_detail(db, conversation)


@workspace_router.post(
    "/conversations/{conversation_id}/scope", response_model=ConversationSummary
)
def update_scope(
    workspace_id: UUID,
    conversation_id: UUID,
    payload: ScopeUpdate,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    require_csrf(request, auth_session)
    workspace = _workspace(db, user, workspace_id)
    conversation = service.get_conversation(db, user, workspace_id, conversation_id)
    state = _resolve_state(db, workspace, payload.state_id)
    service.update_scope(
        db,
        conversation,
        workspace,
        state_id=state.id if state else None,
        state_type=state.state_type if state else None,
        discipline=payload.discipline,
        workbench_view=payload.workbench_view,
        selection_ids=payload.selection_ids,
    )
    db.commit()
    return service.conversation_summary(conversation)


@workspace_router.delete(
    "/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_conversation(
    workspace_id: UUID,
    conversation_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    require_csrf(request, auth_session)
    _workspace(db, user, workspace_id)
    conversation = service.get_conversation(db, user, workspace_id, conversation_id)
    session_id = conversation.opencode_session_id
    if session_id:
        try:
            runtime = runtime_module.build_runtime()
            try:
                runtime.delete_session(session_id)
            finally:
                runtime.close()
        except Exception:  # noqa: BLE001 - disposal is best effort
            pass
    service.delete_conversation(db, conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- messages, cancel, retry, events ---------------------------------------


def _run_turn_task(conversation_id: str, user_id: str, workspace_id: str, content: str) -> None:
    from app.assistant import limits
    from app.models import AssistantConversation, User

    try:
        with SessionLocal() as db:
            conversation = db.get(AssistantConversation, UUID(conversation_id))
            workspace = db.get(Workspace, UUID(workspace_id))
            if conversation is None or workspace is None:
                return
            user_row = db.get(User, UUID(user_id))
            if user_row is None:
                return
            user = AuthenticatedUser(
                id=user_row.id,
                tenant_id=workspace.tenant_id,
                email=user_row.email,
                tenant_name=workspace.name,
            )
            runtime = runtime_module.build_runtime()
            try:
                gateway.run_turn(
                    db, conversation, user, workspace, runtime=runtime, user_text=content
                )
            finally:
                runtime.close()
    finally:
        limits.limiter.release(
            conversation_id=conversation_id, user_id=user_id, workspace_id=workspace_id
        )


def _acquire_turn_slot(
    user: AuthenticatedUser, workspace: Workspace, conversation_id: UUID
) -> None:
    from app.assistant import limits

    try:
        limits.limiter.check_turn_rate(str(user.id))
        limits.limiter.acquire(
            conversation_id=str(conversation_id),
            user_id=str(user.id),
            workspace_id=str(workspace.id),
        )
    except limits.LimitExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": error.code, "message": "Assistant limit reached"},
            headers={"Retry-After": str(error.retry_after or 5)},
        ) from None


@workspace_router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    workspace_id: UUID,
    conversation_id: UUID,
    payload: MessageCreate,
    background: BackgroundTasks,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
    status_dep: AssistantRuntimeStatus = Depends(get_assistant_status),  # noqa: B008
) -> Any:
    require_csrf(request, auth_session)
    workspace = _workspace(db, user, workspace_id)
    if not service.workspace_enabled(workspace):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The assistant is not enabled for this workspace",
        )
    _require_privacy(db, workspace)
    _require_ready(status_dep)
    conversation = service.get_conversation(db, user, workspace_id, conversation_id)
    if conversation.status == "cancelling":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A turn is already being cancelled"
        )
    _acquire_turn_slot(user, workspace, conversation.id)
    message = service.add_message(
        db, conversation, role="user", content=payload.content, status_value="complete"
    )
    db.commit()
    background.add_task(
        _run_turn_task, str(conversation.id), str(user.id), str(workspace.id), payload.content
    )
    return MessageResponse.model_validate(message)


@workspace_router.post(
    "/conversations/{conversation_id}/messages/{message_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_message(
    workspace_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    background: BackgroundTasks,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
    status_dep: AssistantRuntimeStatus = Depends(get_assistant_status),  # noqa: B008
) -> dict[str, Any]:
    require_csrf(request, auth_session)
    workspace = _workspace(db, user, workspace_id)
    _require_ready(status_dep)
    conversation = service.get_conversation(db, user, workspace_id, conversation_id)
    from app.models import AssistantMessage

    message = db.scalar(
        select(AssistantMessage).where(
            AssistantMessage.id == message_id,
            AssistantMessage.conversation_id == conversation.id,
            AssistantMessage.role == "user",
        )
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    _acquire_turn_slot(user, workspace, conversation.id)
    background.add_task(
        _run_turn_task, str(conversation.id), str(user.id), str(workspace.id), message.content
    )
    return {"status": "scheduled"}


@workspace_router.post("/conversations/{conversation_id}/cancel")
def cancel_turn(
    workspace_id: UUID,
    conversation_id: UUID,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    require_csrf(request, auth_session)
    _workspace(db, user, workspace_id)
    conversation = service.get_conversation(db, user, workspace_id, conversation_id)
    gateway.request_cancel(str(conversation.id))
    session_id = conversation.opencode_session_id
    if session_id:
        try:
            runtime = runtime_module.build_runtime()
            try:
                runtime.interrupt(session_id)
            finally:
                runtime.close()
        except Exception:  # noqa: BLE001 - best effort
            pass
    return {"status": "cancelling"}


@workspace_router.get("/conversations/{conversation_id}/events")
def stream_events(
    workspace_id: UUID,
    conversation_id: UUID,
    since: int = 0,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> StreamingResponse:
    _workspace(db, user, workspace_id)
    service.get_conversation(db, user, workspace_id, conversation_id)
    return StreamingResponse(
        event_stream(str(conversation_id), since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def event_stream(
    conversation_id: str, since: int, *, max_idle_seconds: float = 120.0
) -> Iterator[str]:
    """Durable SSE: read the sequenced event log by cursor. Worker-safe."""
    cursor = since
    idle_seconds = 0.0
    while idle_seconds < max_idle_seconds:
        events = []
        with SessionLocal() as db:
            events = service.events_after(db, UUID(conversation_id), cursor)
            for event in events:
                cursor = event.sequence
                body = {
                    "type": event.event_type,
                    "seq": event.sequence,
                    "at": event.created_at.isoformat(),
                    **(event.payload or {}),
                }
                yield f"id: {event.sequence}\ndata: {json.dumps(body)}\n\n"
        if events:
            idle_seconds = 0.0
        else:
            time.sleep(0.5)
            idle_seconds += 0.5
            if int(idle_seconds) % int(SSE_HEARTBEAT_SECONDS) == 0:
                yield ": heartbeat\n\n"


# -- proposal lifecycle events ---------------------------------------------


@workspace_router.post("/conversations/{conversation_id}/proposal-events")
def record_proposal_event(
    workspace_id: UUID,
    conversation_id: UUID,
    payload: ProposalEventRequest,
    request: Request,
    auth_session: AuthSession = Depends(get_auth_session),  # noqa: B008
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Record a bounded proposal lifecycle event for the originating conversation.

    The browser reports the user-driven action; the backend derives the bounded
    summary from the authoritative helper change set. Full operations and
    payloads are never stored in conversation events.
    """
    require_csrf(request, auth_session)
    workspace = _workspace(db, user, workspace_id)
    conversation = service.get_conversation(db, user, workspace_id, conversation_id)

    from app.models import AssistantToolCall, HelperChangeSet

    change_set = db.scalar(
        select(HelperChangeSet).where(
            HelperChangeSet.id == payload.change_set_id,
            HelperChangeSet.workspace_id == workspace.id,
            HelperChangeSet.tenant_id == workspace.tenant_id,
        )
    )
    if change_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change set not found")
    referenced = db.scalar(
        select(AssistantToolCall.id).where(
            AssistantToolCall.conversation_id == conversation.id,
            AssistantToolCall.change_set_id == change_set.id,
        )
    )
    if referenced is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This conversation does not reference the change set",
        )

    apply_summary = change_set.apply_summary or {}
    undo_summary = change_set.undo_summary or {}
    summary: dict[str, Any] = {
        "change_set_id": str(change_set.id),
        "status": change_set.status,
        "proposal_hash_prefix": (change_set.proposal_hash or "")[:12],
        "operation_count": (change_set.validation_summary or {}).get("operations"),
        "applied_operation_count": apply_summary.get("applied_operation_count"),
        "undone_operation_count": undo_summary.get("undone_operation_count"),
    }
    if payload.reason_code:
        summary["reason_code"] = payload.reason_code
    service.add_event(
        db,
        conversation,
        f"proposal.{payload.action}",
        {key: value for key, value in summary.items() if value is not None},
    )
    db.commit()
    return {"status": "recorded"}


# -- tool manifest ---------------------------------------------------------


@workspace_router.get("/tools/manifest", response_model=ToolManifestResponse)
def tool_manifest(
    workspace_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> ToolManifestResponse:
    workspace = _workspace(db, user, workspace_id)
    disciplines = list(workspace.disciplines or [])
    state = _resolve_state(db, workspace, None)
    state_type = state.state_type if state else "current"
    return ToolManifestResponse(
        tools=tools.tool_manifest(disciplines, state_type),
        scope={"disciplines": disciplines, "state_type": state_type},
    )


# -- internal plugin surface (service token only) --------------------------


def _require_service_token(header_value: str | None) -> None:
    settings = get_assistant_settings()
    tokens = settings.service_tokens()
    if not tokens:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised")
    if not header_value or not any(
        secrets.compare_digest(header_value, token) for token in tokens
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised")


MAX_INTERNAL_REQUEST_BYTES = 64 * 1024


def _internal_rate_limited(error_code: str, retry_after: int | None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": error_code, "message": "Internal dispatch rate limited"},
        headers={"Retry-After": str(retry_after or 5)},
    )


def _guard_internal_request(
    request: Request,
    header_value: str | None,
) -> str:
    """Hardened internal-dispatch guard. Returns a correlation id.

    The static service token is mandatory. Client-supplied forwarded-IP headers
    are never trusted for authorization.
    """
    from app.assistant import limits, redaction

    correlation_id = redaction.correlation_id()
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="JSON required"
            )
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) > MAX_INTERNAL_REQUEST_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request too large",
                    )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length"
                ) from None
    _require_service_token(header_value)
    try:
        limits.limiter.check_internal_dispatch_rate()
    except limits.LimitExceeded as error:
        raise _internal_rate_limited(error.code, error.retry_after) from None
    return correlation_id


def internal_guard(
    request: Request,
    x_assistant_service_token: str | None = Header(default=None),
) -> str:
    """FastAPI dependency: hardened internal-dispatch guard, runs before body parsing."""
    return _guard_internal_request(request, x_assistant_service_token)


@internal_router.get("/manifest")
def internal_manifest(
    response: Response,
    correlation_id: str = Depends(internal_guard),  # noqa: B008
) -> dict[str, Any]:
    response.headers["X-Assistant-Correlation-Id"] = correlation_id
    return {"tools": tools.plugin_manifest()}


@internal_router.get("/scope", response_model=InternalScopeResponse)
def internal_scope(
    session: str,
    response: Response,
    correlation_id: str = Depends(internal_guard),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InternalScopeResponse:
    response.headers["X-Assistant-Correlation-Id"] = correlation_id
    from app.assistant import limits
    from app.assistant.context import resolve_scope

    try:
        limits.limiter.check_scope_rate(session)
    except limits.LimitExceeded as error:
        raise _internal_rate_limited(error.code, error.retry_after) from None
    resolved = resolve_scope(db, session)
    if resolved is None:
        return InternalScopeResponse(status="denied", tools=[])
    _conversation, _workspace, allowed = resolved
    return InternalScopeResponse(status="ok", tools=allowed)


@internal_router.post("/call", response_model=InternalToolCallResponse)
def internal_call(
    payload: InternalToolCallRequest,
    response: Response,
    correlation_id: str = Depends(internal_guard),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> InternalToolCallResponse:
    response.headers["X-Assistant-Correlation-Id"] = correlation_id
    from app.assistant import limits
    from app.assistant.context import resolve_conversation_by_session
    from app.models import User

    conversation = resolve_conversation_by_session(db, payload.opencode_session_id)
    if conversation is None:
        return InternalToolCallResponse(status="denied", error_code="unknown_session")
    try:
        limits.limiter.check_tool_rate(
            conversation_id=str(conversation.id),
            user_id=str(conversation.user_id),
            workspace_id=str(conversation.workspace_id),
        )
    except limits.LimitExceeded as error:
        raise _internal_rate_limited(error.code, error.retry_after) from None
    user_row = db.get(User, conversation.user_id)
    if user_row is None:
        return InternalToolCallResponse(status="denied", error_code="unknown_session")
    user = AuthenticatedUser(
        id=user_row.id,
        tenant_id=conversation.tenant_id,
        email=user_row.email,
        tenant_name="",
    )
    outcome = tools.dispatch_tool(db, user, conversation, payload.tool, payload.arguments)
    return InternalToolCallResponse(**outcome)
