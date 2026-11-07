from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import ActivityType, AuctionStatus
from app.models import ActivityLog, Bid, Rfq, User
from app.services.query_service import status_of
from scripts import seed
from tests.factories import T0
from tests.fakes import RecordingScheduler


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


def test_seed_brings_stored_status_up_to_date_and_queues_jobs(db: Session) -> None:
    jobs = RecordingScheduler()
    seed.run(db, wipe=True, now=T0, scheduler=jobs)
    rfqs = {r.reference_id: r for r in db.scalars(select(Rfq))}

    # The sweep at the end of seeding stores what the times say.
    assert {ref: r.status for ref, r in rfqs.items()} == {
        ref: status_of(r, T0) for ref, r in rfqs.items()
    }
    forced = rfqs["RFQ-2026-0005"]
    last = db.scalars(
        select(ActivityLog).where(ActivityLog.rfq_id == forced.id).order_by(ActivityLog.id.desc())
    ).first()
    assert last is not None
    assert last.type == ActivityType.AUCTION_FORCE_CLOSED
    assert last.created_at == forced.forced_close_at
    assert forced.closed_at == forced.forced_close_at

    # Jobs only for auctions that are still open or upcoming.
    upcoming = rfqs["RFQ-2026-0003"]
    assert jobs.starts == [(upcoming.id, upcoming.bid_start_at)]
    assert {rfq_id for rfq_id, _ in jobs.closes} == {
        rfqs[ref].id for ref in ("RFQ-2026-0001", "RFQ-2026-0002", "RFQ-2026-0003")
    }
