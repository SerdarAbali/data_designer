#!/usr/bin/env python3
"""Scripted OpenAI-compatible provider for OpenCode feasibility verification.

This process exists only for the verification harness. It is a *mock model*: it
never talks to a real provider and returns canned responses selected by a marker
the test places in the prompt. That makes every tool-call experiment
deterministic and free, and it lets the harness simulate a fully
prompt-injected / compromised model without needing real credentials.

Endpoints
    GET  /v1/models                  model discovery
    POST /v1/chat/completions        scripted completion (streaming or JSON)
    GET  /__requests                 every recorded provider request body
    POST /__reset                    clear recorded requests
    GET  /__health                   liveness

Script selection
    The marker ``[[SCRIPT:name]]`` is read from the newest user message. The
    script is a JSON list of steps; the step index is the number of assistant
    messages already present in the request, so step 0 is the first model call
    of a turn, step 1 the call after the first tool results, and so on.

Step shapes
    {"text": "..."}                          final assistant text
    {"tool": "name", "args": {...}}          one tool call, then continue
    {"tool_calls": [{"name": ..., "args": {...}}, ...]}
    {"tool": "name", "args": {...}, "sleep": 1.0, "partial": "..."}
                                             stream slowly (cancellation test)
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HOST = "127.0.0.1"
PORT = 4700

_LOCK = threading.Lock()
_REQUESTS: list[dict[str, Any]] = []
_REQUEST_TIMES: list[float] = []
_SCRIPTS: dict[str, list[dict[str, Any]]] = {}

_MARKER = re.compile(r"\[\[SCRIPT:([a-z0-9_\-]+)\]\]")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "archverify_get_test_context",
            "description": "Return the authoritative execution context of this tool call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "discipline": {"type": "string"},
                    "note": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archverify_echo_bounded_value",
            "description": "Echo a bounded value back to the caller.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                    "size": {"type": "integer"},
                },
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archverify_get_test_context_second",
            "description": "Second scoped test tool used for scope-isolation checks.",
            "parameters": {
                "type": "object",
                "properties": {"tag": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Built-in shell tool (must be denied).",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Built-in file read tool (must be denied).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Built-in edit tool (must be denied).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "webfetch",
            "description": "Built-in generic HTTP tool (must be denied).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
]


def _reset() -> None:
    with _LOCK:
        _REQUESTS.clear()
        _REQUEST_TIMES.clear()


def _record(body: dict[str, Any]) -> int:
    with _LOCK:
        _REQUESTS.append(body)
        _REQUEST_TIMES.append(time.time())
        return len(_REQUESTS) - 1


def _strip_marker(text: str) -> tuple[str, str | None]:
    found = _MARKER.search(text or "")
    if not found:
        return text or "", None
    return _MARKER.sub("", text or ""), found.group(1)


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
    return ""


def _assistant_count(messages: list[dict[str, Any]]) -> int:
    return sum(1 for message in messages if message.get("role") == "assistant")


def _script_for(messages: list[dict[str, Any]]) -> dict[str, Any]:
    _, marker = _strip_marker(
        " ".join(
            m.get("content")
            if isinstance(m.get("content"), str)
            else " ".join(
                p.get("text", "") for p in m.get("content") or [] if isinstance(p, dict)
            )
            for m in messages
            if m.get("role") == "user"
        )
    )
    if marker is None:
        return {"text": "no script marker; nothing to do"}
    steps = _SCRIPTS.get(marker) or [{"text": f"unknown script {marker}"}]
    index = min(_assistant_count(messages), len(steps) - 1)
    return steps[index]


def _tool_call_payload(step: dict[str, Any]) -> list[dict[str, Any]]:
    calls = step.get("tool_calls")
    if calls is None:
        if "tool" not in step:
            return []
        calls = [{"name": step["tool"], "args": step.get("args", {})}]
    payload = []
    for index, call in enumerate(calls):
        payload.append(
            {
                "index": index,
                "id": f"call_{call['name']}_{index}_{int(time.time() * 1000)}",
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call.get("args", {}), separators=(",", ":")),
                },
            }
        )
    return payload


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:  # keep the harness output quiet
        return

    # -- helpers ---------------------------------------------------------
    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return {}

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/__health"):
            self._send_json(200, {"ok": True})
            return
        if self.path.startswith("/__requests"):
            with _LOCK:
                self._send_json(200, list(_REQUESTS))
            return
        if self.path.startswith("/v1/models"):
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": "mock-tool-model", "object": "model", "owned_by": "harness"}
                    ],
                },
            )
            return
        self._send_json(404, {"error": {"message": f"unknown path {self.path}"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/__reset"):
            _reset()
            self._send_json(200, {"ok": True})
            return
        if self.path.startswith("/__script"):
            body = self._read_body()
            with _LOCK:
                _SCRIPTS[body["name"]] = body.get("steps", [])
            self._send_json(200, {"ok": True})
            return
        if not self.path.startswith("/v1/chat/completions"):
            self._send_json(404, {"error": {"message": f"unknown path {self.path}"}})
            return

        body = self._read_body()
        body.pop("__recorded_at", None)
        _record(body)
        messages = body.get("messages") or []
        step = _script_for(messages)
        calls = _tool_call_payload(step)
        sleep = float(step.get("sleep") or 0.0)
        partial = step.get("partial")

        if body.get("stream"):
            self._stream(step, calls, partial, sleep)
            return

        message: dict[str, Any] = {"role": "assistant", "content": step.get("text")}
        if calls:
            message["content"] = step.get("text")
            message["tool_calls"] = [
                {k: v for k, v in call.items() if k != "index"} for call in calls
            ]
        self._send_json(
            200,
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model") or "mock-tool-model",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if calls else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    # -- streaming -------------------------------------------------------
    def _chunk(self, delta: dict[str, Any], finish: str | None = None) -> None:
        payload = {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-tool-model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
        self.wfile.flush()

    def _stream(
        self,
        step: dict[str, Any],
        calls: list[dict[str, Any]],
        partial: str | None,
        sleep: float,
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_chunk(data: bytes) -> None:
            self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
            self.wfile.flush()

        def chunk(delta: dict[str, Any], finish: str | None = None) -> None:
            payload = {
                "id": "chatcmpl-mock",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "mock-tool-model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            write_chunk(f"data: {json.dumps(payload)}\n\n".encode())

        chunk({"role": "assistant", "content": ""})
        if partial:
            for word in partial.split(" "):
                chunk({"content": f"{word} "})
                time.sleep(sleep or 0.4)
        elif step.get("text"):
            chunk({"content": str(step["text"])})
        for call in calls:
            chunk({"tool_calls": [call]})
        chunk({}, "tool_calls" if calls else "stop")
        write_chunk(b"data: [DONE]\n\n")
        write_chunk(b"")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"mock provider listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
