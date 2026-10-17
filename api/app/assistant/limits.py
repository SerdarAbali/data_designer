"""Centralized assistant limits: concurrency, rate, and size.

In-process and thread-safe. The application is a single API process in this
environment; the limits are deliberately conservative and fail closed with a
structured ``429`` rather than silently queueing.
"""

from __future__ import annotations

import threading
import time
from collections import deque

MAX_PROMPT_CHARS = 8000
MAX_CONTEXT_BYTES = 8 * 1024
MAX_MESSAGES_PER_CONVERSATION = 500
MAX_TOOL_CALLS_PER_TURN = 12
MAX_ACTIVE_PER_CONVERSATION = 1
MAX_ACTIVE_PER_USER = 3
MAX_ACTIVE_PER_WORKSPACE = 3
MAX_ACTIVE_GLOBAL = 4
TURNS_PER_MINUTE_PER_USER = 20
SESSION_CREATIONS_PER_MINUTE = 20

#: Internal scope resolution (``/internal/assistant/scope``) is a cheap,
#: idempotent read performed once per model request. It gets its own bucket so a
#: multi-step turn's context hooks can never starve real tool execution. The
#: budget is generous but still bounds a runaway caller.
SCOPE_CHECKS_PER_MINUTE = 240

#: Actual architecture tool execution (``/internal/assistant/call``). Sized so a
#: full 12-tool turn fits comfortably within one conversation's budget, while
#: still bounding a runaway model loop. Enforced per conversation, per user, and
#: per workspace.
TOOL_CALLS_PER_MINUTE_PER_CONVERSATION = 120
TOOL_CALLS_PER_MINUTE_PER_USER = 240
TOOL_CALLS_PER_MINUTE_PER_WORKSPACE = 480

#: Global abuse cap across *all* internal dispatch (scope checks + tool calls).
INTERNAL_DISPATCH_PER_MINUTE = 1200

GENERATION_TIMEOUT_SECONDS = 180
CANCELLATION_TIMEOUT_SECONDS = 15
PROVIDER_ERROR_BACKOFF_SECONDS = 30


class LimitExceeded(Exception):
    """A structured, safe over-limit error."""

    def __init__(self, code: str, retry_after: int | None = None) -> None:
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class AssistantLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_conversation: dict[str, int] = {}
        self._active_user: dict[str, int] = {}
        self._active_workspace: dict[str, int] = {}
        self._active_global = 0
        self._turn_times: dict[str, deque[float]] = {}
        self._session_times: dict[str, deque[float]] = {}
        self._scope_times: dict[str, deque[float]] = {}
        self._tool_times_conversation: dict[str, deque[float]] = {}
        self._tool_times_user: dict[str, deque[float]] = {}
        self._tool_times_workspace: dict[str, deque[float]] = {}
        self._internal_dispatch_times: dict[str, deque[float]] = {}

    def _bump(self, table: dict[str, int], key: str, delta: int) -> int:
        value = table.get(key, 0) + delta
        if value <= 0:
            table.pop(key, None)
            return 0
        table[key] = value
        return value

    def acquire(self, *, conversation_id: str, user_id: str, workspace_id: str) -> None:
        with self._lock:
            if self._active_conversation.get(conversation_id, 0) >= MAX_ACTIVE_PER_CONVERSATION:
                raise LimitExceeded("conversation_busy")
            if self._active_user.get(user_id, 0) >= MAX_ACTIVE_PER_USER:
                raise LimitExceeded("user_concurrency")
            if self._active_workspace.get(workspace_id, 0) >= MAX_ACTIVE_PER_WORKSPACE:
                raise LimitExceeded("workspace_concurrency")
            if self._active_global >= MAX_ACTIVE_GLOBAL:
                raise LimitExceeded("global_concurrency", retry_after=5)
            self._bump(self._active_conversation, conversation_id, 1)
            self._bump(self._active_user, user_id, 1)
            self._bump(self._active_workspace, workspace_id, 1)
            self._active_global += 1

    def release(self, *, conversation_id: str, user_id: str, workspace_id: str) -> None:
        with self._lock:
            self._bump(self._active_conversation, conversation_id, -1)
            self._bump(self._active_user, user_id, -1)
            self._bump(self._active_workspace, workspace_id, -1)
            self._active_global = max(0, self._active_global - 1)

    def check_turn_rate(self, user_id: str, *, now: float | None = None) -> None:
        moment = now if now is not None else time.monotonic()
        with self._lock:
            window = self._turn_times.setdefault(user_id, deque())
            while window and moment - window[0] > 60:
                window.popleft()
            if len(window) >= TURNS_PER_MINUTE_PER_USER:
                raise LimitExceeded("rate_limited", retry_after=60)
            window.append(moment)

    def check_session_rate(self, user_id: str, *, now: float | None = None) -> None:
        moment = now if now is not None else time.monotonic()
        with self._lock:
            window = self._session_times.setdefault(user_id, deque())
            while window and moment - window[0] > 60:
                window.popleft()
            if len(window) >= SESSION_CREATIONS_PER_MINUTE:
                raise LimitExceeded("session_rate_limited", retry_after=60)
            window.append(moment)

    def _enforce(
        self,
        checks: list[tuple[dict[str, deque[float]], str, int]],
        moment: float,
        code: str,
    ) -> None:
        """Atomically enforce several sliding-window budgets, then record one hit."""
        for table, key, limit in checks:
            window = table.setdefault(key, deque())
            while window and moment - window[0] > 60:
                window.popleft()
            if len(window) >= limit:
                raise LimitExceeded(code, retry_after=60)
        for table, key, _limit in checks:
            table.setdefault(key, deque()).append(moment)

    def check_scope_rate(self, conversation_key: str, *, now: float | None = None) -> None:
        """Lightweight internal scope checks, keyed per conversation/session.

        Deliberately separate from tool execution so resolving scope on every
        model request cannot exhaust the tool budget.
        """
        moment = now if now is not None else time.monotonic()
        with self._lock:
            self._enforce(
                [(self._scope_times, conversation_key, SCOPE_CHECKS_PER_MINUTE)],
                moment,
                "scope_rate_limited",
            )

    def check_tool_rate(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str,
        now: float | None = None,
    ) -> None:
        """Actual architecture tool execution, bounded per conversation/user/workspace."""
        moment = now if now is not None else time.monotonic()
        with self._lock:
            self._enforce(
                [
                    (
                        self._tool_times_conversation,
                        conversation_id,
                        TOOL_CALLS_PER_MINUTE_PER_CONVERSATION,
                    ),
                    (self._tool_times_user, user_id, TOOL_CALLS_PER_MINUTE_PER_USER),
                    (
                        self._tool_times_workspace,
                        workspace_id,
                        TOOL_CALLS_PER_MINUTE_PER_WORKSPACE,
                    ),
                ],
                moment,
                "tool_rate_limited",
            )

    def check_internal_dispatch_rate(self, *, now: float | None = None) -> None:
        """Global abuse cap across every internal-dispatch request."""
        moment = now if now is not None else time.monotonic()
        with self._lock:
            self._enforce(
                [
                    (
                        self._internal_dispatch_times,
                        "internal-dispatch",
                        INTERNAL_DISPATCH_PER_MINUTE,
                    )
                ],
                moment,
                "internal_rate_limited",
            )

    def reset(self) -> None:
        with self._lock:
            self._active_conversation.clear()
            self._active_user.clear()
            self._active_workspace.clear()
            self._active_global = 0
            self._turn_times.clear()
            self._session_times.clear()
            self._scope_times.clear()
            self._tool_times_conversation.clear()
            self._tool_times_user.clear()
            self._tool_times_workspace.clear()
            self._internal_dispatch_times.clear()


limiter = AssistantLimiter()
