"""The demo simulation, run end to end against the app on a fake clock (no waiting)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.domain.enums import ActivityType, UserRole
from app.models import ActivityLog
from scripts import simulate_bidding
from scripts.simulate_bidding import Config, Simulation
from tests.factories import T0, make_user


class ClientApi:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None, user: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        headers = {"X-User-Id": user} if user else {}
        res = self.client.request(method, path, json=body, headers=headers)
        return res.status_code, res.json()


@pytest.fixture
def people(db: Session) -> None:
    make_user(db, UserRole.BUYER, company="Acme Exports")
    for name in ("BlueWave Logistics", "Swift Cargo", "Oceanic Freight"):
        make_user(db, company=name)
    db.commit()


def run(client: TestClient, clock: FrozenClock, config: Config) -> tuple[Any, list[str]]:
    lines: list[str] = []
    clock.set(T0)
    simulation = Simulation(
        ClientApi(client), config, sleep=lambda s: clock.advance(seconds=s), out=lines.append
    )
    return simulation.run(), lines


@pytest.mark.usefixtures("people")
def test_default_demo_extends_until_the_forced_close(
    client: TestClient, clock: FrozenClock, db: Session
) -> None:
    summary, lines = run(client, clock, Config())
    assert summary.status == "FORCE_CLOSED", "\n".join(lines)
    # Close at +3 min, forced at +6 min, Y = 1 min: three extensions reach the cap.
    assert summary.extensions == 3
    assert summary.bids > 3
    assert any("extended to" in line for line in lines)
    assert any("(capped)" in line or "no extension" in line for line in lines)
    skipped = db.scalars(
        select(ActivityLog).where(ActivityLog.type == ActivityType.EXTENSION_SKIPPED)
    ).all()
    assert skipped, "bids at the cap are logged as skipped extensions"
    assert "watch it at http://localhost:5173/rfqs/" in lines[0]


@pytest.mark.usefixtures("people")
def test_one_late_bid_extends_once_then_it_closes_normally(
    client: TestClient, clock: FrozenClock
) -> None:
    # Bots bid only every 2 minutes: one undercut lands in the 1-minute window and extends the
    # close by a minute; the next bid would come after that close, so the auction just closes.
    summary, lines = run(client, clock, Config(close_in=120, forced_in=600, x=1, y=1, interval=120))
    assert summary.status == "CLOSED", "\n".join(lines)
    assert summary.extensions == 1


def test_needs_suppliers(client: TestClient, clock: FrozenClock, db: Session) -> None:
    make_user(db, UserRole.BUYER)
    db.commit()
    with pytest.raises(RuntimeError, match="make seed"):
        run(client, clock, Config())


def test_cli_rejects_a_forced_close_before_the_close(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        simulate_bidding.main(["--close-in", "300", "--forced-in", "200"])
    assert "--forced-in must be later" in capsys.readouterr().err


def test_cli_reports_an_unreachable_api(capsys: pytest.CaptureFixture[str]) -> None:
    assert simulate_bidding.main(["--api", "http://127.0.0.1:1"]) == 1
    assert "Simulation failed" in capsys.readouterr().err


def test_quote_adds_up() -> None:
    q = simulate_bidding.quote(123_457, "Line", "2026-12-31")
    total = sum(float(q[k]) for k in ("freight_charges", "origin_charges", "destination_charges"))
    assert total == 123_457


def test_http_api_sends_json_and_reads_errors() -> None:
    """The standard-library client used against a real server."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            seen["body"] = self.rfile.read(length)
            seen["user"] = self.headers["X-User-Id"]
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": {"code": "AUCTION_CLOSED", "message": "closed"}}')

        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        api = simulate_bidding.HttpApi(f"http://127.0.0.1:{server.server_port}/")
        assert api.request("GET", "/api/users") == (200, {"ok": True})
        status, body = api.request("POST", "/api/rfqs/x/bids", {"a": 1}, user="u-1")
        assert (status, body["error"]["code"]) == (409, "AUCTION_CLOSED")
        assert seen == {"body": b'{"a": 1}', "user": "u-1"}
    finally:
        server.shutdown()


@pytest.mark.usefixtures("people")
def test_a_rejected_bot_bid_is_reported_and_the_run_goes_on(
    client: TestClient, clock: FrozenClock
) -> None:
    lines: list[str] = []
    clock.set(T0)
    simulation = Simulation(
        ClientApi(client), Config(), sleep=lambda s: clock.advance(seconds=s), out=lines.append
    )
    simulation.run()
    supplier = client.get("/api/users").json()["items"][1]
    rfq_id = client.get("/api/rfqs").json()["items"][0]["id"]
    assert simulation.bid(rfq_id, supplier, 1, "2026-12-31") is False  # the auction has ended
    assert lines[-1].endswith("rejected: AUCTION_CLOSED")
