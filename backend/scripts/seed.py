"""Seed demo users and auctions.

    python -m scripts.seed           # add missing users; add demo auctions if there are none
    python -m scripts.seed --reset   # wipe all data first

User ids are derived from their emails, so they stay the same across re-seeds and the
frontend's remembered "acting as" user keeps working.

Auctions and bids are created through the real services on a simulated clock, so every
ranking, extension and activity entry is produced by the actual auction rules:

- RFQ-2026-0001  open, closes ~10 min after seeding, small X/Y: good for trying extensions
- RFQ-2026-0002  open for ~2 hours, "any rank change" trigger
- RFQ-2026-0003  upcoming
- RFQ-2026-0004  closed (extended once, then ended before its forced close)
- RFQ-2026-0005  force closed (the HLD worked example: four extensions, then the cap)
"""

import argparse
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock, utc_now
from app.db import SessionLocal
from app.domain.enums import TriggerType, UserRole
from app.models import Rfq, User
from app.schemas.bid import BidCreate
from app.schemas.rfq import AuctionConfigIn, RfqCreate
from app.services import bid_service, rfq_service

SEED_NAMESPACE = uuid.UUID("6b1f2c1e-7a8d-4c55-9a43-2f0d6c1b9e10")

TABLES = ["activity_logs", "auction_extensions", "bids", "auction_configs", "rfqs", "users"]


@dataclass(frozen=True)
class SeedUser:
    name: str
    email: str
    company_name: str
    role: UserRole
    carrier: str = ""

    @property
    def id(self) -> uuid.UUID:
        return uuid.uuid5(SEED_NAMESPACE, self.email)


ASHA = SeedUser("Asha Mehta", "asha@acme-exports.example", "Acme Exports", UserRole.BUYER)
RAHUL = SeedUser("Rahul Verma", "rahul@nova-retail.example", "Nova Retail", UserRole.BUYER)
BLUEWAVE = SeedUser("Kiran Rao", "kiran@bluewave.example", "BlueWave Logistics",
                    UserRole.SUPPLIER, "BlueWave Ocean Lines")  # fmt: skip
SWIFT = SeedUser("Meera Iyer", "meera@swiftcargo.example", "Swift Cargo",
                 UserRole.SUPPLIER, "Swift Sea Freight")  # fmt: skip
OCEANIC = SeedUser("Arjun Nair", "arjun@oceanic.example", "Oceanic Freight",
                   UserRole.SUPPLIER, "Oceanic Container Line")  # fmt: skip
TRANSGLOBAL = SeedUser("Sara Khan", "sara@transglobal.example", "TransGlobal Movers",
                       UserRole.SUPPLIER, "TransGlobal Shipping")  # fmt: skip

USERS = [ASHA, RAHUL, BLUEWAVE, SWIFT, OCEANIC, TRANSGLOBAL]

ORIGIN_CHARGES = Decimal(8000)
DESTINATION_CHARGES = Decimal(6500)


def reset(session: Session) -> None:
    session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    session.commit()


def seed_users(session: Session) -> int:
    existing = set(session.scalars(select(User.email)))
    created = 0
    for u in USERS:
        if u.email in existing:
            continue
        session.add(
            User(id=u.id, name=u.name, email=u.email, company_name=u.company_name, role=u.role)
        )
        created += 1
    session.commit()
    return created


class Scenario:
    """Creates one auction and replays bids on a simulated clock."""

    def __init__(
        self,
        session: Session,
        *,
        reference_id: str,
        name: str,
        buyer: SeedUser,
        start: datetime,
        close: datetime,
        forced: datetime,
        x: int,
        y: int,
        trigger: TriggerType,
        pickup: date,
    ) -> None:
        self.session = session
        self.clock = FrozenClock(min(start, utc_now()) - timedelta(minutes=10))
        self.pickup = pickup
        self.rfq = rfq_service.create_rfq(
            session,
            RfqCreate(
                reference_id=reference_id,
                name=name,
                bid_start_at=start,
                bid_close_at=close,
                forced_close_at=forced,
                pickup_date=pickup,
                auction_config=AuctionConfigIn(
                    trigger_window_minutes=x, extension_duration_minutes=y, trigger_type=trigger
                ),
            ),
            session.get_one(User, buyer.id),
            self.clock.now(),
        )

    def bid(self, supplier: SeedUser, total: int, when: datetime, transit_days: int = 24) -> None:
        self.clock.set(when)
        body = BidCreate(
            carrier_name=supplier.carrier,
            freight_charges=Decimal(total) - ORIGIN_CHARGES - DESTINATION_CHARGES,
            origin_charges=ORIGIN_CHARGES,
            destination_charges=DESTINATION_CHARGES,
            transit_time_days=transit_days,
            quote_validity_date=self.pickup + timedelta(days=30),
        )
        supplier_user = self.session.get_one(User, supplier.id)
        bid_service.submit_bid(self.session, self.rfq.id, supplier_user, body, self.clock)


def seed_rfqs(session: Session, now: datetime) -> int:
    if session.scalar(select(func.count()).select_from(Rfq)):
        return 0
    n = now.replace(second=0, microsecond=0)
    m = timedelta(minutes=1)
    soon = (n + timedelta(days=14)).date()

    demo = Scenario(session, reference_id="RFQ-2026-0001", name="Mumbai to Rotterdam, 2 x 40HC",
                    buyer=ASHA, start=n - 5 * m, close=n + 10 * m, forced=n + 20 * m, x=3, y=2,
                    trigger=TriggerType.L1_CHANGE, pickup=soon)  # fmt: skip
    demo.bid(BLUEWAVE, 152_000, n - 4 * m, transit_days=28)
    demo.bid(SWIFT, 149_500, n - 3 * m, transit_days=26)
    demo.bid(OCEANIC, 151_000, n - 2 * m, transit_days=25)

    long = Scenario(session, reference_id="RFQ-2026-0002", name="Chennai to Singapore, 1 x 20GP",
                    buyer=ASHA, start=n - 30 * m, close=n + 120 * m, forced=n + 180 * m, x=10,
                    y=5, trigger=TriggerType.ANY_RANK_CHANGE, pickup=soon)  # fmt: skip
    long.bid(TRANSGLOBAL, 64_000, n - 25 * m, transit_days=9)
    long.bid(OCEANIC, 61_500, n - 20 * m, transit_days=10)
    long.bid(TRANSGLOBAL, 60_800, n - 12 * m, transit_days=9)

    Scenario(session, reference_id="RFQ-2026-0003", name="Delhi to Dubai, air freight 800 kg",
             buyer=RAHUL, start=n + 60 * m, close=n + 180 * m, forced=n + 240 * m, x=15, y=10,
             trigger=TriggerType.BID_RECEIVED, pickup=soon)  # fmt: skip

    close = n - 120 * m
    closed = Scenario(session, reference_id="RFQ-2026-0004",
                      name="Nhava Sheva to Jebel Ali, 1 x 40HC", buyer=RAHUL, start=close - 60 * m,
                      close=close, forced=close + 30 * m, x=10, y=5,
                      trigger=TriggerType.BID_RECEIVED, pickup=soon)  # fmt: skip
    closed.bid(SWIFT, 98_000, close - 40 * m, transit_days=6)
    closed.bid(BLUEWAVE, 96_500, close - 25 * m, transit_days=7)
    closed.bid(SWIFT, 95_900, close - 6 * m, transit_days=6)  # in window: +5 min, then quiet

    # The HLD worked example, scaled to real money: four extensions, then the forced close.
    close = n - 180 * m
    forced = Scenario(session, reference_id="RFQ-2026-0005", name="Mundra to Felixstowe, 3 x 40HC",
                      buyer=ASHA, start=close - 60 * m, close=close, forced=close + 20 * m, x=10,
                      y=5, trigger=TriggerType.L1_CHANGE, pickup=soon)  # fmt: skip
    for supplier, total, minutes in [
        (BLUEWAVE, 210_000, -20),
        (SWIFT, 205_000, -8),
        (SWIFT, 203_000, -2),
        (BLUEWAVE, 201_000, 1),
        (SWIFT, 199_500, 8),
        (BLUEWAVE, 198_000, 12),
        (SWIFT, 196_000, 16),
    ]:
        forced.bid(supplier, total, close + minutes * m)
    return 5


def run(session: Session, *, wipe: bool, now: datetime) -> tuple[int, int]:
    if wipe:
        reset(session)
    users = seed_users(session)
    rfqs = seed_rfqs(session, now)
    return users, rfqs


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo users and auctions")
    parser.add_argument("--reset", action="store_true", help="delete all data before seeding")
    args = parser.parse_args()

    with SessionLocal() as session:
        users, rfqs = run(session, wipe=args.reset, now=utc_now())
    print(f"Seeded {users} user(s) and {rfqs} RFQ(s).")
    for u in USERS:
        print(f"  {u.role.value:<8} {u.company_name:<20} X-User-Id: {u.id}")


if __name__ == "__main__":
    main()
