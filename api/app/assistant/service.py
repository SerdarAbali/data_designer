"""Assistant conversation persistence.

Application transcripts are authoritative; the OpenCode session is a disposable
cache. Conversations are scoped to one user, tenant, and workspace. Retention is
30 days by default and conversations are soft-deleted and then hard-deleted on
request.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.assistant.context import retention_expiry, scope_fingerprint
from app.auth.dependencies import AuthenticatedUser
from app.models import (
    AssistantConversation,
    AssistantEvent,
    AssistantMessage,
    AssistantToolCall,
    Workspace,
)

MAX_MESSAGES_PER_CONVERSATION = 500
MAX_CONVERSATIONS_PER_WORKSPACE = 20
EVENT_RETENTION_PER_CONVERSATION = 2000


def _now() -> datetime:
    return datetime.now(UTC)


def workspace_enabled(workspace: Workspace) -> bool:
    return bool(getattr(workspace, "assistant_enabled", False))


def create_conversation(
    db: Session,
    user: AuthenticatedUser,
    workspace: Workspace,
    *,
    title: str | None = None,
    state_id: UUID | None = None,
    state_type: str | None = None,
    discipline: str | None = None,
    workbench_view: str | None = None,
    selection_ids: list[UUID] | None = None,
) -> AssistantConversation:
    existing = db.scalar(
        select(func.count())
        .select_from(AssistantConversation)
        .where(
            AssistantConversation.tenant_id == workspace.tenant_id,
            AssistantConversation.workspace_id == workspace.id,
            AssistantConversation.user_id == user.id,
            AssistantConversation.status != "deleted",
        )
    )
    if existing is not None and existing >= MAX_CONVERSATIONS_PER_WORKSPACE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Too many assistant conversations for this workspace",
        )
    conversation = AssistantConversation(
        tenant_id=workspace.tenant_id,
        workspace_id=workspace.id,
        user_id=user.id,
        title=(title or "New conversation")[:200],
        status="active",
        active_state_id=state_id,
        state_type=state_type,
        discipline=discipline,
        workbench_view=workbench_view,
        selection_ids=[str(item) for item in (selection_ids or [])],
        scope_hash=scope_fingerprint(workspace, state_id, list(workspace.disciplines or [])),
        expires_at=retention_expiry(),
    )
    db.add(conversation)
    db.flush()
    return conversation


def list_conversations(
    db: Session, user: AuthenticatedUser, workspace_id: UUID, *, limit: int = 50
) -> list[AssistantConversation]:
    return list(
        db.scalars(
            select(AssistantConversation)
            .where(
                AssistantConversation.workspace_id == workspace_id,
                AssistantConversation.user_id == user.id,
                AssistantConversation.status != "deleted",
            )
            .order_by(AssistantConversation.updated_at.desc())
            .limit(limit)
        )
    )


def get_conversation(
    db: Session, user: AuthenticatedUser, workspace_id: UUID, conversation_id: UUID
) -> AssistantConversation:
    conversation = db.scalar(
        select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.workspace_id == workspace_id,
            AssistantConversation.user_id == user.id,
            AssistantConversation.status != "deleted",
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


def update_scope(
    db: Session,
    conversation: AssistantConversation,
    workspace: Workspace,
    *,
    state_id: UUID | None,
    state_type: str | None,
    discipline: str | None,
    workbench_view: str | None,
    selection_ids: list[UUID] | None,
) -> AssistantConversation:
    conversation.active_state_id = state_id
    conversation.state_type = state_type
    conversation.discipline = discipline
    conversation.workbench_view = workbench_view
    if selection_ids is not None:
        conversation.selection_ids = [str(item) for item in selection_ids]
    conversation.scope_hash = scope_fingerprint(
        workspace, state_id, list(workspace.disciplines or [])
    )
    conversation.updated_at = _now()
    db.flush()
    return conversation


def next_sequence(db: Session, conversation_id: UUID) -> int:
    current = db.scalar(
        select(func.max(AssistantMessage.sequence)).where(
            AssistantMessage.conversation_id == conversation_id
        )
    )
    return (current or 0) + 1


def add_message(
    db: Session,
    conversation: AssistantConversation,
    *,
    role: str,
    content: str,
    status_value: str = "complete",
    error_code: str | None = None,
) -> AssistantMessage:
    message = AssistantMessage(
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        workspace_id=conversation.workspace_id,
        sequence=next_sequence(db, conversation.id),
        role=role,
        content=content,
        status=status_value,
        error_code=error_code,
    )
    db.add(message)
    conversation.message_count = (conversation.message_count or 0) + 1
    conversation.last_message_at = _now()
    conversation.updated_at = _now()
    db.flush()
    return message


def next_event_sequence(db: Session, conversation_id: UUID) -> int:
    current = db.scalar(
        select(func.max(AssistantEvent.sequence)).where(
            AssistantEvent.conversation_id == conversation_id
        )
    )
    return (current or 0) + 1


def add_event(
    db: Session,
    conversation: AssistantConversation,
    event_type: str,
    payload: dict,
) -> AssistantEvent:
    event = AssistantEvent(
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        workspace_id=conversation.workspace_id,
        sequence=next_event_sequence(db, conversation.id),
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    db.flush()
    _prune_events(db, conversation.id)
    return event


def _prune_events(db: Session, conversation_id: UUID) -> None:
    total = db.scalar(
        select(func.count())
        .select_from(AssistantEvent)
        .where(AssistantEvent.conversation_id == conversation_id)
    )
    if total is not None and total > EVENT_RETENTION_PER_CONVERSATION:
        excess = total - EVENT_RETENTION_PER_CONVERSATION
        oldest = list(
            db.scalars(
                select(AssistantEvent.id)
                .where(AssistantEvent.conversation_id == conversation_id)
                .order_by(AssistantEvent.sequence.asc())
                .limit(excess)
            )
        )
        if oldest:
            db.execute(delete(AssistantEvent).where(AssistantEvent.id.in_(oldest)))


def events_after(
    db: Session, conversation_id: UUID, since: int, *, limit: int = 200
) -> list[AssistantEvent]:
    return list(
        db.scalars(
            select(AssistantEvent)
            .where(
                AssistantEvent.conversation_id == conversation_id,
                AssistantEvent.sequence > since,
            )
            .order_by(AssistantEvent.sequence.asc())
            .limit(limit)
        )
    )


def record_tool_call(
    db: Session,
    conversation: AssistantConversation,
    *,
    call_id: str,
    tool_name: str,
    arguments_summary: dict,
    arguments_hash: str,
    status_value: str,
    error_code: str | None,
    duration_ms: int | None,
    result_summary: dict,
) -> AssistantToolCall:
    existing = db.scalar(
        select(AssistantToolCall).where(
            AssistantToolCall.conversation_id == conversation.id,
            AssistantToolCall.call_id == call_id,
        )
    )
    if existing is not None:
        return existing
    call = AssistantToolCall(
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        workspace_id=conversation.workspace_id,
        call_id=call_id,
        tool_name=tool_name,
        arguments_summary=arguments_summary,
        arguments_hash=arguments_hash,
        status=status_value,
        error_code=error_code,
        duration_ms=duration_ms,
        result_summary=result_summary,
        completed_at=_now(),
    )
    db.add(call)
    conversation.tool_call_count = (conversation.tool_call_count or 0) + 1
    conversation.updated_at = _now()
    db.flush()
    return call


def conversation_summary(conversation: AssistantConversation) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "status": conversation.status,
        "state_id": conversation.active_state_id,
        "state_type": conversation.state_type,
        "discipline": conversation.discipline,
        "workbench_view": conversation.workbench_view,
        "message_count": conversation.message_count,
        "tool_call_count": conversation.tool_call_count,
        "last_message_at": conversation.last_message_at,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def conversation_detail(db: Session, conversation: AssistantConversation) -> dict:
    messages = list(
        db.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation.id)
            .order_by(AssistantMessage.sequence.asc())
            .limit(MAX_MESSAGES_PER_CONVERSATION)
        )
    )
    tool_calls = list(
        db.scalars(
            select(AssistantToolCall)
            .where(AssistantToolCall.conversation_id == conversation.id)
            .order_by(AssistantToolCall.created_at.asc())
            .limit(200)
        )
    )
    detail = conversation_summary(conversation)
    detail["messages"] = messages
    detail["tool_calls"] = tool_calls
    return detail


def delete_conversation(db: Session, conversation: AssistantConversation) -> None:
    conversation.status = "deleted"
    conversation.deleted_at = _now()
    db.flush()
    db.execute(
        delete(AssistantToolCall).where(AssistantToolCall.conversation_id == conversation.id)
    )
    db.execute(delete(AssistantMessage).where(AssistantMessage.conversation_id == conversation.id))
    db.execute(delete(AssistantEvent).where(AssistantEvent.conversation_id == conversation.id))
    db.execute(delete(AssistantConversation).where(AssistantConversation.id == conversation.id))


def prune_expired(db: Session, *, now: datetime | None = None) -> int:
    moment = now or _now()
    expired = list(
        db.scalars(
            select(AssistantConversation).where(
                AssistantConversation.expires_at.is_not(None),
                AssistantConversation.expires_at <= moment,
            )
        )
    )
    for conversation in expired:
        delete_conversation(db, conversation)
    return len(expired)
