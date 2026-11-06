import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import uuid_pk

if TYPE_CHECKING:
    from app.models.user import User

MONEY = Numeric(14, 2)


class Bid(Base):
    """A supplier's quote. Revisions are new rows; only the latest per supplier is ranked."""

    __tablename__ = "bids"
    __table_args__ = (
        CheckConstraint("freight_charges >= 0", name="chk_freight_non_negative"),
        CheckConstraint("origin_charges >= 0", name="chk_origin_non_negative"),
        CheckConstraint("destination_charges >= 0", name="chk_destination_non_negative"),
        CheckConstraint("transit_time_days BETWEEN 1 AND 365", name="chk_transit_time_range"),
        # At most one ranked (latest) bid per supplier per RFQ.
        Index(
            "uq_bids_latest_per_supplier",
            "rfq_id",
            "supplier_id",
            unique=True,
            postgresql_where=text("is_latest"),
        ),
        Index(
            "idx_bids_ranking",
            "rfq_id",
            "total_amount",
            "submitted_at",
            postgresql_where=text("is_latest"),
        ),
        Index("idx_bids_history", "rfq_id", text("submitted_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    carrier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    freight_charges: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    origin_charges: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    destination_charges: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(
        MONEY,
        Computed("freight_charges + origin_charges + destination_charges", persisted=True),
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR", server_default=text("'INR'")
    )
    transit_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_validity_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    is_latest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    rank_at_submission: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    supplier: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<Bid {self.id} total={self.total_amount} latest={self.is_latest}>"
