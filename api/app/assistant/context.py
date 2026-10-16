"""Conversation scope resolution.

Identity flows strictly one way:

    OpenCode session id
      -> assistant conversation row
      -> authenticated user
      -> tenant
      -> workspace
      -> enabled disciplines
      -> active architecture state

The model never supplies or overrides scope. If a scope cannot be resolved, the
caller fails closed (no tools offered, no dispatch).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.tools import allowed_tool_names
from app.models import AssistantConversation, Workspace

#: How long a conversation transcript is retained by default.
DEFAULT_RETENTION_DAYS = 30


def resolve_conversation_by_session(
    db: Session, opencode_session_id: str
) -> AssistantConversation | None:
    if not opencode_session_id:
        return None
    conversation = db.scalar(
        select(AssistantConversation).where(
            AssistantConversation.opencode_session_id == opencode_session_id
        )
    )
    if conversation is None or conversation.deleted_at is not None:
        return None
    if conversation.status == "deleted":
        return None
    return conversation


def resolve_scope(
    db: Session, opencode_session_id: str
) -> tuple[AssistantConversation, Workspace, list[str]] | None:
    """Resolve conversation, workspace, and allowed tool names. None => fail closed."""
    conversation = resolve_conversation_by_session(db, opencode_session_id)
    if conversation is None:
        return None
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == conversation.workspace_id,
            Workspace.deleted_at.is_(None),
        )
    )
    if workspace is None:
        return None
    disciplines = list(workspace.disciplines or [])
    allowed = allowed_tool_names(disciplines, conversation.state_type or "current")
    return conversation, workspace, allowed


def scope_fingerprint(
    workspace: Workspace, state_id: object | None, disciplines: list[str]
) -> str:
    payload = "|".join(
        [
            str(workspace.id),
            str(state_id) if state_id else "none",
            ",".join(sorted(disciplines or [])),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def retention_expiry(now: datetime | None = None, days: int = DEFAULT_RETENTION_DAYS) -> datetime:
    from datetime import timedelta

    base = now or datetime.now(UTC)
    return base + timedelta(days=days)
