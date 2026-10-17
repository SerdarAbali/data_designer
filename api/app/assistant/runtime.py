"""Narrow OpenCode HTTP client for the Architecture Assistant.

The adapter deliberately exposes **no** generic HTTP method. Callers can only
invoke the typed lifecycle operations below; every one of them routes through
:meth:`OpenCodeRuntime._request`, which resolves the concrete path against the
hardcoded allowlist (:mod:`app.assistant.endpoints`) *before* any network access.

Guarantees:
* HTTP Basic authentication is applied server-side on every request;
* responses are read through a bounded reader and rejected before being
  retained or forwarded if they exceed ``max_response_bytes``;
* redirects are never followed and are rejected outright, so a response can
  never escape the configured OpenCode origin;
* the ``{"data": ...}`` envelope is unwrapped strictly and unknown shapes are
  rejected as protocol errors;
* errors are structured, redacted, and carry a correlation id.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from enum import Enum
from typing import Any

import httpx

from app.assistant import endpoints as ep
from app.assistant import redaction
from app.assistant.endpoints import Endpoint, EndpointNotAllowed, EnvelopePolicy
from app.assistant.settings import AssistantSettings

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class RuntimeErrorCode(str, Enum):
    ENDPOINT_NOT_ALLOWED = "endpoint_not_allowed"
    INVALID_REQUEST = "invalid_request"
    RUNTIME_UNREACHABLE = "runtime_unreachable"
    RUNTIME_TIMEOUT = "runtime_timeout"
    AUTH_FAILED = "auth_failed"
    HTTP_ERROR = "http_error"
    PROTOCOL_ERROR = "protocol_error"
    RESPONSE_TOO_LARGE = "response_too_large"
    REDIRECT_REJECTED = "redirect_rejected"


class AssistantRuntimeError(Exception):
    """A structured, redacted runtime failure.

    ``message`` is always constructed locally, never taken from an upstream
    body, so it can be surfaced without leaking credentials or internals.
    """

    def __init__(
        self,
        code: RuntimeErrorCode,
        message: str,
        *,
        status: int | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.code = code
        self.status = status
        self.correlation_id = correlation_id or redaction.correlation_id()
        super().__init__(message)


class OpenCodeRuntime:
    def __init__(
        self,
        settings: AssistantSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._secrets = (settings.password(),) if settings.has_password() else ()
        if client is not None:
            self._client = client
        else:
            self._client = httpx.Client(
                base_url=settings.opencode_base_url,
                auth=(settings.opencode_auth_username, settings.password()),
                transport=transport,
                follow_redirects=False,
                timeout=self._timeout(settings.request_timeout_seconds),
            )

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenCodeRuntime:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def base_url(self) -> str:
        return self._settings.opencode_base_url

    # -- typed operations ------------------------------------------------

    def info(self) -> Mapping[str, Any]:
        return self._request(ep.INFO, timeout=self._settings.probe_timeout_seconds)

    def openapi(self) -> Mapping[str, Any]:
        return self._request(
            ep.OPENAPI,
            timeout=self._settings.probe_timeout_seconds,
            max_bytes=self._settings.max_contract_bytes,
        )

    def create_session(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(ep.CREATE_SESSION, json_body=body)

    def get_session(self, session_id: str) -> Mapping[str, Any]:
        return self._request(ep.GET_SESSION, params={"sessionID": session_id})

    def patch_session(self, session_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(ep.PATCH_SESSION, params={"sessionID": session_id}, json_body=body)

    def delete_session(self, session_id: str) -> Mapping[str, Any]:
        return self._request(ep.DELETE_SESSION, params={"sessionID": session_id})

    def prompt(self, session_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(ep.PROMPT, params={"sessionID": session_id}, json_body=body)

    def synthetic(self, session_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(ep.SYNTHETIC, params={"sessionID": session_id}, json_body=body)

    def switch_model(self, session_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(ep.SWITCH_MODEL, params={"sessionID": session_id}, json_body=body)

    def interrupt(self, session_id: str) -> Mapping[str, Any]:
        return self._request(ep.INTERRUPT, params={"sessionID": session_id}, json_body={})

    def messages(self, session_id: str) -> Any:
        # The session transcript accumulates every step of a turn, so it is read
        # through a dedicated (still bounded) ceiling rather than the tight
        # per-response cap that governs the other lifecycle calls.
        return self._request(
            ep.MESSAGES,
            params={"sessionID": session_id},
            max_bytes=self._settings.max_transcript_bytes,
        )

    def permissions(self, session_id: str) -> Any:
        return self._request(ep.PERMISSIONS, params={"sessionID": session_id})

    def reply_permission(
        self, session_id: str, request_id: str, body: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._request(
            ep.PERMISSION_REPLY,
            params={"sessionID": session_id, "requestID": request_id},
            json_body=body,
        )

    def wait(self, session_id: str) -> Mapping[str, Any]:
        return self._request(ep.WAIT, params={"sessionID": session_id}, json_body={})

    def providers(self) -> Any:
        return self._request(ep.PROVIDERS)

    def models(self) -> Any:
        return self._request(ep.MODELS)

    def stream_events(self) -> Iterator[Mapping[str, Any]]:
        """Yield parsed events from the OpenCode SSE stream.

        Each event is bounded by ``max_stream_event_bytes``. The stream is
        live-only (no replay); the gateway keeps its own durable event log.
        """
        path = ep.EVENT.template
        self._resolve(ep.EVENT.method.value, path)
        timeout = self._timeout(self._settings.stream_timeout_seconds)
        try:
            with self._client.stream("GET", path, timeout=timeout) as response:
                self._raise_for_status(response)
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    if len(raw) > self._settings.max_stream_event_bytes:
                        raise AssistantRuntimeError(
                            RuntimeErrorCode.RESPONSE_TOO_LARGE,
                            "OpenCode stream event exceeded the configured size limit",
                        )
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        continue
        except AssistantRuntimeError:
            raise
        except httpx.TimeoutException:
            raise AssistantRuntimeError(
                RuntimeErrorCode.RUNTIME_TIMEOUT, "OpenCode event stream timed out"
            ) from None
        except httpx.HTTPError:
            raise AssistantRuntimeError(
                RuntimeErrorCode.RUNTIME_UNREACHABLE, "OpenCode runtime is unreachable"
            ) from None

    # -- internals -------------------------------------------------------

    def _timeout(self, read_seconds: float) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self._settings.connect_timeout_seconds,
            read=read_seconds,
            write=read_seconds,
            pool=self._settings.connect_timeout_seconds,
        )

    def _resolve(self, method: str, path: str) -> Endpoint:
        try:
            return ep.resolve_endpoint(method, path)
        except EndpointNotAllowed as error:
            raise AssistantRuntimeError(
                RuntimeErrorCode.ENDPOINT_NOT_ALLOWED,
                f"OpenCode endpoint is not permitted ({error.reason})",
            ) from None

    def _request(
        self,
        endpoint: Endpoint,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> Any:
        path = endpoint.path(**params) if params else endpoint.template
        resolved = self._resolve(endpoint.method.value, path)
        # Defence in depth: the resolved template must be the endpoint we asked
        # for, so a forged Endpoint cannot smuggle a different path through.
        if resolved.template != endpoint.template:
            raise AssistantRuntimeError(
                RuntimeErrorCode.ENDPOINT_NOT_ALLOWED,
                "OpenCode endpoint is not permitted",
            )

        read_timeout = timeout if timeout is not None else self._settings.request_timeout_seconds
        size_limit = max_bytes if max_bytes is not None else self._settings.max_response_bytes
        try:
            with self._client.stream(
                endpoint.method.value,
                path,
                json=json_body,
                timeout=self._timeout(read_timeout),
            ) as response:
                self._raise_for_status(response)
                raw = self._read_bounded(response, size_limit)
        except AssistantRuntimeError:
            raise
        except httpx.TimeoutException:
            raise AssistantRuntimeError(
                RuntimeErrorCode.RUNTIME_TIMEOUT, "OpenCode request timed out"
            ) from None
        except httpx.HTTPError:
            raise AssistantRuntimeError(
                RuntimeErrorCode.RUNTIME_UNREACHABLE, "OpenCode runtime is unreachable"
            ) from None

        return self._decode(raw, endpoint)

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status in _REDIRECT_STATUSES:
            raise AssistantRuntimeError(
                RuntimeErrorCode.REDIRECT_REJECTED,
                "OpenCode responded with a redirect, which is never followed",
                status=status,
            )
        if status in (401, 403):
            raise AssistantRuntimeError(
                RuntimeErrorCode.AUTH_FAILED,
                "OpenCode rejected the runtime credentials",
                status=status,
            )
        if status >= 400:
            raise AssistantRuntimeError(
                RuntimeErrorCode.HTTP_ERROR,
                f"OpenCode returned HTTP {status}",
                status=status,
            )

    def _read_bounded(self, response: httpx.Response, limit: int) -> bytes:
        buffer = bytearray()
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            buffer.extend(chunk)
            if len(buffer) > limit:
                raise AssistantRuntimeError(
                    RuntimeErrorCode.RESPONSE_TOO_LARGE,
                    "OpenCode response exceeded the configured size limit",
                    status=response.status_code,
                )
        return bytes(buffer)

    def _decode(self, raw: bytes, endpoint: Endpoint) -> Any:
        if not raw:
            if endpoint.envelope is EnvelopePolicy.BARE:
                return {}
            raise AssistantRuntimeError(
                RuntimeErrorCode.PROTOCOL_ERROR, "OpenCode returned an empty response"
            )
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise AssistantRuntimeError(
                RuntimeErrorCode.PROTOCOL_ERROR, "OpenCode returned a non-JSON response"
            ) from None

        if endpoint.envelope is EnvelopePolicy.BARE:
            if not isinstance(payload, dict):
                raise AssistantRuntimeError(
                    RuntimeErrorCode.PROTOCOL_ERROR,
                    "OpenCode returned an unexpected response shape",
                )
            return payload

        # DATA envelope: the payload must be an object carrying "data". A bare
        # object, an array, or an error envelope is rejected.
        if not isinstance(payload, dict) or "data" not in payload:
            raise AssistantRuntimeError(
                RuntimeErrorCode.PROTOCOL_ERROR,
                "OpenCode response is missing the expected data envelope",
            )
        return payload["data"]


def build_runtime() -> OpenCodeRuntime:
    """Construct the production runtime from settings.

    A single override point so tests can supply a deterministic fake without a
    live OpenCode server.
    """
    from app.assistant.settings import settings as assistant_settings

    return OpenCodeRuntime(assistant_settings)
