from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main


def test_health_reports_api_and_database(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database", lambda: None)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"api": "ok", "database": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["permissions-policy"] == (
        "camera=(), microphone=(), geolocation=()"
    )


def test_health_reports_database_unavailable(monkeypatch) -> None:
    def fail_connection() -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(main, "check_database", fail_connection)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"api": "ok", "database": "unavailable"}
