"""Fail-closed startup capability probe tests (Slice B).

Covers required proofs 1, 2, 13, 14, 15, 16, 17, 18.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.assistant import endpoints as ep
from app.assistant.probe import CapabilityProbe, RuntimeState
from tests.assistant_support import (
    DISTINCTIVE_PASSWORD,
    Recorder,
    happy_openapi,
    make_settings,
    probe_handler,
    runtime_with,
    write_profile,
    write_tools,
)


def run_probe(settings, handler):
    runtime = runtime_with(settings, handler)
    try:
        return CapabilityProbe(settings, runtime).run()
    finally:
        runtime.close()


def test_pinned_version_passes() -> None:
    result = run_probe(make_settings(), probe_handler())
    assert result.state is RuntimeState.READY
    assert result.reason_code == "ok"
    assert result.observed_version == "2.0.30"
    assert result.expected_version == "2.0.30"


def test_version_mismatch_fails_closed() -> None:
    result = run_probe(make_settings(), probe_handler(info={"version": "2.0.29"}))
    assert result.state is RuntimeState.INCOMPATIBLE
    assert result.reason_code == "version_mismatch"
    assert result.observed_version == "2.0.29"


def test_unreadable_version_fails_closed() -> None:
    result = run_probe(make_settings(), probe_handler(info={"pid": 1}))
    assert result.state is RuntimeState.INCOMPATIBLE
    assert result.reason_code == "version_unreadable"


def test_authentication_failure_fails_closed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "unauthorized"}})

    result = run_probe(make_settings(), handler)
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "auth_failed"


def test_probe_timeout_is_unavailable_without_leaking_internals() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream too slow")

    result = run_probe(make_settings(), handler)
    assert result.state is RuntimeState.UNAVAILABLE
    assert result.reason_code == "runtime_timeout"
    detail = result.detail or ""
    assert "opencode.test" not in detail
    assert DISTINCTIVE_PASSWORD not in detail


def test_unreachable_runtime_is_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    result = run_probe(make_settings(), handler)
    assert result.state is RuntimeState.UNAVAILABLE
    assert result.reason_code == "runtime_unreachable"


def test_oversized_probe_response_is_incompatible() -> None:
    settings = make_settings(max_response_bytes=1024)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 100_000)

    result = run_probe(settings, handler)
    assert result.state is RuntimeState.INCOMPATIBLE
    assert result.reason_code == "response_too_large"


def test_ask_rule_fails_closed_without_contacting_opencode(tmp_path: Path) -> None:
    profile = write_profile(
        tmp_path,
        lambda data: data["agents"]["architecture-assistant"]["permissions"].append(
            {"action": "webfetch", "resource": "*", "effect": "ask"}
        ),
    )
    recorder = Recorder()
    result = run_probe(
        make_settings(opencode_profile_path=profile), probe_handler(recorder=recorder)
    )
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "ask_rule_present"
    assert not recorder.called


def test_missing_deny_all_fails_closed(tmp_path: Path) -> None:
    profile = write_profile(tmp_path, lambda data: data.__setitem__("permissions", []))
    result = run_probe(make_settings(opencode_profile_path=profile), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "deny_all_missing"


def test_missing_profile_fails_closed(tmp_path: Path) -> None:
    settings = make_settings(opencode_profile_path=str(tmp_path / "absent.json"))
    result = run_probe(settings, probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "profile_missing"


def test_missing_steps_fails_closed(tmp_path: Path) -> None:
    profile = write_profile(
        tmp_path, lambda data: data["agents"]["architecture-assistant"].pop("steps")
    )
    result = run_probe(make_settings(opencode_profile_path=profile), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "steps_missing"


def test_unbounded_steps_fails_closed(tmp_path: Path) -> None:
    profile = write_profile(
        tmp_path, lambda data: data["agents"]["architecture-assistant"].__setitem__("steps", 99)
    )
    result = run_probe(make_settings(opencode_profile_path=profile), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "steps_unbounded"


def test_enabled_builtin_agent_fails_closed(tmp_path: Path) -> None:
    profile = write_profile(
        tmp_path, lambda data: data["agents"]["build"].__setitem__("disabled", False)
    )
    result = run_probe(make_settings(opencode_profile_path=profile), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "builtin_agent_enabled"


def test_missing_codemode_fails_closed(tmp_path: Path) -> None:
    tools = write_tools(
        tmp_path,
        [{"name": "architecture_probe_context", "kind": "probe"}],
    )
    result = run_probe(make_settings(opencode_tools_path=tools), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "tool_codemode_missing"


def test_unnamespaced_tool_fails_closed(tmp_path: Path) -> None:
    tools = write_tools(tmp_path, [{"name": "probe_context", "codemode": False}])
    result = run_probe(make_settings(opencode_tools_path=tools), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "tool_name_unnamespaced"


def test_tool_without_allow_rule_fails_closed(tmp_path: Path) -> None:
    tools = write_tools(tmp_path, [{"name": "architecture_other", "codemode": False}])
    result = run_probe(make_settings(opencode_tools_path=tools), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "tool_not_allowed"


def test_missing_tool_manifest_fails_closed(tmp_path: Path) -> None:
    settings = make_settings(opencode_tools_path=str(tmp_path / "absent.json"))
    result = run_probe(settings, probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "tool_manifest_missing"


def test_endpoint_contract_drift_fails_closed(tmp_path: Path) -> None:
    document = happy_openapi()
    document["paths"].pop("/api/session/{sessionID}/interrupt")
    result = run_probe(make_settings(), probe_handler(openapi=document))
    assert result.state is RuntimeState.INCOMPATIBLE
    assert result.reason_code == "endpoint_contract_drift"


def test_contract_version_drift_fails_closed() -> None:
    document = happy_openapi()
    document["openapi"] = "2.0"
    result = run_probe(make_settings(), probe_handler(openapi=document))
    assert result.state is RuntimeState.INCOMPATIBLE
    assert result.reason_code == "contract_version_drift"


def test_contract_fetch_uses_a_dedicated_larger_cap() -> None:
    # The lifecycle response cap is far below the contract document; the probe's
    # contract fetch has its own, larger cap and must still succeed.
    settings = make_settings(max_response_bytes=512, max_contract_bytes=65536)
    result = run_probe(settings, probe_handler())
    assert result.state is RuntimeState.READY


def test_contract_size_limit_is_enforced() -> None:
    settings = make_settings(max_response_bytes=65536, max_contract_bytes=256)
    result = run_probe(settings, probe_handler())
    assert result.state is RuntimeState.INCOMPATIBLE
    assert result.reason_code == "response_too_large"


def test_provider_fallback_fails_closed() -> None:
    result = run_probe(
        make_settings(provider_fallback_enabled=True), probe_handler()
    )
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "provider_fallback_enabled"


def test_missing_password_fails_closed() -> None:
    result = run_probe(make_settings(opencode_password=""), probe_handler())
    assert result.state is RuntimeState.MISCONFIGURED
    assert result.reason_code == "runtime_password_missing"


def test_disabled_does_not_contact_opencode() -> None:
    recorder = Recorder()
    settings = make_settings(enabled=False)
    runtime = runtime_with(settings, probe_handler(recorder=recorder))
    try:
        result = CapabilityProbe(settings, runtime).run()
    finally:
        runtime.close()
    assert result.state is RuntimeState.DISABLED
    assert result.reason_code == "assistant_disabled"
    assert not recorder.called


def test_required_contract_paths_match_the_allowlist() -> None:
    assert ep.REQUIRED_CONTRACT_PATHS == frozenset(
        endpoint.template for endpoint in ep.ALLOWED_ENDPOINTS
    )
    # The probe-only endpoints are not part of the runtime lifecycle contract.
    assert "/api/info" not in ep.REQUIRED_CONTRACT_PATHS
    assert "/openapi.json" not in ep.REQUIRED_CONTRACT_PATHS


def test_shipped_profile_and_manifest_are_valid() -> None:
    from tests.assistant_support import PROFILE_PATH, TOOLS_PATH

    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(TOOLS_PATH.read_text(encoding="utf-8"))
    assert profile["default_agent"] == "architecture-assistant"
    assert manifest["tools"]
    result = run_probe(make_settings(), probe_handler())
    assert result.state is RuntimeState.READY
