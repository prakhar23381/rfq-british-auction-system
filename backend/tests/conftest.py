"""Test setup: point the app at the test database *before* app.db creates its engine, rebuild
the schema through Alembic once per session, and truncate all tables before each test."""

import os

from app.config import BACKEND_DIR, Settings, get_settings

os.environ["DATABASE_URL"] = Settings().test_database_url
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


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
