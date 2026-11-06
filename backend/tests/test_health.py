from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.redis_client import get_redis
from app.db import get_db
from app.main import app


def _client(db_ok: bool, redis_ok: bool) -> TestClient:
    db = MagicMock()
    if not db_ok:
        db.execute.side_effect = RuntimeError("db down")
    redis = MagicMock()
    if not redis_ok:
        redis.ping.side_effect = RuntimeError("redis down")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_health_ok() -> None:
    res = _client(db_ok=True, redis_ok=True).get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"
    assert body["server_time"]


def test_health_reports_failing_dependency() -> None:
    body = _client(db_ok=True, redis_ok=False).get("/api/health").json()
    assert body["status"] == "error"
    assert body["db"] == "ok"
    assert body["redis"] == "error"
