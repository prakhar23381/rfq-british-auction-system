import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AppClock, BuyerUser, DbSession
from app.domain.enums import AuctionStatus
from app.schemas.activity import ActivityListResponse
from app.schemas.bid import BidListResponse
from app.schemas.common import ErrorResponse
from app.schemas.rfq import RfqCreate, RfqDetail, RfqListResponse
from app.services import query_service, rfq_service

router = APIRouter(prefix="/rfqs", tags=["rfqs"])

ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=RfqDetail,
    status_code=status.HTTP_201_CREATED,
    responses={k: ERRORS[k] for k in (401, 403, 409, 422)},
)
def create_rfq(body: RfqCreate, buyer: BuyerUser, db: DbSession, clock: AppClock) -> RfqDetail:
    """Create an RFQ run as a British auction (buyers only)."""
    now = clock.now()
    rfq = rfq_service.create_rfq(db, body, buyer, now)
    return query_service.get_rfq_detail(db, rfq.id, now)


@router.get("", response_model=RfqListResponse)
def list_rfqs(
    db: DbSession,
    clock: AppClock,
    status: AuctionStatus | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RfqListResponse:
    """Auction listing: active first (closing soonest), then upcoming, then ended."""
    return query_service.list_rfqs(
        db, now=clock.now(), status=status, search=search, page=page, page_size=page_size
    )


@router.get("/{rfq_id}", response_model=RfqDetail, responses={404: ERRORS[404]})
def get_rfq(rfq_id: uuid.UUID, db: DbSession, clock: AppClock) -> RfqDetail:
    """Auction details: configuration, ranking (L1, L2, ...) with quote breakdown, stats."""
    return query_service.get_rfq_detail(db, rfq_id, clock.now())


@router.get("/{rfq_id}/bids", response_model=BidListResponse, responses={404: ERRORS[404]})
def list_bids(rfq_id: uuid.UUID, db: DbSession, history: bool = False) -> BidListResponse:
    """Latest bid per supplier in rank order; `history=true` returns every bid, newest first."""
    return query_service.list_bids(db, rfq_id, history=history)


@router.get("/{rfq_id}/activity", response_model=ActivityListResponse, responses={404: ERRORS[404]})
def list_activity(
    rfq_id: uuid.UUID,
    db: DbSession,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ActivityListResponse:
    """Activity log, newest first. Pass `next_before_id` as `before_id` for older entries."""
    return query_service.list_activity(db, rfq_id, before_id=before_id, limit=limit)
