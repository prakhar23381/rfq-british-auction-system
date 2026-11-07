"""Bidding simulation for demos: bot suppliers fight over a short British auction.

    python -m scripts.simulate_bidding                      # against http://localhost:8000
    python -m scripts.simulate_bidding --close-in 120 --forced-in 240 --x 1 --y 1

It creates an RFQ that opens in a few seconds, closes in 3 minutes and force-closes at 6
(X = 2 min, Y = 1 min, "L1 changes" trigger). After an opening round, whenever the auction is
inside its trigger window a bot that is not L1 undercuts the current L1. Each undercut changes
L1, so the auction keeps extending until the forced close caps it. Open the printed link in a
browser (as buyer and as supplier) to watch it happen live.

Needs the API, a Celery worker and Beat running (`make api`, `make worker`, `make beat`).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

ENDED = {"CLOSED", "FORCE_CLOSED"}


class Api(Protocol):
    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None, user: str | None = None
    ) -> tuple[int, dict[str, Any]]: ...


class HttpApi:
    """The real API over HTTP (standard library only)."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None, user: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if user:
            headers["X-User-Id"] = user
        req = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")


@dataclass(frozen=True)
class Config:
    close_in: int = 180  # seconds from now to the bid close
    forced_in: int = 360  # seconds from now to the forced close
    x: int = 2  # trigger window, minutes
    y: int = 1  # extension, minutes
    trigger: str = "L1_CHANGE"
    suppliers: int = 4
    interval: float = 8.0  # seconds between bot bids inside the window
    opening_price: int = 150_000
    start_in: int = 5


@dataclass(frozen=True)
class Summary:
    rfq_id: str
    reference_id: str
    status: str
    bids: int
    extensions: int
    l1_company: str | None
    l1_total: str | None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def quote(total: int, carrier: str, validity: str) -> dict[str, Any]:
    """A bid whose charges add up to `total` rupees."""
    origin = round(total * 0.06)
    destination = round(total * 0.04)
    return {
        "carrier_name": carrier,
        "freight_charges": f"{total - origin - destination}.00",
        "origin_charges": f"{origin}.00",
        "destination_charges": f"{destination}.00",
        "transit_time_days": 21,
        "quote_validity_date": validity,
        "notes": "Simulated bid",
    }


class Simulation:
    def __init__(
        self,
        api: Api,
        config: Config,
        *,
        sleep: Callable[[float], None] = time.sleep,
        out: Callable[[str], None] = print,
        web_url: str = "http://localhost:5173",
    ) -> None:
        self.api = api
        self.config = config
        self.sleep = sleep
        self.out = out
        self.web_url = web_url

    def call(
        self, method: str, path: str, body: dict[str, Any] | None = None, user: str | None = None
    ) -> dict[str, Any]:
        status, payload = self.api.request(method, path, body, user)
        if status >= 400:
            error = payload.get("error", {})
            raise RuntimeError(
                f"{method} {path} → {status} {error.get('code')}: {error.get('message')}"
            )
        return payload

    def now(self) -> datetime:
        return parse_time(self.call("GET", "/api/meta/time")["server_time"])

    def wait_until(self, moment: datetime) -> None:
        remaining = (moment - self.now()).total_seconds()
        if remaining > 0:
            self.sleep(remaining)

    def log(self, message: str) -> None:
        self.out(f"{self.now():%H:%M:%S}  {message}")

    def run(self) -> Summary:
        c = self.config
        users = self.call("GET", "/api/users")["items"]
        buyer = next(u for u in users if u["role"] == "BUYER")
        bots = [u for u in users if u["role"] == "SUPPLIER"][: c.suppliers]
        if len(bots) < 2:
            raise RuntimeError("Need at least two supplier users: run `make seed` first.")

        now = self.now()
        start = now + timedelta(seconds=c.start_in)
        rfq = self.call(
            "POST",
            "/api/rfqs",
            {
                "name": f"Simulated auction {now:%H:%M:%S}",
                "pickup_date": (now + timedelta(days=7)).date().isoformat(),
                "bid_start_at": start.isoformat(),
                "bid_close_at": (now + timedelta(seconds=c.close_in)).isoformat(),
                "forced_close_at": (now + timedelta(seconds=c.forced_in)).isoformat(),
                "auction_config": {
                    "trigger_window_minutes": c.x,
                    "extension_duration_minutes": c.y,
                    "trigger_type": c.trigger,
                },
            },
            buyer["id"],
        )["rfq"]
        rfq_id = rfq["id"]
        validity = (now + timedelta(days=30)).date().isoformat()
        self.log(f"Created {rfq['reference_id']} · watch it at {self.web_url}/rfqs/{rfq_id}")
        self.log(
            f"Close {parse_time(rfq['bid_close_at']):%H:%M:%S}, forced close "
            f"{parse_time(rfq['forced_close_at']):%H:%M:%S}, X={c.x} min, Y={c.y} min, {c.trigger}"
        )

        self.wait_until(start + timedelta(milliseconds=500))
        for i, bot in enumerate(bots):  # opening round, outside the window
            total = round(c.opening_price * (1 + 0.03 * i))
            self.bid(rfq_id, bot, total, validity)
            self.sleep(1)

        turn = 0
        while True:
            detail = self.call("GET", f"/api/rfqs/{rfq_id}")
            if detail["rfq"]["status"] in ENDED:
                break
            now = self.now()
            close = parse_time(detail["rfq"]["current_close_at"])
            window_start = close - timedelta(minutes=c.x)
            if now < window_start:
                self.sleep(min(c.interval, (window_start - now).total_seconds() + 0.5))
                continue
            ranking = detail["ranking"]
            challengers = [r for r in ranking if r["rank"] != 1]
            if ranking and challengers:
                challenger = challengers[turn % len(challengers)]
                turn += 1
                l1_total = float(ranking[0]["total_amount"])
                target = int(l1_total * 0.98) // 100 * 100
                bot = next(b for b in bots if b["id"] == challenger["supplier"]["id"])
                if not self.bid(rfq_id, bot, target, validity):
                    continue
            self.sleep(c.interval)

        final = self.call("GET", f"/api/rfqs/{rfq_id}")
        l1 = final["ranking"][0] if final["ranking"] else None
        summary = Summary(
            rfq_id=rfq_id,
            reference_id=final["rfq"]["reference_id"],
            status=final["rfq"]["status"],
            bids=final["stats"]["bid_count"],
            extensions=final["stats"]["extension_count"],
            l1_company=l1["supplier"]["company_name"] if l1 else None,
            l1_total=l1["total_amount"] if l1 else None,
        )
        self.log(
            f"{summary.status}: {summary.bids} bids, {summary.extensions} extensions, "
            f"L1 {summary.l1_company} at ₹{summary.l1_total}"
        )
        return summary

    def bid(self, rfq_id: str, bot: dict[str, Any], total: int, validity: str) -> bool:
        status, payload = self.api.request(
            "POST",
            f"/api/rfqs/{rfq_id}/bids",
            quote(total, f"{bot['company_name']} Line", validity),
            bot["id"],
        )
        if status >= 400:
            self.log(f"{bot['company_name']} bid ₹{total:,} rejected: {payload['error']['code']}")
            return False
        line = f"{bot['company_name']} bids ₹{total:,} → {payload['rank_label']}"
        extension = payload["extension"]
        if extension and extension["applied"]:
            line += f" · extended to {parse_time(extension['new_close_at']):%H:%M:%S}"
            if extension["capped"]:
                line += " (capped)"
        elif extension and extension["capped"]:
            line += " · already at the forced close, no extension"
        self.log(line)
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--web", default="http://localhost:5173")
    defaults = Config()
    parser.add_argument(
        "--close-in", type=int, default=defaults.close_in, help="seconds until the bid close"
    )
    parser.add_argument(
        "--forced-in", type=int, default=defaults.forced_in, help="seconds until the forced close"
    )
    parser.add_argument("--x", type=int, default=defaults.x, help="trigger window, minutes")
    parser.add_argument("--y", type=int, default=defaults.y, help="extension, minutes")
    parser.add_argument(
        "--trigger",
        default=defaults.trigger,
        choices=["BID_RECEIVED", "ANY_RANK_CHANGE", "L1_CHANGE"],
    )
    parser.add_argument("--suppliers", type=int, default=defaults.suppliers)
    parser.add_argument(
        "--interval", type=float, default=defaults.interval, help="seconds between bot bids"
    )
    args = parser.parse_args(argv)
    if args.forced_in <= args.close_in:
        parser.error("--forced-in must be later than --close-in")
    config = Config(
        close_in=args.close_in,
        forced_in=args.forced_in,
        x=args.x,
        y=args.y,
        trigger=args.trigger,
        suppliers=args.suppliers,
        interval=args.interval,
    )
    try:
        Simulation(HttpApi(args.api), config, web_url=args.web).run()
    except (RuntimeError, urllib.error.URLError) as err:
        print(f"Simulation failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
