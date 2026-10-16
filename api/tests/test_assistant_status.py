"""Application-owned assistant status endpoint tests (Slice B).

Covers required proofs 4, 18, 20: the browser-facing status never contains
credentials, a disabled assistant never contacts OpenCode, and existing
application functionality is unaffected.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.assistant.probe import AssistantRuntimeStatus, get_assistant_status
from app.auth.dependencies import AuthenticatedUser, get_current_user
from tests.assistant_support import (
    DISTINCTIVE_PASSWORD,
    make_settings,
    probe_handler,
    runtime_with,
)


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="assistant@example.test",
        tenant_name="Example",
    )


def _client(status: AssistantRuntimeStatus) -> TestClient:
    main.app.dependency_overrides[get_current_user] = _fake_user
    main.app.dependency_overrides[get_assistant_status] = lambda: status
    return TestClient(main.app)


def _clear_overrides() -> None:
    main.app.dependency_overrides.pop(get_current_user, None)
    main.app.dependency_overrides.pop(get_assistant_status, None)


def test_status_reports_ready_and_never_leaks_credentials() -> None:
    settings = make_settings()
    runtime = runtime_with(settings, probe_handler())
    status = AssistantRuntimeStatus(settings, runtime=runtime)
    client = _client(status)
    try:
        response = client.get("/api/assistant/status")
    finally:
        _clear_overrides()
        runtime.close()

    assert response.status_code == 200
    body = response.json()
    assert body["runtime_status"] == "ready"
    assert body["assistant_enabled"] is True
    assert body["expected_opencode_version"] == "2.0.30"
    assert body["observed_opencode_version"] == "2.0.30"
    assert body["reason_code"] == "ok"
    assert body["correlation_id"].startswith("cor_")

    text = response.text.lower()
    assert DISTINCTIVE_PASSWORD.lower() not in text
    for forbidden in ("password", "authorization", "api_key", "opencode.test", "traceback"):
        assert forbidden not in text


def test_status_requires_authentication() -> None:
    _clear_overrides()
    response = TestClient(main.app).get("/api/assistant/status")
    assert response.status_code == 401


def test_disabled_status_does_not_contact_opencode() -> None:
    calls: list[str] = []

    def factory():  # pragma: no cover - must never be called
        calls.append("constructed")
        raise AssertionError("runtime must not be constructed while disabled")

    status = AssistantRuntimeStatus(make_settings(enabled=False), runtime_factory=factory)
    client = _client(status)
    try:
        response = client.get("/api/assistant/status")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["assistant_enabled"] is False
    assert body["runtime_status"] == "disabled"
    assert body["reason_code"] == "assistant_disabled"
    assert calls == []


def test_application_health_unaffected_when_assistant_disabled(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database", lambda: None)
    status = AssistantRuntimeStatus(make_settings(enabled=False))
    client = _client(status)
    try:
        assert client.get("/health").json() == {"api": "ok", "database": "ok"}
        assistant = client.get("/api/assistant/status")
    finally:
        _clear_overrides()

    assert assistant.status_code == 200
    assert assistant.json()["runtime_status"] == "disabled"


def test_only_the_status_route_is_exposed() -> None:
    paths = {
        route.path
        for route in main.app.routes
        if getattr(route, "path", "").startswith("/api/assistant")
    }
    assert paths == {"/api/assistant/status"}
