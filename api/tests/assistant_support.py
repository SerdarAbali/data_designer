"""Shared helpers for the Slice B assistant tests.

The tests are hermetic: they drive the runtime adapter and the capability probe
through ``httpx.MockTransport`` so no real OpenCode server or provider is needed.
The pinned profile and tool manifest shipped under ``assistant-runtime/`` are used
as the source of truth, and are copied and mutated per test when a failure case
is required.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

from app.assistant import endpoints as ep
from app.assistant.runtime import OpenCodeRuntime
from app.assistant.settings import AssistantSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "assistant-runtime" / "opencode.json"
TOOLS_PATH = REPO_ROOT / "assistant-runtime" / "assistant-tools.json"
SNAPSHOT_PATH = REPO_ROOT / "assistant-runtime" / "openapi" / "opencode-2.0.30.json"

DISTINCTIVE_PASSWORD = "ASSISTANT-PROBE-SECRET-7c41ab90"


def make_settings(**overrides: Any) -> AssistantSettings:
    values: dict[str, Any] = {
        "enabled": True,
        "opencode_base_url": "http://opencode.test:4096",
        "opencode_version": "2.0.30",
        "opencode_password": DISTINCTIVE_PASSWORD,
        "opencode_profile_path": str(PROFILE_PATH),
        "opencode_tools_path": str(TOOLS_PATH),
        "opencode_openapi_snapshot_path": str(SNAPSHOT_PATH),
        "connect_timeout_seconds": 0.5,
        "request_timeout_seconds": 1.0,
        "stream_timeout_seconds": 1.0,
        "probe_timeout_seconds": 1.0,
        "probe_cache_seconds": 0.0,
        "max_response_bytes": 65536,
    }
    values.update(overrides)
    return AssistantSettings(**values)


def basic_auth_header(settings: AssistantSettings) -> str:
    token = base64.b64encode(
        f"{settings.opencode_auth_username}:{settings.password()}".encode()
    ).decode()
    return f"Basic {token}"


def happy_openapi() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "opencode HttpApi", "version": "0.0.1"},
        "paths": {path: ["get"] for path in sorted(ep.REQUIRED_CONTRACT_PATHS)},
    }


class Recorder:
    """Records every request that reaches the transport."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    @property
    def called(self) -> bool:
        return bool(self.calls)


def runtime_with(settings: AssistantSettings, handler: Callable[[httpx.Request], httpx.Response]):
    return OpenCodeRuntime(settings, transport=httpx.MockTransport(handler))


def probe_handler(
    *,
    info: Any | None = None,
    openapi: Any | None = None,
    recorder: Recorder | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if recorder is not None:
            recorder.calls.append(request)
        path = request.url.path
        if path == "/api/info":
            payload = {"version": "2.0.30"} if info is None else info
            return httpx.Response(200, json=payload)
        if path == "/openapi.json":
            payload = happy_openapi() if openapi is None else openapi
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return handler


def write_profile(tmp_path: Path, mutate: Callable[[dict[str, Any]], None]) -> str:
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    mutate(data)
    target = tmp_path / "opencode.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return str(target)


def write_tools(tmp_path: Path, tools: list[Mapping[str, Any]]) -> str:
    target = tmp_path / "assistant-tools.json"
    target.write_text(
        json.dumps({"namespace": "architecture", "tools": tools}), encoding="utf-8"
    )
    return str(target)


def write_openapi(tmp_path: Path, document: Mapping[str, Any]) -> str:
    target = tmp_path / "opencode-openapi.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return str(target)
