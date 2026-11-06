from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import ActivityType, AuctionStatus
from app.models import ActivityLog, Rfq, User
from scripts import seed
from tests.factories import T0


def test_seed_is_idempotent_with_stable_ids(db: Session) -> None:
    assert seed.run(db, wipe=False, now=T0) == (6, 3)
    db.flush()
    assert seed.run(db, wipe=False, now=T0) == (0, 0)

    ids = set(db.scalars(select(User.id)))
    assert ids == {u.id for u in seed.USERS}


def test_seed_creates_consistent_auctions(db: Session) -> None:
    seed.run(db, wipe=True, now=T0)
    db.flush()

    rfqs = db.scalars(select(Rfq)).all()
    statuses = sorted(r.status for r in rfqs)
    assert statuses == [AuctionStatus.ACTIVE, AuctionStatus.ACTIVE, AuctionStatus.SCHEDULED]
    for rfq in rfqs:
        assert rfq.bid_start_at < rfq.bid_close_at < rfq.forced_close_at
        assert rfq.current_close_at == rfq.bid_close_at
        assert rfq.auction_config is not None

    created = db.scalar(
        select(func.count())
        .select_from(ActivityLog)
        .where(ActivityLog.type == ActivityType.RFQ_CREATED)
    )
    assert created == 3
