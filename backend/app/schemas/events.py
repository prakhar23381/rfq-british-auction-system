"""Payloads of live events (the `data` of a WebSocket message).

`version` is the id of the auction's newest activity entry when the snapshot was taken. It
grows with every change to the auction, so a client keeps the highest version it has seen
(from REST or from events) and ignores anything older: events can arrive out of order when two
changes commit back to back.
"""

from datetime import datetime

from pydantic import Field

from app.domain.enums import AuctionStatus
from app.schemas.activity import ActivityOut
from app.schemas.bid import BidOut, ExtensionOut
from app.schemas.common import ApiModel
from app.schemas.rfq import RankedBidOut, RfqListItem, RfqOut, RfqStats

VERSION_DESCRIPTION = "Newest activity id of the auction; ignore events older than your state"


class BidSubmittedData(ApiModel):
    """`bid.submitted` on `rfq:{id}`: the new bid plus a fresh snapshot of the auction."""

    version: int = Field(description=VERSION_DESCRIPTION)
    bid: BidOut
    rank: int
    rank_label: str
    extension: ExtensionOut | None
    rfq: RfqOut
    ranking: list[RankedBidOut]
    stats: RfqStats
    activity: list[ActivityOut] = Field(description="Entries written by this bid, oldest first")


class AuctionExtendedData(ApiModel):
    """`auction.extended` on `rfq:{id}`, right after the `bid.submitted` that caused it."""

    version: int = Field(description=VERSION_DESCRIPTION)
    previous_close_at: datetime
    new_close_at: datetime
    capped: bool
    reason: str
    extension_count: int
    activity: list[ActivityOut]


class AuctionStatusData(ApiModel):
    """`auction.status` on `rfq:{id}`: the auction opened or closed."""

    version: int = Field(description=VERSION_DESCRIPTION)
    status: AuctionStatus
    rfq: RfqOut
    activity: list[ActivityOut]


class ListingItemData(ApiModel):
    """`rfq.created` / `listing.updated` on `listing`."""

    version: int = Field(description=VERSION_DESCRIPTION)
    item: RfqListItem
