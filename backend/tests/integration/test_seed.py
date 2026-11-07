from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import ActivityType, AuctionStatus
from app.models import ActivityLog, Bid, Rfq, User
from app.services.query_service import status_of
from scripts import seed
from tests.factories import T0


def test_seed_is_idempotent_with_stable_ids(db: Session) -> None:
    assert seed.run(db, wipe=False, now=T0) == (6, 5)
    assert seed.run(db, wipe=False, now=T0) == (0, 0)
    assert set(db.scalars(select(User.id))) == {u.id for u in seed.USERS}


def test_seeded_auctions_cover_every_status(db: Session) -> None:
    seed.run(db, wipe=True, now=T0)
    rfqs = {r.reference_id: r for r in db.scalars(select(Rfq))}

    assert {ref: status_of(r, T0) for ref, r in rfqs.items()} == {
        "RFQ-2026-0001": AuctionStatus.ACTIVE,
        "RFQ-2026-0002": AuctionStatus.ACTIVE,
        "RFQ-2026-0003": AuctionStatus.SCHEDULED,
        "RFQ-2026-0004": AuctionStatus.CLOSED,
        "RFQ-2026-0005": AuctionStatus.FORCE_CLOSED,
    }
    assert rfqs["RFQ-2026-0004"].extension_count == 1
    forced = rfqs["RFQ-2026-0005"]
    assert forced.extension_count == 4
    assert forced.current_close_at == forced.forced_close_at

    def count(rfq: Rfq, kind: ActivityType) -> int:
        return (
            db.scalar(
                select(func.count()).where(ActivityLog.rfq_id == rfq.id, ActivityLog.type == kind)
            )
            or 0
        )

    assert count(forced, ActivityType.EXTENSION_SKIPPED) == 1
    assert count(forced, ActivityType.BID_SUBMITTED) == 7
    assert db.scalar(select(func.count()).select_from(Bid)) == 3 + 3 + 0 + 3 + 7
