# Testing

How the British Auction RFQ system is tested, how to run each suite, and where every rule from the assignment is checked.

| Suite | Tool | Tests | What it covers |
|---|---|---|---|
| Backend unit | pytest + Hypothesis | 102 | Auction engine (ranking, trigger window, the three triggers, extension cap, status), request validation, error envelope, realtime plumbing |
| Backend integration | pytest against real PostgreSQL + Redis | 144 | Every endpoint, bid service, Celery lifecycle jobs and sweeper, WebSocket events, migrations and DB constraints, seed and simulation scripts |
| Model-based | Hypothesis stateful testing | 60 random auctions × 25 steps | Random bid sequences against an independent model of the rules |
| API fuzzing | Hypothesis | ~1,000 requests per run | Malformed and nearly valid requests never cause a 500 |
| Frontend | Vitest + Testing Library | 177 | Components, forms, time/money maths, live-update logic with a fake WebSocket |
| End to end | Playwright (Chromium) | 8 | The full stack in real browsers: buyer and suppliers in separate windows, live updates, force close, phone and laptop layouts |
| Accessibility | axe-core in Playwright | every page | No serious or critical WCAG 2.1 AA violations |

Coverage: backend 98% (`app` and `scripts`), frontend 97% of statements. CI enforces a frontend floor of 95% statements, 90% branches.

## Running the tests

```bash
make test        # backend: unit + integration + model-based + fuzzing (needs `make up`)
make test-web    # frontend unit tests
cd frontend && npm run coverage   # with coverage report and thresholds
make e2e         # browser tests: needs `make api`, `make worker`, `make beat` and a seeded DB
# or against the Docker stack (docker compose up --build):
cd frontend && E2E_BASE_URL=http://localhost:8080 E2E_API_URL=http://localhost:8080 npm run e2e
make check       # everything CI runs except e2e
```

CI (`.github/workflows/ci.yml`) runs three jobs on every push:
- **backend:** ruff, mypy and pytest with coverage.
- **frontend:** oxlint, Vitest with coverage thresholds, and the build.
- **e2e:** starts Postgres, Redis, the API, a Celery worker and Beat, then runs Playwright.

## How the important properties are tested

**The rules, exhaustively.** `tests/unit/test_auction_engine.py` covers each trigger type with positive and negative cases, the inclusive/exclusive window edges down to the microsecond, and the cap. A Hypothesis property checks that an extension never passes the forced close.

**The rules, end to end, at random.** `tests/integration/test_auction_model.py` is a state machine:
- Hypothesis picks random suppliers, prices (from a narrow range, so ties and "not lower" rejections are common) and time steps, plus bids placed exactly on the window and close boundaries.
- Each step runs through the real bid service and database.
- A short reference model written independently of the engine predicts every outcome.
- After every step, the database must agree on acceptance and the rejection reason, current close, extension count, ranking (computed in SQL and by the API), bid count, every activity-log type, and the derived status.

I checked the model test by deliberately breaking the engine in seven ways. It caught every one:
- window start exclusive;
- no forced-close cap;
- extending at the cap;
- accepting a bid at the close instant;
- rank change treated as L1 change;
- ties broken by id instead of time;
- equal re-bids allowed.

**Concurrency.** `test_a20` fires 20 simultaneous bids and checks every invariant. `test_a21` runs a close job while a bid holds the row lock and checks the job sees the bid's extension. Two regression tests cover a stale-session bug found in Stage 7 (`populate_existing` on the lock query).

**Robustness.** `tests/integration/test_api_fuzz.py` sends:
- random JSON of any type, including NaN and Infinity;
- random query strings, paths and `X-User-Id` headers;
- "nearly valid" requests, where one field of a valid body is replaced.

Every answer must be a deliberate status code with the error envelope, and a 422 must name the broken field.

**Scale.** `tests/integration/test_query_budget.py` checks:
- the listing and details pages use a constant number of SQL queries however many auctions, suppliers or revisions exist (no N+1);
- 200 auctions, plus one auction with 50 suppliers × 5 revisions, stay within a time budget;
- a bid at that scale is still one quick transaction.

**Live updates in the browser.** The frontend tests drive the real hooks with a fake WebSocket. They check:
- events newer than the cache are applied;
- older ones are ignored, whether they arrive as events or as late REST responses;
- reconnects and server `resync` trigger a refetch;
- countdowns falling to zero trigger a fallback refetch.

The Playwright tests then check the same things across real browsers. In `auction-flow.spec.ts`:
- a buyer creates an RFQ in the form;
- a supplier bids in another window, and the buyer sees the bid and the extension;
- a second supplier underbids, and the first is told they were outbid;
- the listing updates live;
- a reload mid-auction shows the same state.

`lifecycle.spec.ts` watches an auction open, extend up to its forced close, and force-close on time without a reload. Celery jobs drive the open and close.

**Mutation checks.** For the critical frontend logic, each guard was deliberately broken to confirm a test fails. This covered:
- version checks;
- refetch on stale data;
- outbid detection;
- the bid "must be lower" rule;
- the timezone conversion;
- the extension maximum;
- daylight-saving handling.

Whenever a break survived, I added a test for it.

## Bugs these tests found (all fixed)

| Found by | Bug |
|---|---|
| Regression tests (Stage 7) | The bid lock could return a stale copy of the auction from the session, causing a duplicate "opened" entry or a wrongly rejected bid |
| Large-amount test | Three charges each at the per-charge limit overflowed the total's `NUMERIC(14, 2)` column and returned a 500. The total is now validated (422) |
| API fuzzing | A NUL character in a name, carrier, notes or search query returned a 500, because PostgreSQL rejects NUL. Control characters are now rejected with a 422 on the field |
| Playwright lifecycle test | A capped extension shorter than a minute was logged as "extended by 0 min". Durations are now exact ("40 s"), and stats include `total_extended_seconds` |
| axe accessibility check | White text on the primary button had 3.6:1 contrast. The button fill is now deeper (4.9:1, WCAG AA) |
| Browser screenshots | A see-through user menu, the header wrapping on phones, and the ranking table overflowing at 1440 px |
| Playwright width test (Stage 14) | Beside the bid form, the ranking table was cut off at 1024–1440 px (by up to 407 px). It now switches between table and cards by the space it actually has (a container query), and folds origin and destination under freight when space is tight |

## Test matrix traceability

The scenario matrix from the plan, with where each row is tested.

### Engine (`backend/tests/unit/test_auction_engine.py`)

| # | Case | Test |
|---|---|---|
| E1, E2 | Ranking by total; ties by earlier bid | `test_e1_ranking_is_lowest_total_first`, `test_e2_tie_goes_to_earlier_bid` |
| E3–E5 | Window start inclusive, before it excluded, close excluded | `test_trigger_window_boundaries` |
| E6–E16 | Each trigger type, positive and negative, incl. first bids | `test_trigger_types` (one case per row) |
| X1–X4 | Extension, cap, exact fit, already at forced close | `test_compute_extension` |
| X5 | New close never passes the forced close (property) | `test_x5_extension_never_passes_forced_close` |
| S1–S4 | Status from the clock | `test_derive_status` |

### API and services (`backend/tests/integration/`)

| # | Case | Test |
|---|---|---|
| A1 | Create RFQ; start/close jobs queued | `test_lifecycle.py::test_a1_create_queues_start_and_close_jobs` |
| A2 | Forced close not after close → `FORCED_CLOSE_NOT_AFTER_CLOSE` | `test_rfqs_api.py::test_a2_forced_close_must_be_after_close` |
| A3, A4 | Close ≤ start; X or Y out of range | `test_rfqs_api.py::test_validation_errors_point_at_the_field` |
| A5, A10 | Wrong role creating or bidding | `test_a5_only_buyers_create_rfqs`, `test_a10_only_suppliers_bid` |
| A6 | Duplicate reference | `test_a6_duplicate_reference_id` |
| A7–A9 | Bid before start, at/after close, after forced close | `test_bids_api.py::test_a7…`, `test_a8…`, `test_a9…` |
| A11, A12 | Re-bid must be lower; replaces the previous bid | `test_a11_revision_must_be_lower`, `test_a12_lower_revision_replaces_previous_bid` |
| A13 | Bid outside the window: no extension | `test_bids_api.py::test_response_and_log_for_a_bid_outside_the_window` |
| A14 | Each trigger type in and out of the window | `test_a14_trigger_types` |
| A15 | The worked example until force close | `test_a15_worked_example_until_force_close` |
| A16 | Quote validity before pickup | `test_a16_quote_must_cover_pickup_date` |
| A17–A19 | Listing, details, activity log | `test_a17…`, `test_a18…`, `test_rfqs_api.py::test_activity_newest_first_with_pagination` |
| A20 | 20 concurrent bids | `test_a20_concurrent_bids_keep_every_invariant` |
| A21–A23 | Bid racing the close job; stale close job; sweeper | `test_lifecycle.py::test_a21…`, `test_a22…`, `test_a23…` |
| A24 | WebSocket delivery through Redis | `test_websocket.py::test_a24_bids_and_extensions_reach_subscribed_sockets_only` |

### Frontend (`frontend/src/**/*.test.ts(x)`, `frontend/e2e/`)

| Case | Test |
|---|---|
| Create form: each error on the right field; preview maths | `features/createRfq/form.test.ts`, `lib/auctionPreview.test.ts`, `pages/CreateRfqPage.test.tsx` |
| Local time ↔ UTC across time zones and daylight saving | `lib/datetimeLocal.test.ts` |
| Listing: statuses, countdowns, live rows, filters, search | `pages/AuctionListPage.test.tsx` |
| Details: live re-ranking, extension toast and pulse, activity, form disabled at zero, own row, history | `pages/AuctionDetailPage.test.tsx` |
| Bid form rules and money in paise | `features/bid/bidForm.test.ts` |
| Server clock and countdown ticking | `lib/serverClock.test.ts`, `hooks/useCountdown.test.tsx` |
| WebSocket reconnect, resubscribe and resync | `realtime/wsClient.test.ts` |
| Two windows live; force close live; 390 px; ranking fits at 1024–1920 px; accessibility | `e2e/auction-flow.spec.ts`, `e2e/lifecycle.spec.ts`, `e2e/pages.spec.ts`, `e2e/accessibility.spec.ts` |

## Demo tooling

`make simulate` (`backend/scripts/simulate_bidding.py`) creates a short auction and has bot suppliers bid against each other inside the trigger window. It prints a timeline of bids, extensions and the cap, ending with the force close. Its own tests run the whole simulation on a fake clock in about a second.
