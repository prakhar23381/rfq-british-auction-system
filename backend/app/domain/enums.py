"""Domain enums shared by the engine, ORM models and API schemas.

Values equal names, so they map 1:1 to the PostgreSQL enum types.
"""

from enum import StrEnum


class UserRole(StrEnum):
    BUYER = "BUYER"
    SUPPLIER = "SUPPLIER"


class AuctionStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    FORCE_CLOSED = "FORCE_CLOSED"


class TriggerType(StrEnum):
    BID_RECEIVED = "BID_RECEIVED"
    ANY_RANK_CHANGE = "ANY_RANK_CHANGE"
    L1_CHANGE = "L1_CHANGE"


class ActivityType(StrEnum):
    RFQ_CREATED = "RFQ_CREATED"
    AUCTION_STARTED = "AUCTION_STARTED"
    BID_SUBMITTED = "BID_SUBMITTED"
    AUCTION_EXTENDED = "AUCTION_EXTENDED"
    EXTENSION_SKIPPED = "EXTENSION_SKIPPED"
    AUCTION_CLOSED = "AUCTION_CLOSED"
    AUCTION_FORCE_CLOSED = "AUCTION_FORCE_CLOSED"
