import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.enums import AuctionStatus, TriggerType
from app.models.base import created_at_column, pg_enum, uuid_pk

if TYPE_CHECKING:
    from app.models.user import User

# Numbers generated reference IDs (RFQ-YYYY-NNNN). Created by migration 3295d5dfa131.
RFQ_REFERENCE_SEQ = Sequence("rfq_reference_seq", metadata=Base.metadata)


class Rfq(Base):
    """An RFQ run as a British auction. Its row is also the per-auction lock that serialises
    bid submission and closing (SELECT ... FOR UPDATE)."""

    __tablename__ = "rfqs"
    __table_args__ = (
        CheckConstraint("bid_close_at > bid_start_at", name="chk_close_after_start"),
        # Assignment rule: forced close must be later than bid close.
        CheckConstraint("forced_close_at > bid_close_at", name="chk_forced_after_close"),
        # Assignment rule: extensions never go past the forced close.
        CheckConstraint(
            "current_close_at >= bid_close_at AND current_close_at <= forced_close_at",
            name="chk_current_in_bounds",
        ),
        CheckConstraint("extension_count >= 0", name="chk_extension_count_non_negative"),
        Index("idx_rfqs_status_close", "status", "current_close_at"),
        Index("idx_rfqs_status_start", "status", "bid_start_at"),
        Index("idx_rfqs_created", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    reference_id: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_british_auction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    bid_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Original close; never changed after creation.
    bid_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Live close; moved forward by extensions, capped at forced_close_at.
    current_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forced_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AuctionStatus] = mapped_column(
        pg_enum(AuctionStatus, "auction_status"),
        nullable=False,
        default=AuctionStatus.SCHEDULED,
        server_default=AuctionStatus.SCHEDULED.value,
    )
    extension_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    buyer: Mapped["User"] = relationship()
    auction_config: Mapped["AuctionConfig"] = relationship(
        back_populates="rfq", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Rfq {self.reference_id} {self.status}>"


class AuctionConfig(Base):
    """British auction settings for one RFQ: trigger window X, extension Y, trigger type."""

    __tablename__ = "auction_configs"
    __table_args__ = (
        CheckConstraint(
            "trigger_window_minutes BETWEEN 1 AND 120", name="chk_trigger_window_range"
        ),
        CheckConstraint(
            "extension_duration_minutes BETWEEN 1 AND 120", name="chk_extension_duration_range"
        ),
    )

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="CASCADE"), primary_key=True
    )
    trigger_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    extension_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(
        pg_enum(TriggerType, "trigger_type"), nullable=False
    )

    rfq: Mapped[Rfq] = relationship(back_populates="auction_config")
