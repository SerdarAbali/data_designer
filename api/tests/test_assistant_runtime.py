"""Narrow runtime adapter tests (Slice B).

Covers required proofs 3, 5, 6, 7, 12 and the "reject before network access"
guarantee, plus error redaction.
"""

from __future__ import annotations

import inspect

import httpx
import pytest

from app.assistant import endpoints as ep
from app.assistant.runtime import AssistantRuntimeError, RuntimeErrorCode
from tests.assistant_support import (
    DISTINCTIVE_PASSWORD,
    Recorder,
    basic_auth_header,
    make_settings,
    runtime_with,
)


def test_basic_auth_is_applied_server_side() -> None:
    settings = make_settings()
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.calls.append(request)
        return httpx.Response(200, json={"version": "2.0.30"})

    runtime = runtime_with(settings, handler)
    try:
        assert runtime.info() == {"version": "2.0.30"}
    finally:
        runtime.close()

    assert recorder.called
    assert recorder.calls[0].headers["authorization"] == basic_auth_header(settings)
    assert DISTINCTIVE_PASSWORD not in recorder.calls[0].url.path


def test_exact_basic_credentials_are_sent_and_rejections_map_to_auth_failed() -> None:
    expected = basic_auth_header(make_settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != expected:
            return httpx.Response(401, json={"error": {"message": "unauthorized"}})
        return httpx.Response(200, json={"version": "2.0.30"})

    runtime = runtime_with(make_settings(), handler)
    try:
        assert runtime.info() == {"version": "2.0.30"}
    finally:
        runtime.close()

    wrong = runtime_with(make_settings(opencode_password="not-the-password"), handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            wrong.info()
        assert raised.value.code is RuntimeErrorCode.AUTH_FAILED
    finally:
        wrong.close()


def test_data_envelope_is_unwrapped_strictly() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"id": "ses_1"}})

    runtime = runtime_with(make_settings(), handler)
    try:
        assert runtime.create_session({"title": "t"}) == {"id": "ses_1"}
    finally:
        runtime.close()


def test_data_envelope_allows_location_sibling() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"location": {"directory": "/sandbox"}, "data": []})

    runtime = runtime_with(make_settings(), handler)
    try:
        assert runtime.providers() == []
    finally:
        runtime.close()


def test_missing_data_envelope_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "ses_1"})

    runtime = runtime_with(make_settings(), handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.create_session({"title": "t"})
        assert raised.value.code is RuntimeErrorCode.PROTOCOL_ERROR
    finally:
        runtime.close()


def test_non_object_payload_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    runtime = runtime_with(make_settings(), handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.create_session({"title": "t"})
        assert raised.value.code is RuntimeErrorCode.PROTOCOL_ERROR
    finally:
        runtime.close()


def test_bare_endpoint_requires_an_object() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    runtime = runtime_with(make_settings(), handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.info()
        assert raised.value.code is RuntimeErrorCode.PROTOCOL_ERROR
    finally:
        runtime.close()


def test_oversized_response_is_rejected() -> None:
    settings = make_settings(max_response_bytes=4096)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 200_000)

    runtime = runtime_with(settings, handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.info()
        assert raised.value.code is RuntimeErrorCode.RESPONSE_TOO_LARGE
    finally:
        runtime.close()


def test_redirect_is_rejected_and_never_followed() -> None:
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.calls.append(request)
        if request.url.host == "opencode.test":
            return httpx.Response(302, headers={"location": "http://evil.example/api/info"})
        return httpx.Response(200, json={"version": "2.0.30"})

    runtime = runtime_with(make_settings(), handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.info()
        assert raised.value.code is RuntimeErrorCode.REDIRECT_REJECTED
    finally:
        runtime.close()

    # Only the original origin was ever contacted.
    assert {call.url.host for call in recorder.calls} == {"opencode.test"}


def test_timeout_is_mapped() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream too slow")

    runtime = runtime_with(make_settings(), handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.info()
        assert raised.value.code is RuntimeErrorCode.RUNTIME_TIMEOUT
    finally:
        runtime.close()


def test_denied_endpoint_is_rejected_before_network_access() -> None:
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.calls.append(request)
        return httpx.Response(200, json={"data": {"secret": DISTINCTIVE_PASSWORD}})

    runtime = runtime_with(make_settings(), handler)
    forged = ep.Endpoint(ep.HttpMethod.GET, "/api/config")
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime._request(forged)
        assert raised.value.code is RuntimeErrorCode.ENDPOINT_NOT_ALLOWED
    finally:
        runtime.close()

    assert not recorder.called


def test_runtime_exposes_no_generic_http_method() -> None:
    runtime = runtime_with(make_settings(), lambda _request: httpx.Response(200, json={}))
    try:
        for forbidden in ("request", "get", "post", "fetch", "proxy", "forward"):
            assert not hasattr(runtime, forbidden)
        for name in dir(runtime):
            if name.startswith("_"):
                continue
            attribute = getattr(runtime, name)
            if not callable(attribute):
                continue
            parameters = set(inspect.signature(attribute).parameters)
            assert "path" not in parameters
            assert "url" not in parameters
    finally:
        runtime.close()


def test_errors_are_redacted() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        # An upstream body that leaks the secret must never surface in the error.
        return httpx.Response(500, content=DISTINCTIVE_PASSWORD.encode())

    runtime = runtime_with(make_settings(), handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.info()
    finally:
        runtime.close()

    error = raised.value
    assert error.code is RuntimeErrorCode.HTTP_ERROR
    assert DISTINCTIVE_PASSWORD not in str(error)
    assert DISTINCTIVE_PASSWORD not in repr(error.__dict__)
    assert error.correlation_id.startswith("cor_")


def test_response_too_large_error_never_contains_the_body() -> None:
    settings = make_settings(max_response_bytes=1024)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=DISTINCTIVE_PASSWORD.encode() * 100)

    runtime = runtime_with(settings, handler)
    try:
        with pytest.raises(AssistantRuntimeError) as raised:
            runtime.info()
        assert raised.value.code is RuntimeErrorCode.RESPONSE_TOO_LARGE
        assert DISTINCTIVE_PASSWORD not in str(raised.value)
    finally:
        runtime.close()
