"""Single-container mode: the API also serves the built React app (STATIC_DIR)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

INDEX = '<!doctype html><div id="root"></div>'


@pytest.fixture
def site(tmp_path: Path) -> Iterator[TestClient]:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("outside the static dir")
    settings = get_settings().model_copy(update={"static_dir": tmp_path})
    with TestClient(create_app(settings)) as client:
        yield client


def test_client_routes_get_the_app_shell(site: TestClient) -> None:
    for path in ("/", "/rfqs/new", "/rfqs/0b6f3f1e-0000-0000-0000-000000000000", "/nope"):
        res = site.get(path)
        assert res.status_code == 200, path
        assert res.text == INDEX
        assert res.headers["cache-control"] == "no-cache"


def test_files_and_hashed_assets_are_served(site: TestClient) -> None:
    assert site.get("/favicon.svg").text == "<svg/>"
    asset = site.get("/assets/index-abc123.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    assert site.get("/assets/missing.js").status_code == 404


def test_the_api_still_wins(site: TestClient) -> None:
    assert site.get("/api/health").json()["status"] == "ok"
    missing = site.get("/api/nope")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert site.get("/api").status_code == 404
    assert site.get("/openapi.json").json()["info"]["title"]
    with site.websocket_connect("/ws") as ws:
        ws.send_json({"action": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_no_escape_from_the_static_dir(site: TestClient) -> None:
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "outside" not in site.get(path).text, path


def test_a_missing_build_fails_at_startup(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"no index\.html"):
        create_app(Settings(static_dir=tmp_path))
