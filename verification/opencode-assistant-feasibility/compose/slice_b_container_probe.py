#!/usr/bin/env python3
"""Slice B deployment verification, run inside the application (api) image.

Executed by the isolated ``slice-b-verify`` Compose project. It reaches OpenCode
only through the private Compose network by service name
(``http://opencode:4096``), exercising the real production runtime adapter,
capability probe, and status endpoint.

It prints a PASS/FAIL line per check and exits non-zero if any check fails.
"""

from __future__ import annotations

import json
import os
import sys
from uuid import uuid4

import httpx

from app import main
from app.assistant import endpoints as ep
from app.assistant.probe import AssistantRuntimeStatus, CapabilityProbe, RuntimeState
from app.assistant.probe import get_assistant_status
from app.assistant.runtime import AssistantRuntimeError, OpenCodeRuntime
from app.assistant.settings import AssistantSettings
from app.auth.dependencies import AuthenticatedUser, get_current_user
from fastapi.testclient import TestClient

BASE_URL = os.environ["ASSISTANT_OPENCODE_BASE_URL"]
PASSWORD = os.environ["ASSISTANT_OPENCODE_PASSWORD"]
PROFILE = os.environ["ASSISTANT_OPENCODE_PROFILE_PATH"]
TOOLS = os.environ["ASSISTANT_OPENCODE_TOOLS_PATH"]

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    suffix = f" :: {detail}" if detail else ""
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{suffix}")
    if not ok:
        FAILURES.append(name)


def mk_settings(**overrides) -> AssistantSettings:
    values = {
        "enabled": True,
        "opencode_base_url": BASE_URL,
        "opencode_version": "2.0.30",
        "opencode_password": PASSWORD,
        "opencode_profile_path": PROFILE,
        "opencode_tools_path": TOOLS,
        "connect_timeout_seconds": 2.0,
        "request_timeout_seconds": 5.0,
        "probe_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return AssistantSettings(**values)


def probe(settings: AssistantSettings):
    runtime = OpenCodeRuntime(settings)
    try:
        return CapabilityProbe(settings, runtime).run()
    finally:
        runtime.close()


def auth_checks() -> None:
    print("\n-- authentication (through the Compose network) --")
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        unauthenticated = client.get("/api/info")
        check(
            "unauthenticated request rejected",
            unauthenticated.status_code == 401,
            f"status={unauthenticated.status_code}",
        )

        incorrect = client.get("/api/info", auth=("opencode", "definitely-wrong"))
        check(
            "incorrect Basic credentials rejected",
            incorrect.status_code == 401,
            f"status={incorrect.status_code}",
        )

        correct = client.get("/api/info", auth=("opencode", PASSWORD))
        check(
            "API backend authenticates with server-side configuration",
            correct.status_code == 200,
            f"status={correct.status_code}",
        )
        if correct.status_code == 200:
            check(
                "observed OpenCode version is 2.0.30",
                correct.json().get("version") == "2.0.30",
                str(correct.json().get("version")),
            )


def probe_checks() -> None:
    print("\n-- production capability probe --")
    settings = mk_settings()
    ready = probe(settings)
    check(
        "correct runtime reports ready",
        ready.state is RuntimeState.READY,
        f"state={ready.state.value} reason={ready.reason_code}",
    )
    check("ready observed version is 2.0.30", ready.observed_version == "2.0.30")

    mismatch = probe(mk_settings(opencode_version="2.0.29"))
    check(
        "wrong expected version reports incompatible",
        mismatch.state is RuntimeState.INCOMPATIBLE and mismatch.reason_code == "version_mismatch",
        f"state={mismatch.state.value} reason={mismatch.reason_code}",
    )

    missing = probe(mk_settings(opencode_password=""))
    check(
        "missing credentials report a safe non-ready status",
        missing.state is RuntimeState.MISCONFIGURED and missing.reason_code == "runtime_password_missing",
        f"state={missing.state.value} reason={missing.reason_code}",
    )

    invalid = probe(mk_settings(opencode_password="definitely-wrong"))
    check(
        "invalid credentials report a safe non-ready status",
        invalid.state is RuntimeState.MISCONFIGURED and invalid.reason_code == "auth_failed",
        f"state={invalid.state.value} reason={invalid.reason_code}",
    )
    check(
        "invalid-credential failure leaks no secret",
        PASSWORD not in (invalid.detail or "") and PASSWORD not in json.dumps(invalid.reason_code),
    )

    no_deny = json.loads(open(PROFILE, encoding="utf-8").read())
    no_deny["permissions"] = []
    with open("/tmp/bad-profile.json", "w", encoding="utf-8") as handle:
        json.dump(no_deny, handle)
    bad = probe(mk_settings(opencode_profile_path="/tmp/bad-profile.json"))
    check(
        "restricted-profile mismatch fails closed",
        bad.state is RuntimeState.MISCONFIGURED and bad.reason_code == "deny_all_missing",
        f"state={bad.state.value} reason={bad.reason_code}",
    )

    ask = json.loads(open(PROFILE, encoding="utf-8").read())
    ask["agents"]["architecture-assistant"]["permissions"].append(
        {"action": "webfetch", "resource": "*", "effect": "ask"}
    )
    with open("/tmp/ask-profile.json", "w", encoding="utf-8") as handle:
        json.dump(ask, handle)
    ask_result = probe(mk_settings(opencode_profile_path="/tmp/ask-profile.json"))
    check(
        "no ask rule is accepted",
        ask_result.state is RuntimeState.MISCONFIGURED and ask_result.reason_code == "ask_rule_present",
        f"state={ask_result.state.value} reason={ask_result.reason_code}",
    )

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"version": "2.0.30"})

    disabled_settings = mk_settings(enabled=False)
    disabled_runtime = OpenCodeRuntime(disabled_settings, transport=httpx.MockTransport(handler))
    try:
        disabled = CapabilityProbe(disabled_settings, disabled_runtime).run()
    finally:
        disabled_runtime.close()
    check(
        "disabled mode performs no OpenCode request",
        disabled.state is RuntimeState.DISABLED and not calls,
        f"state={disabled.state.value} requests={len(calls)}",
    )


def status_endpoint_checks() -> None:
    print("\n-- application-owned status endpoint --")
    settings = mk_settings()
    status = AssistantRuntimeStatus(settings, runtime=OpenCodeRuntime(settings))
    main.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid4(), tenant_id=uuid4(), email="verify@example.test", tenant_name="Verify"
    )
    main.app.dependency_overrides[get_assistant_status] = lambda: status
    try:
        response = TestClient(main.app).get("/api/assistant/status")
    finally:
        main.app.dependency_overrides.pop(get_current_user, None)
        main.app.dependency_overrides.pop(get_assistant_status, None)

    expected_keys = {
        "assistant_enabled",
        "runtime_status",
        "expected_opencode_version",
        "observed_opencode_version",
        "probe_checked_at",
        "reason_code",
        "correlation_id",
    }
    body = response.json()
    check(
        "status endpoint returns exactly the safe keys",
        set(body) == expected_keys,
        str(sorted(body)),
    )
    check("status reports ready", body.get("runtime_status") == "ready")
    check("status observed version is 2.0.30", body.get("observed_opencode_version") == "2.0.30")

    lowered = response.text.lower()
    check(
        "status response contains no credential or internal URL",
        PASSWORD.lower() not in lowered
        and "authorization" not in lowered
        and "opencode:4096" not in lowered
        and "password" not in lowered,
    )


def forbidden_route_checks() -> None:
    print("\n-- forbidden routes remain unreachable through the adapter --")
    forbidden = [
        ("GET", "/api/config"),
        ("PATCH", "/api/experimental/config"),
        ("GET", "/api/credential"),
        ("GET", "/api/fs/read/etc/passwd"),
        ("POST", "/api/experimental/fs/write"),
        ("POST", "/api/shell"),
        ("GET", "/api/pty"),
        ("GET", "/api/vcs/status"),
        ("GET", "/api/worktree"),
        ("POST", "/api/rpc/rpc_1/method"),
        ("POST", "/api/plugin/update"),
        ("GET", "/api/mcp"),
        ("GET", "/api/integration"),
    ]
    leaked = []
    for method, path in forbidden:
        try:
            ep.resolve_endpoint(method, path)
            leaked.append(f"{method} {path}")
        except ep.EndpointNotAllowed:
            continue
    check("all forbidden routes are rejected before network access", not leaked, ", ".join(leaked))

    # The adapter exposes no generic path-taking method.
    runtime = OpenCodeRuntime(mk_settings())
    try:
        generic = [name for name in ("request", "get", "post", "fetch", "proxy", "forward") if hasattr(runtime, name)]
    finally:
        runtime.close()
    check("runtime adapter exposes no generic HTTP method", not generic, ", ".join(generic))


def exception_redaction_check() -> None:
    print("\n-- exception redaction --")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=PASSWORD.encode())

    runtime = OpenCodeRuntime(mk_settings(), transport=httpx.MockTransport(handler))
    try:
        try:
            runtime.info()
            check("upstream error raised", False)
        except AssistantRuntimeError as error:
            check(
                "runtime exception leaks no credential",
                PASSWORD not in str(error) and PASSWORD not in repr(error.__dict__),
                f"code={error.code.value}",
            )
    finally:
        runtime.close()


def main_entry() -> int:
    print(f"Slice B deployment verification against {BASE_URL}")
    auth_checks()
    probe_checks()
    status_endpoint_checks()
    forbidden_route_checks()
    exception_redaction_check()
    print(f"\nDEPLOYMENT RESULT: {'FAIL' if FAILURES else 'PASS'}")
    if FAILURES:
        print("failed checks: " + "; ".join(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main_entry())
