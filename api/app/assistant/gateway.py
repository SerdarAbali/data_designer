"""Assistant turn orchestration.

A turn: persist the user message (done by the route) -> ensure a restricted
OpenCode session -> inject the bounded context envelope when scope changed ->
prompt -> consume the transcript, streaming deltas and tool activity into the
durable event log -> persist the authoritative assistant message.

The gateway never widens the tool surface. Tool calls are dispatched by the
plugin to ``/internal/assistant/tools/call``; this module only records their
bounded summaries from the transcript.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.assistant import service
from app.assistant.context_envelope import build_envelope, envelope_text
from app.assistant.runtime import AssistantRuntimeError, OpenCodeRuntime
from app.auth.dependencies import AuthenticatedUser
from app.models import AssistantConversation, Workspace

MAX_ASSISTANT_CHARS = 24_000
TURN_POLL_SECONDS = 0.4
TURN_MAX_POLLS = 300

_CANCELS: dict[str, threading.Event] = {}
_CANCELS_LOCK = threading.Lock()


def register_cancel(conversation_id: str) -> threading.Event:
    with _CANCELS_LOCK:
        event = threading.Event()
        _CANCELS[conversation_id] = event
        return event


def request_cancel(conversation_id: str) -> bool:
    with _CANCELS_LOCK:
        event = _CANCELS.get(conversation_id)
    if event is None:
        return False
    event.set()
    return True


def clear_cancel(conversation_id: str) -> None:
    with _CANCELS_LOCK:
        _CANCELS.pop(conversation_id, None)


def arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _normalize_messages(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("messages", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def extract_turn(payload: Any) -> tuple[str, list[dict[str, Any]], bool]:
    """Return (assistant_text, tool_parts, finished) from an OpenCode transcript."""
    messages = _normalize_messages(payload)
    text_parts: list[str] = []
    tools: list[dict[str, Any]] = []
    finished = False
    for message in messages:
        if message.get("type") != "assistant":
            continue
        content = message.get("content") or []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and part.get("text"):
                text_parts.append(str(part["text"]))
            elif part.get("type") == "tool":
                state = part.get("state") or {}
                output = ""
                for item in state.get("content") or []:
                    if isinstance(item, dict) and item.get("type") == "text":
                        output += str(item.get("text") or "")
                tools.append(
                    {
                        "call_id": str(part.get("id") or ""),
                        "name": str(part.get("name") or ""),
                        "status": str(state.get("status") or "completed"),
                        "input": state.get("input") or {},
                        "output": output,
                        "error": (state.get("error") or {}).get("message")
                        if isinstance(state.get("error"), dict)
                        else state.get("error"),
                    }
                )
        info = message.get("info") or {}
        if info.get("finish") in ("stop", "tool_calls") or message.get("finish"):
            finished = True
    if not finished and messages:
        # A transcript with no explicit finish marker is treated as complete once
        # no tool part is still running.
        finished = all(tool["status"] != "running" for tool in tools) and bool(text_parts)
    return "".join(text_parts)[:MAX_ASSISTANT_CHARS], tools, finished


def _tool_result_summary(tool: dict[str, Any]) -> dict[str, Any]:
    output = str(tool.get("output") or "")
    return {
        "output_chars": len(output),
        "truncated": False,
        "preview": output[:200],
    }


def _record_tools(
    db: Session, conversation: AssistantConversation, tools: list[dict[str, Any]]
) -> None:
    for tool in tools:
        name = tool.get("name") or "unknown"
        call_id = tool.get("call_id") or arguments_hash({"name": name, "at": time.time()})
        arguments = tool.get("input") if isinstance(tool.get("input"), dict) else {}
        status_value = "completed" if tool.get("status") == "completed" else "error"
        error_code = None
        if tool.get("error"):
            message = str(tool["error"])
            if "not available" in message or "not named" in message:
                error_code = "not_permitted_in_scope"
            else:
                error_code = "tool_error"
        service.record_tool_call(
            db,
            conversation,
            call_id=call_id[:120],
            tool_name=name[:80],
            arguments_summary={
                "keys": sorted(str(key) for key in arguments),
                "bytes": len(json.dumps(arguments, default=str)),
            },
            arguments_hash=arguments_hash(arguments),
            status_value=status_value,
            error_code=error_code,
            duration_ms=None,
            result_summary=_tool_result_summary(tool),
        )


def run_turn(
    db: Session,
    conversation: AssistantConversation,
    user: AuthenticatedUser,
    workspace: Workspace,
    *,
    runtime: OpenCodeRuntime,
    user_text: str,
    cancel: threading.Event | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run one assistant turn. Never raises: failures become a failed message."""
    conversation_id = str(conversation.id)
    cancel = cancel or register_cancel(conversation_id)
    try:
        _run_turn(
            db,
            conversation,
            user,
            workspace,
            runtime=runtime,
            user_text=user_text,
            cancel=cancel,
            sleep=sleep,
        )
    except AssistantRuntimeError as error:
        _fail(db, conversation, error.code.value)
    except Exception:  # noqa: BLE001 - a turn must never crash the worker
        _fail(db, conversation, "turn_failed")
    finally:
        clear_cancel(conversation_id)
        db.commit()


def _create_session(
    runtime: OpenCodeRuntime, conversation: AssistantConversation, db: Session
) -> str | None:
    created = runtime.create_session(
        {"title": conversation.title[:80], "agent": "architecture-assistant"}
    )
    session_id = str((created or {}).get("id") or "")
    if not session_id:
        return None
    conversation.opencode_session_id = session_id
    conversation.opencode_version = getattr(runtime, "version", None)
    db.flush()
    return session_id


def _run_turn(
    db: Session,
    conversation: AssistantConversation,
    user: AuthenticatedUser,
    workspace: Workspace,
    *,
    runtime: OpenCodeRuntime,
    user_text: str,
    cancel: threading.Event,
    sleep: Callable[[float], None],
) -> None:
    service.add_event(db, conversation, "turn.started", {})
    db.commit()

    session_id = conversation.opencode_session_id
    if session_id is None:
        session_id = _create_session(runtime, conversation, db)
        if session_id is None:
            _fail(db, conversation, "session_unavailable")
            return

    envelope = build_envelope(db, user, conversation, workspace)
    runtime.synthetic(session_id, {"text": envelope_text(envelope)})
    db.commit()

    try:
        runtime.prompt(session_id, {"text": user_text})
    except AssistantRuntimeError as error:
        if error.status != 404:
            raise
        # The OpenCode session is a disposable cache: recreate and replay the
        # current bounded envelope once, then retry the prompt.
        session_id = _create_session(runtime, conversation, db)
        if session_id is None:
            _fail(db, conversation, "session_unavailable")
            return
        runtime.synthetic(session_id, {"text": envelope_text(envelope)})
        runtime.prompt(session_id, {"text": user_text})

    last_text = ""
    finished = False
    for _ in range(TURN_MAX_POLLS):
        if cancel.is_set():
            try:
                runtime.interrupt(session_id)
            except AssistantRuntimeError:
                pass
            service.add_message(
                db,
                conversation,
                role="assistant",
                content=last_text,
                status_value="cancelled",
                error_code="cancelled",
            )
            service.add_event(db, conversation, "turn.cancelled", {})
            conversation.status = "active"
            db.commit()
            return
        payload = runtime.messages(session_id)
        text, tools, finished = extract_turn(payload)
        if text and text != last_text:
            last_text = text
            service.add_event(db, conversation, "assistant.delta", {"text": text})
            db.commit()
        if finished:
            if tools:
                _record_tools(db, conversation, tools)
                for tool in tools:
                    service.add_event(
                        db,
                        conversation,
                        "tool.completed",
                        {"tool": tool.get("name"), "status": tool.get("status")},
                    )
            break
        sleep(TURN_POLL_SECONDS)

    assistant_text = last_text[:MAX_ASSISTANT_CHARS]
    service.add_message(
        db,
        conversation,
        role="assistant",
        content=assistant_text,
        status_value="complete" if finished else "failed",
        error_code=None if finished else "turn_timeout",
    )
    service.add_event(
        db,
        conversation,
        "assistant.message.completed" if finished else "turn.failed",
        {"chars": len(assistant_text)} if finished else {"reason": "turn_timeout"},
    )
    db.commit()


def _fail(db: Session, conversation: AssistantConversation, code: str) -> None:
    try:
        service.add_message(
            db, conversation, role="notice", content="", status_value="failed", error_code=code
        )
        service.add_event(db, conversation, "turn.failed", {"reason": code})
        conversation.error_code = code
        db.commit()
    except Exception:  # noqa: BLE001 - best-effort failure recording
        db.rollback()
