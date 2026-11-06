import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.domain.enums import ActivityType, TriggerType
from app.models.base import created_at_column, pg_enum, uuid_pk


class AuctionExtension(Base):
    """One applied extension of an auction's close time (structured data for metrics)."""

    __tablename__ = "auction_extensions"
    __table_args__ = (
        CheckConstraint("new_close_at > previous_close_at", name="chk_extension_moves_forward"),
        Index("idx_ext_rfq", "rfq_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    bid_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bids.id"), nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(
        pg_enum(TriggerType, "trigger_type"), nullable=False
    )
    previous_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class ActivityLog(Base):
    """Human-readable auction timeline: bids, extensions (with reason), start and close."""

    __tablename__ = "activity_logs"
    __table_args__ = (Index("idx_activity_rfq", "rfq_id", text("id DESC")),)

    # Sequence id gives a strict order even when timestamps collide; also the pagination cursor.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[ActivityType] = mapped_column(
        pg_enum(ActivityType, "activity_type"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    bid_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bids.id"))
    extension_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("auction_extensions.id"))
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    # "metadata" is reserved on declarative classes, so the attribute is named `meta`.
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_column()
