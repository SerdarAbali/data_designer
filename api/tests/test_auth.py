from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.responses import Response

from app import main
from app.auth.rate_limit import login_rate_limiter
from app.auth.routes import set_auth_cookies
from app.auth.security import hash_password
from app.config import settings
from app.db import Base, get_session
from app.models import AuthSession, Tenant, User


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with testing_sessions() as db:
            yield db

    main.app.dependency_overrides[get_session] = override_session
    with testing_sessions.begin() as db:
        tenant = Tenant(name=f"internal-{uuid4()}")
        db.add(tenant)
        db.flush()
        db.add(
            User(
                tenant_id=tenant.id,
                email="operator@example.test",
                password_hash=hash_password("a-long-test-password"),
            )
        )
    login_rate_limiter._attempts.clear()
    with TestClient(main.app) as test_client:
        yield test_client, testing_sessions
    main.app.dependency_overrides.clear()
    login_rate_limiter._attempts.clear()
    engine.dispose()


def login(client: TestClient, password: str = "a-long-test-password"):
    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    token = csrf.json()["csrf_token"]
    return client.post(
        "/api/auth/login",
        json={"email": "OPERATOR@example.test", "password": password},
        headers={"X-CSRF-Token": token},
    )


def test_login_sets_secure_session_and_current_user(client) -> None:
    test_client, _ = client

    response = login(test_client)

    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    assert response.cookies.get("dd_session")
    assert response.cookies.get("dd_csrf")
    assert "httponly" in response.headers["set-cookie"].lower()

    current = test_client.get("/api/auth/me")
    assert current.status_code == 200
    assert current.json()["email"] == "operator@example.test"
    assert current.json()["tenant_name"].startswith("internal-")


def test_password_hash_uses_argon2id() -> None:
    password_hash = hash_password("a-long-test-password")

    assert password_hash.startswith("$argon2id$")


def test_secure_cookie_flags_for_https_deployment(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = Response()

    set_auth_cookies(response, "session", "csrf")

    session_cookie, csrf_cookie = response.headers.getlist("set-cookie")
    assert "httponly" in session_cookie.lower()
    assert "secure" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert "secure" in csrf_cookie.lower()


def test_invalid_password_and_unauthenticated_access(client) -> None:
    test_client, _ = client

    assert test_client.get("/api/auth/me").status_code == 401
    response = login(test_client, password="incorrect-password")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_missing_csrf(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/api/auth/login",
        json={"email": "operator@example.test", "password": "a-long-test-password"},
    )

    assert response.status_code == 403


def test_logout_revokes_session_and_clears_cookies(client) -> None:
    test_client, testing_sessions = client
    assert login(test_client).status_code == 200
    csrf = test_client.cookies["dd_csrf"]
    session_token = test_client.cookies["dd_session"]

    response = test_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    assert response.status_code == 204
    assert "dd_session" not in test_client.cookies
    assert test_client.get("/api/auth/me").status_code == 401
    with testing_sessions() as db:
        auth_session = db.scalar(select(AuthSession))
        assert auth_session is not None
        assert auth_session.token_hash != session_token
        assert len(auth_session.token_hash) == 64
        assert auth_session.revoked_at is not None


def test_logout_rejects_invalid_csrf(client) -> None:
    test_client, _ = client
    assert login(test_client).status_code == 200

    response = test_client.post("/api/auth/logout", headers={"X-CSRF-Token": "invalid"})

    assert response.status_code == 403


def test_expired_session_is_rejected(client) -> None:
    test_client, testing_sessions = client
    assert login(test_client).status_code == 200
    token = test_client.cookies["dd_session"]
    from app.auth.dependencies import token_digest

    with testing_sessions.begin() as db:
        auth_session = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(token))
        )
        assert auth_session is not None
        auth_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    assert test_client.get("/api/auth/me").status_code == 401


def test_login_rate_limit_returns_retry_after(client, monkeypatch) -> None:
    test_client, _ = client
    monkeypatch.setattr("app.auth.rate_limit.settings.login_rate_limit", 2)

    assert login(test_client, password="wrong").status_code == 401
    assert login(test_client, password="wrong").status_code == 401
    response = login(test_client, password="wrong")

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
