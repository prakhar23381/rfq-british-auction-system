"""Test setup: point the app at the test database *before* app.db creates its engine, rebuild
the schema through Alembic once per session, and truncate all tables before each test."""

import os

from app.config import BACKEND_DIR, Settings, get_settings

os.environ["DATABASE_URL"] = Settings().test_database_url
# Live events from tests never reach a dev server's browsers.
os.environ["EVENTS_CHANNEL"] = "auction-events-test"
get_settings.cache_clear()

from collections.abc import Iterator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.clock import FrozenClock, get_clock  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.realtime.events import get_publisher  # noqa: E402
from app.services import event_service  # noqa: E402
from app.workers.scheduling import get_scheduler  # noqa: E402
from tests.fakes import RecordingPublisher, RecordingScheduler  # noqa: E402

TABLES = ["activity_logs", "auction_extensions", "bids", "auction_configs", "rfqs", "users"]


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    assert engine.url.database and engine.url.database.endswith("_test"), (
        f"Refusing to run tests against non-test database {engine.url.database!r}"
    )
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def clock() -> Iterator[FrozenClock]:
    """A frozen clock injected into the app; tests move it with clock.set / clock.advance."""
    frozen = FrozenClock(datetime(2026, 11, 10, 12, 0, tzinfo=UTC))
    app.dependency_overrides[get_clock] = lambda: frozen
    yield frozen
    app.dependency_overrides.pop(get_clock, None)


@pytest.fixture(autouse=True)
def scheduler() -> Iterator[RecordingScheduler]:
    """Every test gets a recording scheduler instead of Celery, so no real jobs are queued."""
    recorder = RecordingScheduler()
    app.dependency_overrides[get_scheduler] = lambda: recorder
    yield recorder
    app.dependency_overrides.pop(get_scheduler, None)


@pytest.fixture(autouse=True)
def publisher(monkeypatch: pytest.MonkeyPatch) -> Iterator[RecordingPublisher]:
    """Every test records live events instead of publishing them to Redis, and a bug in an
    event payload fails the test (in production it is only logged)."""
    monkeypatch.setattr(event_service, "STRICT", True)
    recorder = RecordingPublisher()
    app.dependency_overrides[get_publisher] = lambda: recorder
    yield recorder
    app.dependency_overrides.pop(get_publisher, None)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
