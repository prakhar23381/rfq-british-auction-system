import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Rfq


def lock_rfq(db: Session, rfq_id: uuid.UUID, *, skip_locked: bool = False) -> Rfq | None:
    """SELECT ... FOR UPDATE on the RFQ row: the per-auction lock that serialises bids and
    lifecycle jobs. None if the RFQ does not exist (or, with skip_locked, is locked).

    populate_existing makes the session overwrite an RFQ it already holds with the row as
    locked; otherwise it would keep its older in-memory values (e.g. a stale status)."""
    return db.scalars(
        select(Rfq)
        .where(Rfq.id == rfq_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    ).one_or_none()
