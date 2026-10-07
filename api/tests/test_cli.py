from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import cli
from app.db import Base
from app.models import CatalogField, CatalogObject, CatalogSystem, Tenant


class FakeSession:
    def __init__(self) -> None:
        self.added = []

    def scalar(self, _statement):
        return 0

    def add(self, instance) -> None:
        self.added.append(instance)

    def flush(self) -> None:
        pass


def test_initial_user_accepts_short_password(monkeypatch, capsys) -> None:
    session = FakeSession()
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "irmik")

    @contextmanager
    def begin():
        yield session

    monkeypatch.setattr(cli.SessionLocal, "begin", begin)

    cli.create_initial_user("operator@example.test", "Internal")

    assert len(session.added) == 2
    assert session.added[1].password_hash.startswith("$argon2id$")
    assert "Created the initial internal user" in capsys.readouterr().out


def test_initial_user_rejects_empty_password(monkeypatch) -> None:
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "")

    with pytest.raises(ValueError, match="Password must not be empty"):
        cli.create_initial_user("operator@example.test", "Internal")


def test_demo_catalog_load_is_idempotent_and_uses_catalog_models(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(cli, "SessionLocal", testing_sessions)
    with testing_sessions.begin() as db:
        db.add(Tenant(name=f"demo-{uuid4()}"))

    cli.load_demo_catalog()
    with testing_sessions() as db:
        initial_counts = (
            db.scalar(select(func.count()).select_from(CatalogSystem)),
            db.scalar(select(func.count()).select_from(CatalogObject)),
            db.scalar(select(func.count()).select_from(CatalogField)),
        )
        object_ids = list(db.scalars(select(CatalogObject.id)))
        positions = [
            list(
                db.scalars(
                    select(CatalogField.position)
                    .where(CatalogField.object_id == object_id)
                    .order_by(CatalogField.position)
                )
            )
            for object_id in object_ids
        ]

    cli.load_demo_catalog()
    with testing_sessions() as db:
        repeated_counts = (
            db.scalar(select(func.count()).select_from(CatalogSystem)),
            db.scalar(select(func.count()).select_from(CatalogObject)),
            db.scalar(select(func.count()).select_from(CatalogField)),
        )

    assert initial_counts == (4, 4, 13)
    assert repeated_counts == initial_counts
    assert all(order == list(range(len(order))) for order in positions)
    engine.dispose()
