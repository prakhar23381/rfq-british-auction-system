"""Seed demo users and a few auctions.

    python -m scripts.seed           # add missing users; add demo RFQs if there are none
    python -m scripts.seed --reset   # wipe all data first

User ids are derived from their emails, so they stay the same across re-seeds and the
frontend's remembered "acting as" user keeps working.

Bids, extensions and closed auctions are seeded through the real services once those exist
(Stage 5), so their rankings and activity logs are produced by the actual auction rules.
"""

import argparse
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.db import SessionLocal
from app.domain.enums import ActivityType, AuctionStatus, TriggerType, UserRole
from app.models import ActivityLog, AuctionConfig, Rfq, User

SEED_NAMESPACE = uuid.UUID("6b1f2c1e-7a8d-4c55-9a43-2f0d6c1b9e10")

TABLES = ["activity_logs", "auction_extensions", "bids", "auction_configs", "rfqs", "users"]


@dataclass(frozen=True)
class SeedUser:
    name: str
    email: str
    company_name: str
    role: UserRole

    @property
    def id(self) -> uuid.UUID:
        return uuid.uuid5(SEED_NAMESPACE, self.email)


USERS = [
    SeedUser("Asha Mehta", "asha@acme-exports.example", "Acme Exports", UserRole.BUYER),
    SeedUser("Rahul Verma", "rahul@nova-retail.example", "Nova Retail", UserRole.BUYER),
    SeedUser("Kiran Rao", "kiran@bluewave.example", "BlueWave Logistics", UserRole.SUPPLIER),
    SeedUser("Meera Iyer", "meera@swiftcargo.example", "Swift Cargo", UserRole.SUPPLIER),
    SeedUser("Arjun Nair", "arjun@oceanic.example", "Oceanic Freight", UserRole.SUPPLIER),
    SeedUser("Sara Khan", "sara@transglobal.example", "TransGlobal Movers", UserRole.SUPPLIER),
]


def reset(session: Session) -> None:
    session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


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
    return created


def _add_rfq(
    session: Session,
    *,
    reference_id: str,
    name: str,
    buyer: SeedUser,
    start: datetime,
    close: datetime,
    forced: datetime,
    status: AuctionStatus,
    x: int,
    y: int,
    trigger: TriggerType,
) -> None:
    rfq = Rfq(
        reference_id=reference_id,
        name=name,
        buyer_id=buyer.id,
        pickup_date=(forced + timedelta(days=7)).date(),
        bid_start_at=start,
        bid_close_at=close,
        current_close_at=close,
        forced_close_at=forced,
        status=status,
        auction_config=AuctionConfig(
            trigger_window_minutes=x, extension_duration_minutes=y, trigger_type=trigger
        ),
    )
    session.add(rfq)
    session.flush()
    session.add(
        ActivityLog(
            rfq_id=rfq.id,
            type=ActivityType.RFQ_CREATED,
            actor_id=buyer.id,
            message=f"{buyer.company_name} created RFQ {reference_id}",
        )
    )
    if status == AuctionStatus.ACTIVE:
        session.add(
            ActivityLog(rfq_id=rfq.id, type=ActivityType.AUCTION_STARTED, message="Bidding opened")
        )


def seed_rfqs(session: Session, now: datetime) -> int:
    if session.scalar(select(func.count()).select_from(Rfq)):
        return 0
    asha, rahul = USERS[0], USERS[1]
    now = now.replace(second=0, microsecond=0)

    # Short demo auction: already open, closes in a few minutes, small X/Y so extensions
    # are easy to see while clicking through the UI.
    _add_rfq(
        session,
        reference_id="RFQ-2026-0001",
        name="Mumbai to Rotterdam, 2 x 40HC",
        buyer=asha,
        start=now - timedelta(minutes=5),
        close=now + timedelta(minutes=10),
        forced=now + timedelta(minutes=20),
        status=AuctionStatus.ACTIVE,
        x=3,
        y=2,
        trigger=TriggerType.L1_CHANGE,
    )
    _add_rfq(
        session,
        reference_id="RFQ-2026-0002",
        name="Chennai to Singapore, 1 x 20GP",
        buyer=asha,
        start=now - timedelta(minutes=30),
        close=now + timedelta(hours=2),
        forced=now + timedelta(hours=3),
        status=AuctionStatus.ACTIVE,
        x=10,
        y=5,
        trigger=TriggerType.ANY_RANK_CHANGE,
    )
    _add_rfq(
        session,
        reference_id="RFQ-2026-0003",
        name="Delhi to Dubai, air freight 800 kg",
        buyer=rahul,
        start=now + timedelta(hours=1),
        close=now + timedelta(hours=3),
        forced=now + timedelta(hours=4),
        status=AuctionStatus.SCHEDULED,
        x=15,
        y=10,
        trigger=TriggerType.BID_RECEIVED,
    )
    return 3


def run(session: Session, *, wipe: bool, now: datetime) -> tuple[int, int]:
    if wipe:
        reset(session)
    users = seed_users(session)
    session.flush()
    rfqs = seed_rfqs(session, now)
    return users, rfqs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="delete all data before seeding")
    args = parser.parse_args()

    with SessionLocal.begin() as session:
        users, rfqs = run(session, wipe=args.reset, now=utc_now())
    print(f"Seeded {users} user(s) and {rfqs} RFQ(s).")
    for u in USERS:
        print(f"  {u.role.value:<8} {u.company_name:<20} X-User-Id: {u.id}")


if __name__ == "__main__":
    main()
