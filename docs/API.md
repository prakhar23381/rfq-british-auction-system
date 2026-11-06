# API Reference — British Auction RFQ System

Base URL: `http://localhost:8000`. The interactive OpenAPI reference is served at `/docs` (Swagger UI) and `/openapi.json`; this page summarises the contract.

## Conventions

- JSON bodies, `snake_case` field names.
- Timestamps are ISO-8601 in UTC (`2026-11-07T12:00:00Z`); dates are `YYYY-MM-DD`.
- Money is sent as a **string** with two decimals (`"125000.00"`) to avoid floating-point errors.
- Every response includes `server_time` so clients can correct their clock for countdowns.
- **Acting user:** mutating requests send `X-User-Id: <uuid>` (one of the seeded users from `GET /api/users`).

### Errors

```json
{
  "error": {
    "code": "FORCED_CLOSE_NOT_AFTER_CLOSE",
    "message": "Forced close time must be later than the bid close time.",
    "details": [{ "field": "forced_close_at", "message": "Must be later than bid_close_at" }]
  },
  "server_time": "2026-11-07T12:00:00Z"
}
```

| HTTP | Code | When |
|---|---|---|
| 401 | `UNAUTHENTICATED` | `X-User-Id` missing or unknown |
| 403 | `FORBIDDEN` | Wrong role (e.g. a supplier creating an RFQ, a buyer bidding) |
| 404 | `NOT_FOUND` | RFQ does not exist |
| 409 | `DUPLICATE_REFERENCE` | Reference ID already used |
| 409 | `AUCTION_NOT_STARTED` | Bid before the start time |
| 409 | `AUCTION_CLOSED` | Bid at or after the current close (or forced close) |
| 422 | `VALIDATION_ERROR` | Invalid input; `details` lists the fields |
| 422 | `FORCED_CLOSE_NOT_AFTER_CLOSE` | Forced close is not later than bid close |
| 422 | `BID_NOT_LOWER` | Supplier's new bid is not lower than their previous bid |

## Endpoints

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/api/health` | — | Liveness, database and Redis status |
| GET | `/api/meta/time` | — | Server time |
| GET | `/api/users` | — | Seeded users (for choosing the acting user) |
| POST | `/api/rfqs` | Buyer | Create an RFQ with British auction settings |
| GET | `/api/rfqs` | — | Auction listing |
| GET | `/api/rfqs/{id}` | — | Auction details with ranking and stats |
| GET | `/api/rfqs/{id}/bids` | — | Bids; `?history=true` includes superseded revisions |
| POST | `/api/rfqs/{id}/bids` | Supplier | Submit a bid |
| GET | `/api/rfqs/{id}/activity` | — | Activity log, newest first |
| WS | `/ws` | — | Live events |

### Create an RFQ — `POST /api/rfqs`

```json
{
  "name": "Mumbai to Rotterdam, 2 x 40HC",
  "reference_id": "RFQ-2026-0001",
  "pickup_date": "2026-11-20",
  "bid_start_at": "2026-11-07T12:00:00Z",
  "bid_close_at": "2026-11-07T12:30:00Z",
  "forced_close_at": "2026-11-07T13:00:00Z",
  "auction_config": {
    "trigger_window_minutes": 10,
    "extension_duration_minutes": 5,
    "trigger_type": "L1_CHANGE"
  }
}
```

- `reference_id` is optional; one is generated (`RFQ-YYYY-NNNN`) when omitted.
- Rules: start not in the past; close after start; **forced close after close**; pickup date on or after the close date; X and Y between 1 and 120; `trigger_type` is `BID_RECEIVED`, `ANY_RANK_CHANGE` or `L1_CHANGE`.
- Returns `201` with the created RFQ (same shape as the detail response).

### Listing — `GET /api/rfqs`

Query parameters: `status` (`SCHEDULED`, `ACTIVE`, `CLOSED`, `FORCE_CLOSED`), `search` (name or reference ID), `page` (default 1), `page_size` (default 20, max 100).

```json
{
  "items": [
    {
      "id": "6f1c…",
      "reference_id": "RFQ-2026-0001",
      "name": "Mumbai to Rotterdam, 2 x 40HC",
      "status": "ACTIVE",
      "lowest_bid": { "amount": "125000.00", "currency": "INR", "supplier_name": "Swift Cargo" },
      "bid_start_at": "2026-11-07T12:00:00Z",
      "bid_close_at": "2026-11-07T12:30:00Z",
      "current_close_at": "2026-11-07T12:40:00Z",
      "forced_close_at": "2026-11-07T13:00:00Z",
      "extension_count": 2,
      "bid_count": 7,
      "supplier_count": 3
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "server_time": "2026-11-07T12:31:05Z"
}
```

`lowest_bid` is `null` when there are no bids.

### Details — `GET /api/rfqs/{id}`

```json
{
  "rfq": {
    "id": "6f1c…", "reference_id": "RFQ-2026-0001", "name": "…", "status": "ACTIVE",
    "pickup_date": "2026-11-20", "bid_start_at": "…", "bid_close_at": "…",
    "current_close_at": "…", "forced_close_at": "…", "extension_count": 2,
    "buyer": { "id": "…", "name": "…", "company_name": "…" }
  },
  "auction_config": { "trigger_window_minutes": 10, "extension_duration_minutes": 5, "trigger_type": "L1_CHANGE" },
  "ranking": [
    {
      "rank": 1, "rank_label": "L1", "bid_id": "…",
      "supplier": { "id": "…", "name": "…", "company_name": "Swift Cargo" },
      "carrier_name": "Swift Ocean Line",
      "freight_charges": "110000.00", "origin_charges": "8000.00", "destination_charges": "7000.00",
      "total_amount": "125000.00", "currency": "INR",
      "transit_time_days": 24, "quote_validity_date": "2026-11-30",
      "submitted_at": "…", "revision_count": 3
    }
  ],
  "stats": {
    "bid_count": 7, "supplier_count": 3, "extension_count": 2, "total_extended_minutes": 10,
    "first_l1_amount": "140000.00", "current_l1_amount": "125000.00", "savings_pct": "10.71"
  },
  "server_time": "…"
}
```

### Submit a bid — `POST /api/rfqs/{id}/bids`

```json
{
  "carrier_name": "Swift Ocean Line",
  "freight_charges": "110000.00",
  "origin_charges": "8000.00",
  "destination_charges": "7000.00",
  "transit_time_days": 24,
  "quote_validity_date": "2026-11-30",
  "notes": "Includes BAF"
}
```

- Rules: charges ≥ 0 with at most two decimals, total > 0; transit time 1–365 days; quote validity on or after the pickup date; lower than the supplier's previous bid.
- Returns `201`:

```json
{
  "bid": { "id": "…", "total_amount": "125000.00", "submitted_at": "…" },
  "rank": 1,
  "extension": {
    "applied": true,
    "previous_close_at": "2026-11-07T12:35:00Z",
    "new_close_at": "2026-11-07T12:40:00Z",
    "capped": false,
    "reason": "New L1 within last 10 min: Swift Cargo replaced BlueWave Logistics"
  },
  "rfq": { "status": "ACTIVE", "current_close_at": "2026-11-07T12:40:00Z" },
  "server_time": "…"
}
```

`extension` is `null` when the bid did not trigger one.

### Activity log — `GET /api/rfqs/{id}/activity`

Query parameters: `limit` (default 50, max 200), `before_id` (load older entries).

```json
{
  "items": [
    {
      "id": 42, "type": "AUCTION_EXTENDED", "created_at": "…",
      "actor": null,
      "message": "Auction extended 12:35 → 12:40. New L1 within last 10 min: Swift Cargo replaced BlueWave Logistics",
      "metadata": { "previous_close_at": "…", "new_close_at": "…", "capped": false, "trigger_type": "L1_CHANGE" }
    }
  ],
  "next_before_id": 41,
  "server_time": "…"
}
```

## WebSocket — `/ws`

Client messages:

```json
{ "action": "subscribe", "channel": "rfq:6f1c…" }
{ "action": "subscribe", "channel": "listing" }
{ "action": "unsubscribe", "channel": "rfq:6f1c…" }
{ "action": "ping" }
```

Server messages share one envelope:

```json
{ "type": "auction.extended", "channel": "rfq:6f1c…", "data": { … }, "server_time": "…" }
```

| Type | Channel | `data` |
|---|---|---|
| `bid.submitted` | `rfq:{id}` | `ranking`, `bid`, `activity` |
| `auction.extended` | `rfq:{id}` | `previous_close_at`, `new_close_at`, `capped`, `reason`, `activity` |
| `auction.status` | `rfq:{id}` | `status`, `current_close_at`, `activity` |
| `listing.updated` | `listing` | `item` (listing row) |
| `rfq.created` | `listing` | `item` (listing row) |
