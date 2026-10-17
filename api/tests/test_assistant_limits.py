"""Rate-limit separation: lightweight scope checks vs actual tool execution.

A normal multi-step assistant turn resolves scope once per model request *and*
executes a tool per step. Sharing one budget let scope checks alone exhaust the
tool budget; these tests pin the separation and the surviving protections.
"""

from __future__ import annotations

import pytest

from app.assistant import limits

_TOOL = {"conversation_id": "conv-1", "user_id": "user-1", "workspace_id": "ws-1"}


def test_scope_checks_do_not_starve_a_twelve_step_turn() -> None:
    limiter = limits.AssistantLimiter()
    for _ in range(12):
        limiter.check_scope_rate("ses-1")
        limiter.check_tool_rate(**_TOOL)
    # The former shared 20/min budget would have raised at ~step 10.


def test_scope_checks_are_capped_independently_of_tool_execution() -> None:
    limiter = limits.AssistantLimiter()
    for _ in range(limits.SCOPE_CHECKS_PER_MINUTE):
        limiter.check_scope_rate("ses-1")
    with pytest.raises(limits.LimitExceeded) as error:
        limiter.check_scope_rate("ses-1")
    assert error.value.code == "scope_rate_limited"
    # Exhausting scope checks leaves tool execution untouched.
    for _ in range(12):
        limiter.check_tool_rate(**_TOOL)


def test_tool_execution_is_capped_per_conversation() -> None:
    limiter = limits.AssistantLimiter()
    for _ in range(limits.TOOL_CALLS_PER_MINUTE_PER_CONVERSATION):
        limiter.check_tool_rate(**_TOOL)
    with pytest.raises(limits.LimitExceeded) as error:
        limiter.check_tool_rate(**_TOOL)
    assert error.value.code == "tool_rate_limited"
    # A different conversation within the same user/workspace still has budget.
    limiter.check_tool_rate(
        conversation_id="conv-2", user_id="user-1", workspace_id="ws-1"
    )


def test_tool_execution_is_capped_per_user() -> None:
    limiter = limits.AssistantLimiter()
    per_conversation = limits.TOOL_CALLS_PER_MINUTE_PER_CONVERSATION
    conversations = limits.TOOL_CALLS_PER_MINUTE_PER_USER // per_conversation
    for index in range(conversations):
        for _ in range(per_conversation):
            limiter.check_tool_rate(
                conversation_id=f"conv-{index}", user_id="user-1", workspace_id="ws-1"
            )
    with pytest.raises(limits.LimitExceeded) as error:
        limiter.check_tool_rate(
            conversation_id="conv-next", user_id="user-1", workspace_id="ws-1"
        )
    assert error.value.code == "tool_rate_limited"


def test_internal_dispatch_has_a_global_abuse_cap() -> None:
    limiter = limits.AssistantLimiter()
    for _ in range(limits.INTERNAL_DISPATCH_PER_MINUTE):
        limiter.check_internal_dispatch_rate()
    with pytest.raises(limits.LimitExceeded) as error:
        limiter.check_internal_dispatch_rate()
    assert error.value.code == "internal_rate_limited"


def test_windows_expire_after_a_minute() -> None:
    limiter = limits.AssistantLimiter()
    for _ in range(limits.TOOL_CALLS_PER_MINUTE_PER_CONVERSATION):
        limiter.check_tool_rate(**_TOOL, now=1000.0)
    with pytest.raises(limits.LimitExceeded):
        limiter.check_tool_rate(**_TOOL, now=1005.0)
    limiter.check_tool_rate(**_TOOL, now=1061.0)
