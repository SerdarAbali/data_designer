#!/usr/bin/env python3
"""Slice B live probe check.

Opt-in, manual verification (not part of the application test suite and not
collected by ``pytest``, whose ``testpaths`` is ``api/tests``).

It boots a real, fully isolated OpenCode server running the *production*
restricted profile (``assistant-runtime/opencode.json`` + plugin) and runs the
production :class:`CapabilityProbe` against it. It proves the probe passes on the
pinned version and fails closed on a version mismatch and while disabled.

Run:

    api/.venv/bin/python verification/opencode-assistant-feasibility/slice_b_live_probe.py
"""

from __future__ import annotations

import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = Path(__file__).resolve().parent / "runtime"
sys.path.insert(0, str(HARNESS_DIR))
sys.path.insert(0, str(REPO_ROOT / "api"))

import harness  # noqa: E402

from app.assistant.probe import CapabilityProbe, RuntimeState  # noqa: E402
from app.assistant.runtime import OpenCodeRuntime  # noqa: E402
from app.assistant.settings import AssistantSettings  # noqa: E402

PORT = 4731
PASSWORD = "slice-b-live-probe-password"
SCRATCH = harness.SCRATCH_ROOT / "slice-b-live"
SANDBOX = SCRATCH / "sandbox"
PROFILE = REPO_ROOT / "assistant-runtime" / "opencode.json"
TOOLS = REPO_ROOT / "assistant-runtime" / "assistant-tools.json"
PLUGINS = REPO_ROOT / "assistant-runtime" / ".opencode"


def materialize() -> None:
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)
    shutil.copy(PROFILE, SANDBOX / "opencode.json")
    shutil.copy(TOOLS, SANDBOX / "assistant-tools.json")
    shutil.copytree(PLUGINS, SANDBOX / ".opencode")


def settings_for(server: harness.OpenCodeServer, **overrides):
    values = dict(
        enabled=True,
        opencode_base_url=server.base_url,
        opencode_version="2.0.30",
        opencode_password=PASSWORD,
        opencode_profile_path=str(PROFILE),
        opencode_tools_path=str(TOOLS),
        connect_timeout_seconds=2.0,
        request_timeout_seconds=5.0,
        probe_timeout_seconds=5.0,
    )
    values.update(overrides)
    return AssistantSettings(**values)


def main() -> int:
    materialize()
    server = harness.OpenCodeServer(
        scratch=SCRATCH, sandbox=SANDBOX, port=PORT, password=PASSWORD
    )
    server.start()
    failures: list[str] = []
    try:
        try:
            urllib.request.urlopen(server.base_url + "/api/info", timeout=5)
            unauth = 200
        except urllib.error.HTTPError as error:
            unauth = error.code
        print(f"unauthenticated /api/info status: {unauth}")
        if unauth != 401:
            failures.append("unauthenticated request was not rejected")

        settings = settings_for(server)
        runtime = OpenCodeRuntime(settings)
        try:
            ready = CapabilityProbe(settings, runtime).run()
        finally:
            runtime.close()
        print(f"ready probe: {ready.state.value} ({ready.reason_code}) observed={ready.observed_version}")
        if ready.state is not RuntimeState.READY:
            failures.append(f"probe not ready: {ready.reason_code}")

        wrong = settings_for(server, opencode_version="2.0.29")
        runtime = OpenCodeRuntime(wrong)
        try:
            mismatch = CapabilityProbe(wrong, runtime).run()
        finally:
            runtime.close()
        print(f"version-mismatch probe: {mismatch.state.value} ({mismatch.reason_code})")
        if mismatch.state is not RuntimeState.INCOMPATIBLE:
            failures.append("version mismatch did not fail closed")

        disabled = settings_for(server, enabled=False)
        runtime = OpenCodeRuntime(disabled)
        try:
            off = CapabilityProbe(disabled, runtime).run()
        finally:
            runtime.close()
        print(f"disabled probe: {off.state.value} ({off.reason_code})")
        if off.state is not RuntimeState.DISABLED:
            failures.append("disabled probe was not disabled")
    finally:
        server.stop()

    if failures:
        print("FAILED: " + "; ".join(failures))
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
