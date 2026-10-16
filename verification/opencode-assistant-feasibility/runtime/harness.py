#!/usr/bin/env python3
"""Disposable harness that boots an isolated OpenCode server + mock provider.

Nothing here is part of the application. It exists only so the verification
tests can drive a real OpenCode server deterministically and offline:

* the OpenCode server runs with fully isolated XDG directories, its own port and
  its own data directory, so it never touches the developer's live OpenCode
  service, database, or credentials;
* the model provider is a local scripted mock, so no provider credential and no
  network access are required and every tool-call experiment is deterministic;
* the only OpenCode configuration is the restricted profile plus the
  verification-only plugin, both of which are copied into a scratch sandbox that
  contains nothing else.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent
PROFILE_DIR = HARNESS_DIR / "profile"
REPO_ROOT = HARNESS_DIR.parents[1]

OPENCODE_BIN = Path(
    os.environ.get("ARCHVERIFY_OPENCODE_BIN", "/home/sedu/.opencode/bin/opencode")
)
SCRATCH_ROOT = Path(os.environ.get("ARCHVERIFY_SCRATCH", "/tmp/opencode/archverify"))

MOCK_PORT = int(os.environ.get("ARCHVERIFY_MOCK_PORT", "4700"))
OPENCODE_PORT = int(os.environ.get("ARCHVERIFY_OPENCODE_PORT", "4701"))
# A deliberately recognisable secret: the credential-leak tests scan every
# browser-visible payload and event for this exact string.
MOCK_API_KEY = "MOCK-VERIFY-SECRET-KEY-8f3a91c7d5e2"


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def materialize_profile(scratch: Path, name: str = "sandbox") -> Path:
    """Copy the minimal profile into a scratch sandbox that contains nothing else."""
    sandbox = scratch / name
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(PROFILE_DIR, sandbox)
    for stale in (".verify-scopes.json", ".verify-hook-log.jsonl", ".verify-tool-log.jsonl"):
        target = sandbox / stale
        if target.exists():
            target.unlink()
    return sandbox


def spawn_server(
    scratch: Path,
    port: int,
    *,
    name: str = "sandbox",
    config: dict[str, Any] | None = None,
) -> "OpenCodeServer":
    """Materialize an isolated sandbox and start an OpenCode server on ``port``."""
    scratch.mkdir(parents=True, exist_ok=True)
    sandbox = materialize_profile(scratch, name=name)
    if config is not None:
        (sandbox / "opencode.json").write_text(json.dumps(config, indent=2))
    server = OpenCodeServer(scratch=scratch, sandbox=sandbox, port=port)
    server.start()
    return server


# ---------------------------------------------------------------------------
# Mock provider (in-process)
# ---------------------------------------------------------------------------


@dataclass
class MockProvider:
    port: int = MOCK_PORT
    _server: Any = None
    _thread: threading.Thread | None = None

    def start(self) -> None:
        sys.path.insert(0, str(HARNESS_DIR))
        import mock_provider  # noqa: PLC0415

        mock_provider.PORT = self.port
        self._module = mock_provider
        self._server = mock_provider.ThreadingHTTPServer(
            ("127.0.0.1", self.port), mock_provider.Handler
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # -- script control --------------------------------------------------
    def script(self, name: str, steps: list[dict[str, Any]]) -> None:
        self._module._SCRIPTS[name] = steps

    def reset(self) -> None:
        self._module._reset()

    @property
    def requests(self) -> list[dict[str, Any]]:
        return list(self._module._REQUESTS)

    def tool_payloads(self) -> list[dict[str, Any]]:
        """System/tool payloads as they were actually sent to the model."""
        return [
            {
                "at": index,
                "messages": request.get("messages", []),
                "tools": [t.get("function", {}).get("name") for t in request.get("tools", [])],
            }
            for index, request in enumerate(self.requests)
        ]

    def offered_tools(self) -> list[list[str]]:
        return [
            [t.get("function", {}).get("name") for t in request.get("tools", [])]
            for request in self.requests
        ]

    def request_times(self) -> list[float]:
        return list(self._module._REQUEST_TIMES)

    def last_prompt_roles(self) -> list[str]:
        """Roles of the last provider request, to prove tool results reach the model."""
        return [m.get("role") for m in (self.requests[-1].get("messages") or [])]


# ---------------------------------------------------------------------------
# OpenCode server
# ---------------------------------------------------------------------------


@dataclass
class OpenCodeServer:
    scratch: Path
    sandbox: Path
    port: int = OPENCODE_PORT
    password: str = "verify-harness-password"
    process: subprocess.Popen | None = None
    base_url: str = ""
    log_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.log_path = self.scratch / "opencode-server.log"

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "XDG_CONFIG_HOME": str(self.scratch / "xdg-config"),
                "XDG_DATA_HOME": str(self.scratch / "xdg-data"),
                "XDG_CACHE_HOME": str(self.scratch / "xdg-cache"),
                "XDG_STATE_HOME": str(self.scratch / "xdg-state"),
                "OPENCODE_DISABLE_MODELS_FETCH": "1",
                "OPENCODE_DISABLE_AUTOUPDATE": "1",
                "OPENCODE_PASSWORD": self.password,
                "OPENCODE_LOG_LEVEL": "debug",
                "MOCK_API_KEY": MOCK_API_KEY,
                "ARCHVERIFY_MOCK_URL": f"http://127.0.0.1:{MOCK_PORT}/v1",
                "ARCHVERIFY_SANDBOX": str(self.sandbox),
            }
        )
        for key in ("OPENCODE_SESSION_ID", "OPENCODE_TERMINAL"):
            env.pop(key, None)
        return env

    def start(self, timeout: float = 60.0) -> None:
        for directory in ("xdg-config", "xdg-data", "xdg-cache", "xdg-state"):
            (self.scratch / directory).mkdir(parents=True, exist_ok=True)
        self.log = self.log_path.open("w")
        self.process = subprocess.Popen(
            [
                str(OPENCODE_BIN),
                "serve",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=str(self.sandbox),
            env=self.env(),
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"opencode serve exited early ({self.process.returncode}); "
                    f"see {self.log_path}"
                )
            try:
                self.info()
                return
            except Exception as error:  # noqa: BLE001 - startup polling
                last_error = error
                time.sleep(0.4)
        raise RuntimeError(f"opencode serve did not become healthy: {last_error}")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        try:
            self.log.close()
        except Exception:  # noqa: BLE001
            pass

    # -- HTTP ------------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        *,
        timeout: float = 30.0,
        stream: bool = False,
    ):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        credentials = base64.b64encode(f"opencode:{self.password}".encode()).decode()
        request.add_header("Authorization", f"Basic {credentials}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310

    def json(
        self, method: str, path: str, body: Any | None = None, *, timeout: float = 30.0
    ) -> Any:
        with self.request(method, path, body, timeout=timeout) as response:
            raw = response.read()
        payload = json.loads(raw) if raw else None
        # The v2 HTTP surface wraps every payload in {"data": ...}.
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.json("GET", path, **kwargs)

    def post(self, path: str, body: Any | None = None, **kwargs: Any) -> Any:
        return self.json("POST", path, body, **kwargs)

    def patch(self, path: str, body: Any | None = None, **kwargs: Any) -> Any:
        return self.json("PATCH", path, body, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.json("DELETE", path, **kwargs)

    # -- conveniences -----------------------------------------------------
    def info(self) -> dict[str, Any]:
        return self.get("/api/info", timeout=5)

    def create_session(
        self,
        title: str = "verify",
        *,
        agent: str = "architecture-assistant",
        permissions: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "location": {"directory": str(self.sandbox)},
            "title": title,
            "agent": agent,
        }
        if permissions is not None:
            body["permissions"] = permissions
        return self.post("/api/session", body)

    def prompt(self, session_id: str, text: str) -> Any:
        return self.post(f"/api/session/{session_id}/prompt", {"text": text})

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        payload = self.get(f"/api/session/{session_id}/message")
        if isinstance(payload, dict):
            return payload.get("data") or payload.get("messages") or []
        return payload or []

    def wait(self, session_id: str, timeout: float = 30.0) -> Any:
        return self.post(
            f"/api/experimental/session/{session_id}/wait", {}, timeout=timeout
        )

    def interrupt(self, session_id: str) -> Any:
        return self.post(f"/api/session/{session_id}/interrupt", {})

    def delete_session(self, session_id: str) -> Any:
        return self.delete(f"/api/session/{session_id}")

    def get_session(self, session_id: str) -> Any:
        return self.get(f"/api/session/{session_id}")

    def permissions(self, session_id: str) -> Any:
        return self.get(f"/api/session/{session_id}/permission")

    def reply_permission(self, session_id: str, request_id: str, reply: str) -> Any:
        return self.post(
            f"/api/session/{session_id}/permission/{request_id}/reply", {"reply": reply}
        )

    def generate(self, session_id: str, prompt: str) -> Any:
        return self.post(f"/api/session/{session_id}/generate", {"prompt": prompt})

    def switch_model(self, session_id: str, provider_id: str, model_id: str) -> Any:
        return self.post(
            f"/api/session/{session_id}/model",
            {"model": {"providerID": provider_id, "id": model_id}},
        )

    def session_log(self, session_id: str) -> Any:
        return self.get(f"/api/experimental/session/{session_id}/log")

    # -- sandbox journals -------------------------------------------------
    def scopes_file(self) -> Path:
        return self.sandbox / ".verify-scopes.json"

    def set_scopes(self, scopes: dict[str, Any]) -> None:
        self.scopes_file().write_text(json.dumps(scopes))

    def hook_log(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.sandbox / ".verify-hook-log.jsonl")

    def tool_log(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.sandbox / ".verify-tool-log.jsonl")

    def clear_journals(self) -> None:
        for name in (".verify-hook-log.jsonl", ".verify-tool-log.jsonl"):
            path = self.sandbox / name
            if path.exists():
                path.unlink()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def assistant_text(messages: list[dict[str, Any]]) -> str:
    """Join the assistant text parts of a session transcript."""
    parts: list[str] = []
    for message in messages:
        if message.get("type") != "assistant":
            continue
        for part in message.get("content") or []:
            if part.get("type") == "text" and part.get("text"):
                parts.append(part["text"])
    return "\n".join(parts)


def assistant_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [message for message in messages if message.get("type") == "assistant"]


def tool_parts(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tool part in a session transcript, flattened for assertions."""
    results = []
    for message in messages:
        if message.get("type") != "assistant":
            continue
        for part in message.get("content") or []:
            if part.get("type") != "tool":
                continue
            state = part.get("state") or {}
            text = ""
            for item in state.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text += item.get("text") or ""
            results.append(
                {
                    "name": part.get("name"),
                    "tool_call_id": part.get("id"),
                    "status": state.get("status"),
                    "input": state.get("input"),
                    "output": text,
                    "error": (state.get("error") or {}).get("message")
                    if isinstance(state.get("error"), dict)
                    else state.get("error"),
                    "executed": part.get("executed"),
                }
            )
    return results


def wait_for(predicate, timeout: float = 25.0, interval: float = 0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


class EventCollector:
    """Reads the OpenCode `/api/event` SSE stream in the background."""

    def __init__(self, server: "OpenCodeServer", seconds: float = 4.0) -> None:
        self.server = server
        self.seconds = seconds
        self.events: list[dict[str, Any]] = []
        self.raw = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "EventCollector":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            with self.server.request("GET", "/api/event", timeout=self.seconds) as response:
                deadline = time.time() + self.seconds
                while not self._stop.is_set() and time.time() < deadline:
                    line = response.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", "replace")
                    self.raw += text
                    stripped = text.strip()
                    if stripped.startswith("data:"):
                        try:
                            self.events.append(json.loads(stripped[5:].strip()))
                        except json.JSONDecodeError:
                            continue
        except Exception:  # noqa: BLE001 - the stream ends by timeout by design
            return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.seconds + 2)

    def types(self) -> list[str]:
        return [str(event.get("type")) for event in self.events]
