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
| 404 | `NOT_FOUND` | RFQ or route does not exist |
| 405 | `METHOD_NOT_ALLOWED` | HTTP method not supported on the route |
| 409 | `DUPLICATE_REFERENCE` | Reference ID already used |
| 409 | `AUCTION_NOT_STARTED` | Bid before the start time |
| 409 | `AUCTION_CLOSED` | Bid at or after the current close (or forced close) |
| 422 | `VALIDATION_ERROR` | Invalid input; `details` lists the fields |
| 422 | `FORCED_CLOSE_NOT_AFTER_CLOSE` | Forced close is not later than bid close |
| 422 | `BID_NOT_LOWER` | Supplier's new bid is not lower than their previous bid |
| 500 | `INTERNAL_ERROR` | Unexpected server error (details are logged, not returned) |

## Endpoints

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/api/health` | — | Liveness: database, Redis and the live-event relay |
| GET | `/api/meta/time` | — | Server time |
| GET | `/api/users` | — | Seeded users (for choosing the acting user) |
| GET | `/api/users/me` | Any | The user identified by `X-User-Id` |
| POST | `/api/rfqs` | Buyer | Create an RFQ with British auction settings |
| GET | `/api/rfqs` | — | Auction listing |
| GET | `/api/rfqs/{id}` | — | Auction details with ranking and stats |
| GET | `/api/rfqs/{id}/bids` | — | Latest bid per supplier in rank order; `?history=true` returns every bid (including superseded revisions), newest first |
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
      "supplier_count": 3,
      "version": 42
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
    "closed_at": null, "created_at": "…",
    "buyer": { "id": "…", "name": "…", "company_name": "…" },
    "version": 42
  },
  "auction_config": { "trigger_window_minutes": 10, "extension_duration_minutes": 5, "trigger_type": "L1_CHANGE" },
  "ranking": [
    {
      "rank": 1, "rank_label": "L1", "bid_id": "…",
      "supplier": { "id": "…", "name": "…", "company_name": "Swift Cargo" },
      "carrier_name": "Swift Ocean Line",
      "freight_charges": "110000.00", "origin_charges": "8000.00", "destination_charges": "7000.00",
      "total_amount": "125000.00", "currency": "INR",
      "transit_time_days": 24, "quote_validity_date": "2026-11-30", "notes": null,
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

- `status` is derived from the times on every request, so it is correct even before a background task updates the stored status.
- Ranking: each supplier's latest bid, lowest total first; equal totals rank by submission time.
- `first_l1_amount` is the total of the first bid placed; `savings_pct` is the drop from it to the current L1.

### Bids — `GET /api/rfqs/{id}/bids`

Returns `{ "items": [Bid], "server_time": "…" }`. Each bid has the quote fields above plus `id`, `supplier`, `is_latest` (false once the supplier submitted a lower bid), `rank_at_submission` and `submitted_at`.

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
  "bid": { "id": "…", "total_amount": "125000.00", "is_latest": true, "rank_at_submission": 1, "submitted_at": "…", … },
  "rank": 1,
  "rank_label": "L1",
  "extension": {
    "applied": true,
    "previous_close_at": "2026-11-07T12:35:00Z",
    "new_close_at": "2026-11-07T12:40:00Z",
    "capped": false,
    "reason": "New L1 within the last 10 min before close: Swift Cargo replaced BlueWave Logistics"
  },
  "rfq": { "status": "ACTIVE", "current_close_at": "2026-11-07T12:40:00Z", "extension_count": 3 },
  "server_time": "…"
}
```

- `extension` is `null` when the bid did not trigger one (outside the window, or the trigger condition was not met).
- When the trigger is met but the close is already at the forced close, `extension.applied` is `false` and `capped` is `true`; the activity log records `EXTENSION_SKIPPED`.
- When an extension is shortened by the forced close, `applied` and `capped` are both `true`.
- Errors: `AUCTION_NOT_STARTED`, `AUCTION_CLOSED` (409); `BID_NOT_LOWER`, `VALIDATION_ERROR` incl. `quote_validity_date` before the pickup date (422).

### Activity log — `GET /api/rfqs/{id}/activity`

Query parameters: `limit` (default 50, max 200), `before_id` (load older entries).

```json
{
  "items": [
    {
      "id": 42, "type": "AUCTION_EXTENDED", "created_at": "…",
      "actor": null,
      "message": "Auction extended by 5 min. New L1 within the last 10 min before close: Swift Cargo replaced BlueWave Logistics",
      "metadata": { "previous_close_at": "…", "new_close_at": "…", "capped": false, "trigger_type": "L1_CHANGE", "extension_minutes": 5 }
    }
  ],
  "next_before_id": 41,
  "server_time": "…"
}
```

Messages carry no clock times (the UI formats `created_at` and the times in `metadata` in the viewer's timezone).

| Type | Example message | Notes |
|---|---|---|
| `RFQ_CREATED` | Acme Exports created RFQ RFQ-2026-0001 | |
| `AUCTION_STARTED` | Bidding opened | Dated at the start time, even if recorded later |
| `BID_SUBMITTED` | Swift Cargo bid INR 125,000.00: now L1 | `metadata`: `total_amount`, `rank`, `in_trigger_window`, `previous_total` |
| `AUCTION_EXTENDED` | Auction extended by 5 min. *reason* | Shortened extensions add "(capped at the forced close time)" |
| `EXTENSION_SKIPPED` | Not extended: the auction is already at its forced close time. Trigger met: *reason* | |
| `AUCTION_CLOSED` | Auction closed. L1: Swift Cargo at INR 125,000.00 (7 bids from 3 suppliers) | Or "Auction closed with no bids". Dated at the close time; `metadata.l1` holds the supplier, bid and amount |
| `AUCTION_FORCE_CLOSED` | Auction force closed at its forced close time. L1: … | The close had reached the forced close time |

## WebSocket — `/ws`

Connect to `ws://localhost:8000/ws` (the Vite dev server proxies `/ws`). No user header is needed: everything sent is also public over REST.

Client messages (JSON text frames):

```json
{ "action": "subscribe", "channel": "rfq:6f1c…" }
{ "action": "subscribe", "channel": "listing" }
{ "action": "unsubscribe", "channel": "rfq:6f1c…" }
{ "action": "ping" }
```

Every server message uses one envelope:

```json
{ "type": "auction.extended", "channel": "rfq:6f1c…", "data": { … }, "server_time": "2026-11-07T12:35:00.123456Z" }
```

| Type | Channel | `data` |
|---|---|---|
| `subscribed` / `unsubscribed` | the channel | `{}` |
| `pong` | `null` | `{}` |
| `error` | `null` | `code` (`INVALID_MESSAGE`, `UNKNOWN_ACTION`, `INVALID_CHANNEL`, `TOO_MANY_SUBSCRIPTIONS`), `message`. The connection stays open. |
| `resync` | `null` | `{}`: live events may have been missed (the server lost Redis for a while). Reload over REST. |
| `bid.submitted` | `rfq:{id}` | `version`, `bid`, `rank`, `rank_label`, `extension` (as in the submit-bid response), `rfq`, `ranking`, `stats`, `activity` |
| `auction.extended` | `rfq:{id}` | `version`, `previous_close_at`, `new_close_at`, `capped`, `reason`, `extension_count`, `activity` |
| `auction.status` | `rfq:{id}` | `version`, `status`, `rfq`, `activity`: the auction opened or closed |
| `listing.updated` | `listing` | `version`, `item` (a listing row) |
| `rfq.created` | `listing` | `version`, `item` |

- Channels are `listing` and `rfq:<rfq id>`, at most 50 per connection. Unknown RFQ ids are accepted; they just never receive events.
- One change sends its events in this order: `auction.status` (if a bid opened the auction), `bid.submitted`, `auction.extended`, `listing.updated`. They all carry the same `version`.
- **Ordering:** `version` is the auction's newest activity id, and grows with every change. REST responses carry it too (`rfq.version` in details, `version` on each listing row). Keep the highest version you have per auction, and ignore events with a lower one: events from two quick changes can arrive in either order.
- `activity` holds the entries written by that change, oldest first. Each entry is sent in exactly one event.
- On page load: subscribe first, then fetch over REST. After a reconnect or a `resync`: subscribe again and refetch.
