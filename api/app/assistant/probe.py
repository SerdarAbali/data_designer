"""Fail-closed startup capability probe for the Architecture Assistant runtime.

The assistant is only considered ready when *every* production assumption holds.
A failure never degrades silently: the probe returns a non-ready state, and the
runtime is treated as unavailable so no session or tool call can be made.

Static checks (deployed files):
* the restricted profile exists and is valid JSON;
* the profile contains a top-level ``deny *`` rule;
* the profile contains no ``ask`` effect anywhere;
* the default agent exists with an explicit, bounded ``steps`` limit;
* the built-in coding agents are disabled;
* the declared tool manifest exists, every tool is namespaced, declares
  ``codemode: false``, and has an explicit ``allow`` rule in the profile.

Live checks (against the running OpenCode server):
* HTTP Basic authentication is accepted;
* ``GET /api/info`` reports exactly the pinned version;
* the live OpenAPI document exposes every allowlisted contract path.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.assistant import endpoints as ep
from app.assistant import redaction
from app.assistant.runtime import (
    AssistantRuntimeError,
    OpenCodeRuntime,
    RuntimeErrorCode,
)
from app.assistant.settings import MAX_AGENT_STEPS, AssistantSettings

BUILTIN_AGENTS = ("build", "plan", "general", "explore")


class RuntimeState(str, Enum):
    READY = "ready"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"
    MISCONFIGURED = "misconfigured"


@dataclass(frozen=True)
class ProbeResult:
    state: RuntimeState
    reason_code: str
    expected_version: str
    observed_version: str | None
    checked_at: datetime
    correlation_id: str
    detail: str | None = None

    def is_ready(self) -> bool:
        return self.state is RuntimeState.READY


# Runtime error codes that must fail closed, and the probe state each maps to.
_ERROR_STATE: dict[RuntimeErrorCode, RuntimeState] = {
    RuntimeErrorCode.ENDPOINT_NOT_ALLOWED: RuntimeState.MISCONFIGURED,
    RuntimeErrorCode.INVALID_REQUEST: RuntimeState.MISCONFIGURED,
    RuntimeErrorCode.AUTH_FAILED: RuntimeState.MISCONFIGURED,
    RuntimeErrorCode.PROTOCOL_ERROR: RuntimeState.INCOMPATIBLE,
    RuntimeErrorCode.RESPONSE_TOO_LARGE: RuntimeState.INCOMPATIBLE,
    RuntimeErrorCode.REDIRECT_REJECTED: RuntimeState.INCOMPATIBLE,
    RuntimeErrorCode.HTTP_ERROR: RuntimeState.UNAVAILABLE,
    RuntimeErrorCode.RUNTIME_TIMEOUT: RuntimeState.UNAVAILABLE,
    RuntimeErrorCode.RUNTIME_UNREACHABLE: RuntimeState.UNAVAILABLE,
}


def _load_json(path: Path) -> tuple[Any, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError):
        return None, "invalid"


def _has_deny_all(profile: Mapping[str, Any]) -> bool:
    rules = profile.get("permissions")
    if not isinstance(rules, list):
        return False
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        if (
            rule.get("action") == "*"
            and rule.get("resource") == "*"
            and rule.get("effect") == "deny"
        ):
            return True
    return False


def _has_ask_effect(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("effect") == "ask":
            return True
        return any(_has_ask_effect(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_ask_effect(item) for item in value)
    return False


def _allow_actions(agent: Mapping[str, Any]) -> set[str]:
    actions: set[str] = set()
    rules = agent.get("permissions")
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, Mapping) and rule.get("effect") == "allow":
                action = rule.get("action")
                if isinstance(action, str):
                    actions.add(action)
    return actions


class CapabilityProbe:
    def __init__(
        self,
        settings: AssistantSettings,
        runtime: OpenCodeRuntime,
    ) -> None:
        self._settings = settings
        self._runtime = runtime
        self._secrets = (settings.password(),) if settings.has_password() else ()

    # -- public ----------------------------------------------------------

    def run(self) -> ProbeResult:
        try:
            return self._run()
        except AssistantRuntimeError as error:
            return self._runtime_failure(error)
        except Exception:  # noqa: BLE001 - the probe must never raise
            return self._result(
                RuntimeState.MISCONFIGURED,
                "probe_internal_error",
                detail="capability probe failed unexpectedly",
            )

    # -- internals -------------------------------------------------------

    def _run(self) -> ProbeResult:
        if not self._settings.enabled:
            return self._result(RuntimeState.DISABLED, "assistant_disabled")

        if self._settings.provider_fallback_enabled:
            return self._result(
                RuntimeState.MISCONFIGURED,
                "provider_fallback_enabled",
                detail="automatic provider fallback is not permitted",
            )

        if not self._settings.has_password():
            return self._result(
                RuntimeState.MISCONFIGURED,
                "runtime_password_missing",
                detail="no OpenCode server password is configured",
            )

        profile_result = self._check_profile()
        if profile_result is not None:
            return profile_result

        manifest_result = self._check_manifest()
        if manifest_result is not None:
            return manifest_result

        return self._check_live()

    def _check_profile(self) -> ProbeResult | None:
        profile, problem = _load_json(self._settings.profile_path())
        if problem == "missing":
            return self._result(
                RuntimeState.MISCONFIGURED, "profile_missing", detail="restricted profile not found"
            )
        if problem is not None or not isinstance(profile, dict):
            return self._result(
                RuntimeState.MISCONFIGURED,
                "profile_invalid",
                detail="restricted profile is invalid",
            )
        if not _has_deny_all(profile):
            return self._result(
                RuntimeState.MISCONFIGURED,
                "deny_all_missing",
                detail="restricted profile has no top-level deny-all rule",
            )
        if _has_ask_effect(profile):
            return self._result(
                RuntimeState.MISCONFIGURED,
                "ask_rule_present",
                detail="restricted profile contains an ask rule",
            )

        agents = profile.get("agents")
        agent_name = profile.get("default_agent")
        agent = agents.get(agent_name) if isinstance(agents, dict) else None
        if not isinstance(agent, dict):
            return self._result(
                RuntimeState.MISCONFIGURED,
                "default_agent_missing",
                detail="default assistant agent is not defined",
            )
        steps = agent.get("steps")
        if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
            return self._result(
                RuntimeState.MISCONFIGURED,
                "steps_missing",
                detail="assistant agent has no explicit step limit",
            )
        if steps > MAX_AGENT_STEPS:
            return self._result(
                RuntimeState.MISCONFIGURED,
                "steps_unbounded",
                detail="assistant agent step limit exceeds the permitted maximum",
            )
        if isinstance(agents, dict):
            for name in BUILTIN_AGENTS:
                builtin = agents.get(name)
                if not isinstance(builtin, dict) or builtin.get("disabled") is not True:
                    return self._result(
                        RuntimeState.MISCONFIGURED,
                        "builtin_agent_enabled",
                        detail="a built-in coding agent is not disabled",
                    )
        return None

    def _check_manifest(self) -> ProbeResult | None:
        manifest, problem = _load_json(self._settings.tools_path())
        if problem == "missing":
            return self._result(
                RuntimeState.MISCONFIGURED,
                "tool_manifest_missing",
                detail="declared tool manifest not found",
            )
        if problem is not None or not isinstance(manifest, dict):
            return self._result(
                RuntimeState.MISCONFIGURED,
                "tool_manifest_invalid",
                detail="declared tool manifest is invalid",
            )
        tools = manifest.get("tools")
        if not isinstance(tools, list) or not tools:
            return self._result(
                RuntimeState.MISCONFIGURED,
                "tool_manifest_empty",
                detail="declared tool manifest has no tools",
            )

        profile, _ = _load_json(self._settings.profile_path())
        agent = {}
        if isinstance(profile, dict) and isinstance(profile.get("agents"), dict):
            agent = profile["agents"].get(profile.get("default_agent")) or {}
        allowed = _allow_actions(agent) if isinstance(agent, dict) else set()

        for tool in tools:
            if not isinstance(tool, Mapping):
                return self._result(
                    RuntimeState.MISCONFIGURED,
                    "tool_manifest_invalid",
                    detail="declared tool entry is invalid",
                )
            name = tool.get("name")
            if not isinstance(name, str) or not name.startswith("architecture_"):
                return self._result(
                    RuntimeState.MISCONFIGURED,
                    "tool_name_unnamespaced",
                    detail="declared tool name is not namespaced",
                )
            if tool.get("codemode") is not False:
                return self._result(
                    RuntimeState.MISCONFIGURED,
                    "tool_codemode_missing",
                    detail=f"declared tool {name} is missing codemode:false",
                )
            if name not in allowed:
                return self._result(
                    RuntimeState.MISCONFIGURED,
                    "tool_not_allowed",
                    detail=f"declared tool {name} has no explicit allow rule",
                )
        return None

    def _check_live(self) -> ProbeResult:
        info = self._runtime.info()
        version = info.get("version") if isinstance(info, Mapping) else None
        if not isinstance(version, str):
            return self._result(
                RuntimeState.INCOMPATIBLE,
                "version_unreadable",
                detail="OpenCode did not report a version",
            )
        if version != self._settings.opencode_version:
            return self._result(
                RuntimeState.INCOMPATIBLE,
                "version_mismatch",
                observed_version=version,
                detail="OpenCode version does not match the pinned version",
            )

        document = self._runtime.openapi()
        paths = document.get("paths") if isinstance(document, Mapping) else None
        if not isinstance(paths, Mapping):
            return self._result(
                RuntimeState.INCOMPATIBLE,
                "contract_unreadable",
                observed_version=version,
                detail="OpenCode OpenAPI document has no paths",
            )
        missing = sorted(path for path in ep.REQUIRED_CONTRACT_PATHS if path not in paths)
        if missing:
            return self._result(
                RuntimeState.INCOMPATIBLE,
                "endpoint_contract_drift",
                observed_version=version,
                detail="required OpenAPI paths are missing",
            )
        openapi_version = document.get("openapi") if isinstance(document, Mapping) else None
        if not isinstance(openapi_version, str) or not openapi_version.startswith("3."):
            return self._result(
                RuntimeState.INCOMPATIBLE,
                "contract_version_drift",
                observed_version=version,
                detail="OpenCode OpenAPI document version is unsupported",
            )

        return self._result(RuntimeState.READY, "ok", observed_version=version)

    def _runtime_failure(self, error: AssistantRuntimeError) -> ProbeResult:
        state = _ERROR_STATE.get(error.code, RuntimeState.UNAVAILABLE)
        return self._result(
            state,
            error.code.value,
            correlation_id=error.correlation_id,
            detail=redaction.scrub(str(error), self._secrets),
        )

    def _result(
        self,
        state: RuntimeState,
        reason_code: str,
        *,
        observed_version: str | None = None,
        correlation_id: str | None = None,
        detail: str | None = None,
    ) -> ProbeResult:
        return ProbeResult(
            state=state,
            reason_code=reason_code,
            expected_version=self._settings.opencode_version,
            observed_version=observed_version,
            checked_at=datetime.now(UTC),
            correlation_id=correlation_id or redaction.correlation_id(),
            detail=detail,
        )


class AssistantRuntimeStatus:
    """Cached, process-wide probe result used by the status endpoint.

    When the assistant is disabled no runtime is ever constructed, so a disabled
    assistant cannot contact OpenCode.
    """

    def __init__(
        self,
        settings: AssistantSettings,
        *,
        runtime: OpenCodeRuntime | None = None,
        runtime_factory: Any | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        self._settings = settings
        self._runtime = runtime
        self._runtime_factory = runtime_factory or (lambda: OpenCodeRuntime(settings))
        self._ttl = settings.probe_cache_seconds if ttl_seconds is None else ttl_seconds
        self._lock = threading.Lock()
        self._result: ProbeResult | None = None
        self._checked_at: float = 0.0

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    def refresh(self, *, force: bool = False) -> ProbeResult:
        with self._lock:
            now = time.monotonic()
            if not force and self._result is not None and now - self._checked_at < self._ttl:
                return self._result
            result = self._probe()
            self._result = result
            self._checked_at = now
            return result

    def reset(self) -> None:
        with self._lock:
            self._result = None
            self._checked_at = 0.0

    def public_snapshot(self, *, force: bool = False) -> dict[str, Any]:
        result = self.refresh(force=force)
        return {
            "assistant_enabled": self._settings.enabled,
            "runtime_status": result.state.value,
            "expected_opencode_version": result.expected_version,
            "observed_opencode_version": result.observed_version,
            "probe_checked_at": result.checked_at.isoformat(),
            "reason_code": result.reason_code,
            "correlation_id": result.correlation_id,
        }

    def _probe(self) -> ProbeResult:
        if not self._settings.enabled:
            return ProbeResult(
                state=RuntimeState.DISABLED,
                reason_code="assistant_disabled",
                expected_version=self._settings.opencode_version,
                observed_version=None,
                checked_at=datetime.now(UTC),
                correlation_id=redaction.correlation_id(),
            )
        runtime = self._runtime or self._runtime_factory()
        return CapabilityProbe(self._settings, runtime).run()


_status: AssistantRuntimeStatus | None = None
_status_lock = threading.Lock()


def get_assistant_status() -> AssistantRuntimeStatus:
    """FastAPI dependency returning the process-wide runtime status."""
    global _status
    if _status is None:
        with _status_lock:
            if _status is None:
                from app.assistant.settings import settings as assistant_settings

                _status = AssistantRuntimeStatus(assistant_settings)
    return _status


def reset_assistant_status() -> None:
    global _status
    with _status_lock:
        _status = None
