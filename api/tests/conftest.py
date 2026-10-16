"""Shared fixtures for the Architecture Assistant (Slice C) tests.

These are additive fixtures only; existing suites define their own inline
fixtures and are unaffected. The assistant runtime is replaced with a
deterministic fake, so no OpenCode server is contacted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.assistant.probe import RuntimeState, get_assistant_status
from app.assistant.settings import AssistantSettings
from app.auth.security import hash_password
from app.db import Base, get_session
from app.models import (
    ArchitectureObject,
    ArchitectureState,
    CatalogField,
    CatalogObject,
    CatalogSystem,
    Tenant,
    User,
    Workspace,
)

ALL_DISCIPLINES = ["enterprise", "information", "solution", "integration"]


class FakeRuntime:
    """Deterministic stand-in for the OpenCode runtime adapter."""

    def __init__(
        self,
        *,
        text: str = "Here is what I found.",
        tools: list[dict[str, Any]] | None = None,
    ):
        self.sessions: dict[str, dict[str, Any]] = {}
        self.prompts: list[tuple[str, dict[str, Any]]] = []
        self.created = 0
        self.deleted: list[str] = []
        self.interrupted: list[str] = []
        self._text = text
        self._tools = tools or []
        self.version = "2.0.30"

    def create_session(self, body: dict[str, Any]) -> dict[str, Any]:
        self.created += 1
        session_id = f"ses_fake_{self.created}"
        self.sessions[session_id] = {"body": body}
        return {"id": session_id}

    def synthetic(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.sessions.setdefault(session_id, {})["synthetic"] = body
        return {}

    def prompt(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.prompts.append((session_id, body))
        return {}

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": self._text}]
        for tool in self._tools:
            content.append(
                {
                    "type": "tool",
                    "id": tool.get("call_id", "call_1"),
                    "name": tool["name"],
                    "state": {
                        "status": tool.get("status", "completed"),
                        "input": tool.get("input", {}),
                        "content": [{"type": "text", "text": tool.get("output", "{}")}],
                        "error": tool.get("error"),
                    },
                }
            )
        return [
            {
                "type": "assistant",
                "content": content,
                "info": {"finish": "stop"},
            }
        ]

    def interrupt(self, session_id: str) -> dict[str, Any]:
        self.interrupted.append(session_id)
        return {}

    def delete_session(self, session_id: str) -> dict[str, Any]:
        self.deleted.append(session_id)
        return {}

    def close(self) -> None:
        return None


class ReadyStatus:
    """Minimal stand-in for the Slice B runtime status."""

    def __init__(self, state: RuntimeState = RuntimeState.READY) -> None:
        self._state = state

    def refresh(self, *, force: bool = False) -> Any:  # noqa: ARG002
        from app.assistant.probe import ProbeResult

        return ProbeResult(
            state=self._state,
            reason_code="ok" if self._state is RuntimeState.READY else "runtime_unreachable",
            expected_version="2.0.30",
            observed_version="2.0.30" if self._state is RuntimeState.READY else None,
            checked_at=datetime.now(UTC),
            correlation_id="cor_test",
        )

    def public_snapshot(self, *, force: bool = False) -> dict[str, Any]:  # noqa: ARG002
        result = self.refresh()
        return {
            "assistant_enabled": True,
            "runtime_status": result.state.value,
            "expected_opencode_version": result.expected_version,
            "observed_opencode_version": result.observed_version,
            "probe_checked_at": result.checked_at.isoformat(),
            "reason_code": result.reason_code,
            "correlation_id": result.correlation_id,
        }


@dataclass
class AssistantEnv:
    client: TestClient
    sessions: sessionmaker
    runtime: FakeRuntime
    status: ReadyStatus
    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID
    current_state_id: UUID
    candidate_state_id: UUID
    object_id: UUID
    catalog_system_id: UUID
    catalog_object_id: UUID
    login_email: str = "assistant@example.test"
    login_password: str = "assistant-test-password"
    extra: dict[str, Any] = field(default_factory=dict)

    def csrf(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.client.cookies["dd_csrf"]}

    def new_session(self):
        return self.sessions()


@pytest.fixture()
def assistant_env(monkeypatch):
    monkeypatch.setattr("app.config.settings.cookie_secure", False)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with testing_sessions() as db:
            yield db

    main.app.dependency_overrides[get_session] = override_session

    tenant_id = uuid4()
    user_id = uuid4()
    current_state_id = uuid4()
    candidate_state_id = uuid4()
    object_id = uuid4()
    catalog_system_id = uuid4()
    catalog_object_id = uuid4()

    with testing_sessions.begin() as db:
        db.add(Tenant(id=tenant_id, name=f"assistant-{tenant_id}"))
        db.flush()
        db.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email="assistant@example.test",
                password_hash=hash_password("assistant-test-password"),
            )
        )
        db.flush()
        tenant_row = db.get(Tenant, tenant_id)
        tenant_row.owner_id = user_id
        db.add(
            Workspace(
                id=tenant_id,
                tenant_id=tenant_id,
                name="Assistant Workspace",
                disciplines=list(ALL_DISCIPLINES),
                assistant_enabled=True,
            )
        )
        db.flush()
        db.add(
            ArchitectureState(
                id=current_state_id,
                workspace_id=tenant_id,
                name="Current",
                state_type="current",
                nodes=[{"object_id": str(object_id), "discipline": "information"}],
                relationships=[],
            )
        )
        db.flush()
        db.add(
            ArchitectureState(
                id=candidate_state_id,
                workspace_id=tenant_id,
                name="Candidate",
                state_type="candidate",
                nodes=[{"object_id": str(object_id), "discipline": "information"}],
                relationships=[],
            )
        )
        db.flush()
        db.add(
            CatalogSystem(
                id=catalog_system_id, tenant_id=tenant_id, name="CRM", kind="application"
            )
        )
        db.flush()
        db.add(
            CatalogObject(
                id=catalog_object_id,
                tenant_id=tenant_id,
                system_id=catalog_system_id,
                name="customer",
                label="Customer",
            )
        )
        db.flush()
        db.add(
            CatalogField(
                id=uuid4(),
                tenant_id=tenant_id,
                object_id=catalog_object_id,
                name="email",
                label="Email",
                data_type="string",
            )
        )
        db.flush()
        db.add(
            ArchitectureObject(
                id=object_id, tenant_id=tenant_id, kind="information_object"
            )
        )

    runtime = FakeRuntime()
    monkeypatch.setattr("app.assistant.runtime.build_runtime", lambda: runtime)
    monkeypatch.setattr("app.assistant.routes.SessionLocal", testing_sessions)

    service_settings = AssistantSettings(tool_service_token="test-service-token")
    monkeypatch.setattr("app.assistant.routes.get_assistant_settings", lambda: service_settings)

    status = ReadyStatus()
    main.app.dependency_overrides[get_assistant_status] = lambda: status

    with TestClient(main.app) as test_client:
        csrf = test_client.get("/api/auth/csrf").json()["csrf_token"]
        response = test_client.post(
            "/api/auth/login",
            json={"email": "assistant@example.test", "password": "assistant-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield AssistantEnv(
            client=test_client,
            sessions=testing_sessions,
            runtime=runtime,
            status=status,
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id=tenant_id,
            current_state_id=current_state_id,
            candidate_state_id=candidate_state_id,
            object_id=object_id,
            catalog_system_id=catalog_system_id,
            catalog_object_id=catalog_object_id,
            extra={"service_token": "test-service-token"},
        )

    main.app.dependency_overrides.clear()
    engine.dispose()
