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
from uuid import UUID

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


#: Finish reasons that mean the runtime is still executing tools and will
#: continue the same turn. Every other explicit finish reason is terminal.
_IN_PROGRESS_FINISH_REASONS = frozenset({"tool_calls", "tool-calls"})

#: Safe, bounded codes for provider/model failures. The provider's own message
#: body is never persisted or streamed: it can echo credentials or upstream
#: payloads, so only the failure *class* is retained.
_PROVIDER_ERROR_CODES = {
    "provider.auth": "provider_auth",
    "provider.quota": "provider_quota",
    "provider.ratelimit": "provider_rate_limited",
    "provider.timeout": "provider_timeout",
    "provider.unavailable": "provider_unavailable",
    "provider.error": "provider_error",
}


def _finish_reason(message: dict[str, Any]) -> str:
    info = message.get("info") or {}
    return str(message.get("finish") or info.get("finish") or "").lower()


def _safe_turn_error(message: dict[str, Any]) -> str | None:
    """Map a terminal OpenCode failure to a safe, bounded error code."""
    error = message.get("error")
    kind = ""
    if isinstance(error, dict):
        kind = str(error.get("type") or error.get("name") or "").lower()
    if kind in _PROVIDER_ERROR_CODES:
        return _PROVIDER_ERROR_CODES[kind]
    if kind.startswith("model"):
        return "model_unavailable"
    if kind.startswith("provider"):
        return "provider_error"
    finish = _finish_reason(message)
    if kind or finish == "error":
        return "provider_error"
    if finish == "content-filter":
        return "content_filtered"
    return None


def extract_turn(
    payload: Any, *, exclude_ids: set[str] | None = None
) -> tuple[str, list[dict[str, Any]], bool, str | None]:
    """Return (assistant_text, tool_parts, finished, error_code) from a transcript.

    ``exclude_ids`` are message ids that predate the current turn (the transcript
    is a session-wide cache, not a per-turn log).
    """
    messages = _normalize_messages(payload)
    if exclude_ids:
        messages = [
            message for message in messages if str(message.get("id") or "") not in exclude_ids
        ]
    # The runtime returns the transcript newest-first; reorder chronologically so
    # deltas stream and text accumulates in the order the model produced it.
    ordered = sorted(
        messages, key=lambda message: float((message.get("time") or {}).get("created") or 0)
    )
    # The injected context envelope can itself draw a model reply, and the
    # runtime only enqueues the prompt's user message once that reply finishes.
    # Until the user message lands there is no current turn to read.
    user_positions = [
        index for index, message in enumerate(ordered) if message.get("type") == "user"
    ]
    if not user_positions:
        return "", [], False, None
    ordered = ordered[user_positions[-1] + 1 :]
    text_parts: list[str] = []
    tools: list[dict[str, Any]] = []
    finished = False
    error_code: str | None = None
    saw_finish = False
    for message in ordered:
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
        finish = _finish_reason(message)
        if not finish:
            continue
        # Only the most recent assistant message decides the turn state: a
        # ``tool-calls`` finish means more of the turn is still coming.
        saw_finish = True
        finished = finish not in _IN_PROGRESS_FINISH_REASONS
        error_code = _safe_turn_error(message) if finished else None
    if not finished and not saw_finish and ordered:
        # A transcript with no explicit finish marker is treated as complete once
        # no tool part is still running.
        finished = all(tool["status"] != "running" for tool in tools) and bool(text_parts)
    return "".join(text_parts)[:MAX_ASSISTANT_CHARS], tools, finished, error_code


def _tool_result_summary(tool: dict[str, Any]) -> dict[str, Any]:
    output = str(tool.get("output") or "")
    return {
        "output_chars": len(output),
        "truncated": False,
        "preview": output[:200],
    }


def _extract_change_set_id(tool: dict[str, Any]) -> str | None:
    output = str(tool.get("output") or "")
    if not output:
        return None
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        raw = parsed.get("change_set_id")
        if raw:
            return str(raw)
    return None


#: Bounded, safe tool-failure codes. Tool output is untrusted and may carry
#: provider or transport text, so only a known class is ever persisted.
_SAFE_TOOL_ERROR_CODES: dict[str, str] = {
    "backend_unreachable": "backend_unreachable",
    "rate_limited": "rate_limited",
    "session_rate_limited": "rate_limited",
    "scope_rate_limited": "rate_limited",
    "tool_rate_limited": "rate_limited",
    "internal_rate_limited": "rate_limited",
    "tool_not_in_scope": "not_permitted_in_scope",
    "unknown_tool": "not_permitted_in_scope",
    "unknown_session": "not_permitted_in_scope",
    "scope_override": "not_permitted_in_scope",
    "not_permitted_in_scope": "not_permitted_in_scope",
    "invalid_arguments": "invalid_arguments",
    "oversized_arguments": "invalid_arguments",
    "no_active_state": "no_active_state",
    "change_set_not_found": "change_set_not_found",
    "proposal_rejected": "proposal_rejected",
    "validation_rejected": "validation_rejected",
    "read_failed": "read_failed",
    "proposal_in_current": "proposal_in_current",
    "tool_error": "tool_error",
}


def _safe_tool_error_code(raw: Any) -> str:
    return _SAFE_TOOL_ERROR_CODES.get(str(raw or "").strip().lower(), "tool_error")


def _payload_error_code(output: Any) -> str | None:
    """Return a safe code when a tool's *content* is itself an error object.

    The plugin returns the backend's rejection as the tool's textual content
    (``{"error": <code>, "note": ...}``), so a transport ``429`` or
    ``backend_unreachable`` looks like a successful execution. Treat that
    payload as a failure rather than a completed call.
    """
    text = str(output or "").strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not parsed.get("error"):
        return None
    return _safe_tool_error_code(parsed.get("error"))


def _tool_outcome(tool: dict[str, Any]) -> tuple[str, str | None]:
    """Classify a transcript tool part into a persisted ``(status, error_code)``."""
    if tool.get("error"):
        message = str(tool["error"])
        if "not available" in message or "not named" in message:
            return "error", "not_permitted_in_scope"
        return "error", "tool_error"
    payload_error = _payload_error_code(tool.get("output"))
    if payload_error is not None:
        return "error", payload_error
    if tool.get("status") == "completed":
        return "completed", None
    return "error", None


def _record_tools(
    db: Session, conversation: AssistantConversation, tools: list[dict[str, Any]]
) -> list[str]:
    created: list[str] = []
    for tool in tools:
        name = tool.get("name") or "unknown"
        call_id = tool.get("call_id") or arguments_hash({"name": name, "at": time.time()})
        arguments = tool.get("input") if isinstance(tool.get("input"), dict) else {}
        status_value, error_code = _tool_outcome(tool)
        change_set_id = _extract_change_set_id(tool)
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
            change_set_id=UUID(change_set_id) if change_set_id else None,
        )
        if change_set_id:
            created.append(change_set_id)
            service.add_event(
                db, conversation, "proposal.created", {"change_set_id": change_set_id, "tool": name}
            )
        if name.endswith("validate_change_set") and change_set_id:
            parsed_ok = "validation_failed" not in str(tool.get("output") or "")
            service.add_event(
                db,
                conversation,
                "proposal.validated" if parsed_ok else "proposal.validation_failed",
                {"change_set_id": change_set_id},
            )
    return created


def _turn_poll_budget(timeout_seconds: int | None) -> int:
    """Polls allowed for one turn.

    The owner-configured ``timeout_seconds`` is the authoritative turn deadline;
    ``TURN_MAX_POLLS * TURN_POLL_SECONDS`` is only a floor, so a normal
    multi-step turn can finish even when tools are no longer throttled.
    """
    if timeout_seconds and timeout_seconds > 0:
        return max(TURN_MAX_POLLS, int(timeout_seconds / TURN_POLL_SECONDS))
    return TURN_MAX_POLLS


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
    runtime: OpenCodeRuntime,
    conversation: AssistantConversation,
    db: Session,
    *,
    model: dict[str, str] | None = None,
) -> str | None:
    body: dict[str, Any] = {"title": conversation.title[:80], "agent": "architecture-assistant"}
    if model:
        body["model"] = model
    created = runtime.create_session(body)
    session_id = str((created or {}).get("id") or "")
    if not session_id:
        return None
    conversation.opencode_session_id = session_id
    conversation.opencode_version = getattr(runtime, "version", None)
    db.flush()
    return session_id


def _session_anchor(runtime: OpenCodeRuntime, session_id: str) -> set[str]:
    """Ids of transcript messages that predate the current turn.

    The OpenCode session is a session-wide cache reused across turns, so the
    turn boundary is captured before the user prompt is sent.
    """
    try:
        payload = runtime.messages(session_id)
    except AssistantRuntimeError:
        return set()
    return {
        str(message.get("id")) for message in _normalize_messages(payload) if message.get("id")
    }


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

    from app.assistant import model_settings as model_settings_module

    owner_settings = model_settings_module.get_settings(db, conversation.tenant_id)
    model = model_settings_module.runtime_model(owner_settings)

    session_id = conversation.opencode_session_id
    if session_id is None:
        session_id = _create_session(runtime, conversation, db, model=model)
        if session_id is None:
            _fail(db, conversation, "session_unavailable")
            return

    envelope = build_envelope(db, user, conversation, workspace)
    runtime.synthetic(session_id, {"text": envelope_text(envelope)})
    db.commit()

    anchor = _session_anchor(runtime, session_id)
    try:
        runtime.prompt(session_id, {"text": user_text})
    except AssistantRuntimeError as error:
        if error.status != 404:
            raise
        # The OpenCode session is a disposable cache: recreate and replay the
        # current bounded envelope once, then retry the prompt.
        session_id = _create_session(runtime, conversation, db, model=model)
        if session_id is None:
            _fail(db, conversation, "session_unavailable")
            return
        runtime.synthetic(session_id, {"text": envelope_text(envelope)})
        anchor = _session_anchor(runtime, session_id)
        runtime.prompt(session_id, {"text": user_text})

    last_text = ""
    finished = False
    error_code: str | None = None
    created: list[str] = []
    for _ in range(_turn_poll_budget(owner_settings.timeout_seconds)):
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
        text, tools, finished, error_code = extract_turn(payload, exclude_ids=anchor)
        if text and text != last_text:
            last_text = text
            service.add_event(db, conversation, "assistant.delta", {"text": text})
            db.commit()
        if finished:
            if tools:
                created = _record_tools(db, conversation, tools)
                for tool in tools:
                    tool_status, tool_error = _tool_outcome(tool)
                    event_payload: dict[str, Any] = {
                        "tool": tool.get("name"),
                        "status": tool_status,
                    }
                    if tool_error:
                        event_payload["error_code"] = tool_error
                    service.add_event(db, conversation, "tool.completed", event_payload)
            break
        sleep(TURN_POLL_SECONDS)

    assistant_text = last_text[:MAX_ASSISTANT_CHARS]
    # A turn that never reached a terminal finish reason is a timeout; a terminal
    # turn that carries a provider/model failure is a safe, failed message rather
    # than an empty success.
    failure_code = error_code if finished else "turn_timeout"
    if failure_code:
        service.add_message(
            db,
            conversation,
            role="assistant",
            content=assistant_text,
            status_value="failed",
            error_code=failure_code,
            referenced_change_set_ids=created,
        )
        service.add_event(db, conversation, "turn.failed", {"reason": failure_code})
        conversation.error_code = failure_code
    else:
        service.add_message(
            db,
            conversation,
            role="assistant",
            content=assistant_text,
            status_value="complete",
            referenced_change_set_ids=created,
        )
        service.add_event(
            db, conversation, "assistant.message.completed", {"chars": len(assistant_text)}
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
