"""Shared test setup. Pytest loads this file automatically before the tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User
from app.routes.auth import current_user


@pytest.fixture
def engine():
    """A fresh in-memory database for every test, instead of PostgreSQL."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def use_test_database(engine):
    def get_test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db


@pytest.fixture
def client(engine):
    """A fake browser that calls the API, connected to the test database and
    already signed in (the sign-in itself is tested with anonymous_client)."""
    use_test_database(engine)
    app.dependency_overrides[current_user] = lambda: User(id=1, name="Tester", email="t@example.com")
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(engine):
    """A fake browser that is not signed in."""
    use_test_database(engine)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, session_factory):
    """Some services keep state between calls (caches, alert state, the
    monitor's own database connection). Every test starts clean and uses the
    test database, never the real one."""
    from app.services import monitor, otlp, telemetry

    monkeypatch.setattr(monitor, "session_factory", session_factory)
    monkeypatch.setattr(monitor, "_project_id", None)
    otlp._project_ids.clear()
    otlp._last_detection.clear()
    telemetry.reset_alerts()
    yield
