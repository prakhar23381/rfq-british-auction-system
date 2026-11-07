import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Activity, BidCreate, RankedBid, RfqDetail } from '../api/types'
import { callsTo, mockApi, renderApp, respond } from '../test/app'
import { openSocket, serverSends } from '../test/fakeWebSocket'
import { STORAGE_KEY } from '../user/userContext'

const MIN = 60_000
const inMinutes = (m: number) => new Date(Date.now() + m * MIN).toISOString()
const SWIFT = { id: 's2', name: 'Meera Iyer', company_name: 'Swift Cargo' }
const BLUEWAVE = { id: 's1', name: 'Ravi Kumar', company_name: 'BlueWave Logistics' }

function ranked(rank: number, supplier: typeof SWIFT, freight: number, extra: Partial<RankedBid> = {}): RankedBid {
  return {
    rank,
    rank_label: `L${rank}`,
    bid_id: `bid-${supplier.id}-${freight}`,
    supplier,
    carrier_name: `${supplier.company_name} Line`,
    freight_charges: `${freight}.00`,
    origin_charges: '8000.00',
    destination_charges: '0.00',
    total_amount: `${freight + 8000}.00`,
    currency: 'INR',
    transit_time_days: 24,
    quote_validity_date: '2026-12-31',
    notes: null,
    submitted_at: inMinutes(-5),
    revision_count: 2,
    ...extra,
  }
}

function entry(id: number, type: Activity['type'], message: string, metadata: Record<string, unknown> = {}): Activity {
  return { id, type, message, actor: null, metadata, created_at: inMinutes(-1) }
}

function detail(overrides: { closeIn?: number; version?: number; ranking?: RankedBid[] } = {}): RfqDetail {
  const ranking = overrides.ranking ?? [ranked(1, SWIFT, 110000), ranked(2, BLUEWAVE, 113500)]
  return {
    rfq: {
      id: 'rfq-1',
      reference_id: 'RFQ-2026-0001',
      name: 'Mumbai to Rotterdam',
      status: 'ACTIVE',
      pickup_date: '2026-12-01',
      bid_start_at: inMinutes(-30),
      bid_close_at: inMinutes((overrides.closeIn ?? 20) - 5),
      current_close_at: inMinutes(overrides.closeIn ?? 20),
      forced_close_at: inMinutes(60),
      extension_count: 1,
      closed_at: null,
      created_at: inMinutes(-60),
      buyer: { id: 'b1', name: 'Asha Mehta', company_name: 'Acme Exports' },
      version: overrides.version ?? 40,
    },
    auction_config: { trigger_window_minutes: 10, extension_duration_minutes: 5, trigger_type: 'L1_CHANGE' },
    ranking,
    stats: {
      bid_count: 4,
      supplier_count: 2,
      extension_count: 1,
      total_extended_minutes: 5,
      total_extended_seconds: 300,
      first_l1_amount: '130000.00',
      current_l1_amount: '118000.00',
      savings_pct: '9.23',
    },
  }
}

const ACTIVITY = [
  entry(40, 'AUCTION_EXTENDED', 'Auction extended by 5 min. New L1 within the last 10 min before close: Swift Cargo replaced BlueWave Logistics', {
    previous_close_at: '2026-11-07T12:30:00Z',
    new_close_at: '2026-11-07T12:35:00Z',
    capped: false,
  }),
  entry(39, 'BID_SUBMITTED', 'Swift Cargo bid ₹1,18,000 (L1)'),
  entry(2, 'AUCTION_STARTED', 'Bidding opened'),
]

function mockAuction(
  options: { detail?: () => RfqDetail; submit?: (body: BidCreate) => Response } = {},
) {
  return mockApi({
    '/api/rfqs/rfq-1': () => respond(options.detail ? options.detail() : detail()),
    '/api/rfqs/rfq-1/activity': () => respond({ items: ACTIVITY, next_before_id: null }),
    '/api/rfqs/rfq-1/bids': (_, init) =>
      init?.method === 'POST'
        ? (options.submit ?? (() => respond({ error: { code: 'INTERNAL_ERROR', message: 'x' } }, 500)))(
            JSON.parse(String(init.body)) as BidCreate,
          )
        : respond({ items: [] }),
  })
}

const actAs = (id: string) => window.localStorage.setItem(STORAGE_KEY, id)
const rankingTable = () => screen.getByRole('table', { name: /Supplier ranking/ })
const rows = () => within(rankingTable()).getAllByRole('row').slice(1)
async function openAuction() {
  renderApp('/rfqs/rfq-1')
  await screen.findByRole('heading', { level: 1, name: 'Mumbai to Rotterdam' })
}

afterEach(() => vi.unstubAllGlobals())

describe('Auction details', () => {
  it('shows ranking, quote breakdown, settings and activity (R14–R17)', async () => {
    mockAuction()
    await openAuction()

    expect(rows()[0]).toHaveTextContent(/L1.*Swift Cargo.*Swift Cargo Line.*₹1,10,000.*₹8,000.*₹0.*₹1,18,000.*24 d/)
    expect(rows()[1]).toHaveTextContent(/L2.*BlueWave Logistics.*₹1,21,500/)

    const settings = screen.getByRole('heading', { name: 'Auction settings' }).closest('section') as HTMLElement
    expect(settings).toHaveTextContent('10 min')
    expect(settings).toHaveTextContent('+5 min')
    expect(settings).toHaveTextContent('Lowest bidder (L1) changes')

    expect(screen.getByText('9.2%')).toBeInTheDocument() // savings vs first L1
    const log = await screen.findByRole('list', { name: 'Activity log' })
    expect(log).toHaveTextContent('Swift Cargo replaced BlueWave Logistics') // the reason (R17)
    expect(log).toHaveTextContent(/\d\d:\d\d → \d\d:\d\d/)
    expect(screen.getByText(/Extended \+5 min \(1×\)/)).toBeInTheDocument()
  })

  it('invites the buyer to switch to a supplier instead of bidding', async () => {
    mockAuction()
    await openAuction()
    expect(screen.queryByRole('form', { name: 'Place a bid' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Act as BlueWave Logistics' }))
    expect(await screen.findByRole('form', { name: 'Place a bid' })).toBeInTheDocument()
  })

  it('lets a supplier place a lower bid, starting from their current one', async () => {
    actAs('s1')
    const fetchMock = mockAuction({
      submit: () =>
        respond(
          {
            bid: {},
            rank: 1,
            rank_label: 'L1',
            extension: { applied: true, previous_close_at: inMinutes(20), new_close_at: '2026-11-07T13:05:00Z', capped: false, reason: 'New L1' },
            rfq: { status: 'ACTIVE', current_close_at: '2026-11-07T13:05:00Z', extension_count: 2 },
          },
          201,
        ),
    })
    await openAuction()
    const form = screen.getByRole('form', { name: 'Place a bid' })
    expect(form).toHaveTextContent('Your current bid ₹1,21,500 (L2)')
    expect(within(form).getByLabelText('Carrier')).toHaveValue('BlueWave Logistics Line')

    const freight = within(form).getByLabelText('Freight')
    await userEvent.clear(freight)
    await userEvent.type(freight, '100000.5')
    expect(form).toHaveTextContent('₹1,08,000.50')
    await userEvent.click(within(form).getByRole('button', { name: 'Place a lower bid' }))

    expect(await screen.findByText('Bid placed · you’re L1')).toBeInTheDocument()
    expect(screen.getByText(/Auction extended to \d\d:\d\d\./)).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      carrier_name: 'BlueWave Logistics Line',
      freight_charges: '100000.50',
      origin_charges: '8000.00',
      destination_charges: '0.00',
      transit_time_days: 24,
      quote_validity_date: '2026-12-31',
      notes: null,
    })
  })

  it('stops a bid that is not lower before sending it, and shows server rejections', async () => {
    actAs('s1')
    const fetchMock = mockAuction({
      submit: () =>
        respond({ error: { code: 'AUCTION_CLOSED', message: 'Bidding has closed' } }, 409),
    })
    await openAuction()
    const form = screen.getByRole('form', { name: 'Place a bid' })
    await userEvent.click(within(form).getByRole('button', { name: 'Place a lower bid' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('Your new total must be lower than your current bid.')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)

    fireEvent.change(within(form).getByLabelText('Freight'), { target: { value: '90000' } })
    await userEvent.click(within(form).getByRole('button', { name: 'Place a lower bid' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Bidding has closed for this auction.')
  })

  it('warns inside the trigger window', async () => {
    actAs('s1')
    mockAuction({ detail: () => detail({ closeIn: 4 }) })
    await openAuction()
    expect(screen.getByText(/You’re inside the trigger window\. A bid that takes L1 extends the close by 5 min\./)).toBeInTheDocument()
    expect(screen.getAllByRole('timer')[0]).toHaveClass('text-amber')
  })

  it('shows a 404 for unknown auctions', async () => {
    mockApi({ '/api/rfqs/*': () => respond({ error: { code: 'NOT_FOUND', message: 'RFQ not found' } }, 404) })
    renderApp('/rfqs/missing')
    expect(await screen.findByText('This auction doesn’t exist')).toBeInTheDocument()
  })

  describe('live updates', () => {
    it('applies new bids, ignores stale ones, and tells a supplier they were outbid', async () => {
      actAs('s2') // Swift Cargo, currently L1
      mockAuction()
      await openAuction()
      await screen.findByRole('list', { name: 'Activity log' })
      const socket = openSocket()
      expect(socket.sent).toContainEqual({ action: 'subscribe', channel: 'rfq:rfq-1' })

      const next = detail({ version: 41, ranking: [ranked(1, BLUEWAVE, 105000), ranked(2, SWIFT, 110000)] })
      serverSends({
        type: 'bid.submitted',
        channel: 'rfq:rfq-1',
        data: {
          version: 41,
          bid: { supplier: BLUEWAVE },
          rank: 1,
          rank_label: 'L1',
          extension: null,
          rfq: next.rfq,
          ranking: next.ranking,
          stats: next.stats,
          activity: [entry(41, 'BID_SUBMITTED', 'BlueWave Logistics bid ₹1,13,000 (L1)')],
        },
      })
      expect(rows()[0]).toHaveTextContent('BlueWave Logistics')
      expect(rows()[0]).toHaveClass('animate-flash')
      expect(screen.getByRole('list', { name: 'Activity log' }).firstChild).toHaveTextContent('BlueWave Logistics bid ₹1,13,000 (L1)')
      expect(await screen.findByText('You’ve been outbid · now L2')).toBeInTheDocument()

      // A late event from before must not undo it.
      serverSends({
        type: 'bid.submitted',
        channel: 'rfq:rfq-1',
        data: { ...detail({ version: 39 }), version: 39, bid: { supplier: SWIFT }, activity: [] },
      })
      expect(rows()[0]).toHaveTextContent('BlueWave Logistics')
    })

    it('shows extensions and the close as they happen', async () => {
      actAs('s1')
      mockAuction()
      await openAuction()
      openSocket()

      serverSends({
        type: 'auction.extended',
        channel: 'rfq:rfq-1',
        data: {
          version: 41,
          previous_close_at: inMinutes(20),
          new_close_at: inMinutes(25),
          capped: false,
          reason: 'New L1 within the last 10 min before close',
          extension_count: 2,
          activity: [],
        },
      })
      expect(await screen.findByText(/^Auction extended to \d\d:\d\d$/)).toBeInTheDocument()
      expect(screen.getByText('+2 ext')).toBeInTheDocument()

      const closed = detail({ version: 42 })
      serverSends({
        type: 'auction.status',
        channel: 'rfq:rfq-1',
        data: {
          version: 42,
          status: 'CLOSED',
          rfq: { ...closed.rfq, status: 'CLOSED', closed_at: inMinutes(0) },
          activity: [entry(42, 'AUCTION_CLOSED', 'Auction closed. L1: Swift Cargo at ₹1,18,000')],
        },
      })
      expect(await screen.findByText('Auction closed')).toBeInTheDocument()
      expect(screen.getByText('Bidding has closed for this auction.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Place a lower bid' })).toBeDisabled()
      expect(screen.getByText('Closed at')).toBeInTheDocument()
    })

    it('ignores stale status changes and stale bids', async () => {
      actAs('s2') // Swift Cargo, L1
      mockAuction()
      await openAuction()
      openSocket()

      const old = detail({ version: 30 })
      serverSends({
        type: 'auction.status',
        channel: 'rfq:rfq-1',
        data: { version: 30, status: 'CLOSED', rfq: { ...old.rfq, status: 'CLOSED' }, activity: [] },
      })
      expect(screen.getByText('Closes in')).toBeInTheDocument()
      expect(screen.queryByText('Closed at')).not.toBeInTheDocument()

      // An old bid that had Swift at L3 must not claim Swift was just outbid.
      const third = { id: 's9', name: 'X', company_name: 'Oceanic Freight' }
      serverSends({
        type: 'bid.submitted',
        channel: 'rfq:rfq-1',
        data: {
          ...detail({ version: 35 }),
          version: 35,
          ranking: [ranked(1, third, 90000), ranked(2, BLUEWAVE, 100000), ranked(3, SWIFT, 110000)],
          bid: { supplier: third },
          activity: [],
        },
      })
      expect(screen.queryByText(/You’ve been outbid/)).not.toBeInTheDocument()
      expect(rows()[0]).toHaveTextContent('Swift Cargo')
      expect(rows()[0]).not.toHaveClass('animate-flash')
    })

    it('refetches after a resync', async () => {
      const fetchMock = mockAuction()
      await openAuction()
      openSocket()
      const before = callsTo(fetchMock, '/api/rfqs/rfq-1').length
      serverSends({ type: 'resync', channel: null, data: {} })
      await waitFor(() => expect(callsTo(fetchMock, '/api/rfqs/rfq-1').length).toBe(before + 1))
    })
  })
})

describe('Auction details: more cases', () => {
  it('expands a supplier’s bid history', async () => {
    mockApi({
      '/api/rfqs/rfq-1': () => respond(detail()),
      '/api/rfqs/rfq-1/activity': () => respond({ items: ACTIVITY, next_before_id: null }),
      '/api/rfqs/rfq-1/bids': () =>
        respond({
          items: [
            { ...ranked(1, SWIFT, 110000), id: 'b2', is_latest: true, rank_at_submission: 1 },
            { ...ranked(1, SWIFT, 125000), id: 'b1', is_latest: false, rank_at_submission: 2 },
            { ...ranked(2, BLUEWAVE, 113500), id: 'b0', is_latest: true, rank_at_submission: 1 },
          ],
        }),
    })
    await openAuction()
    const toggle = within(rows()[0]).getByRole('button', { name: /2 bids/ })
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const history = await within(rankingTable()).findByRole('list', { name: 'Bid history' })
    expect(within(history).getAllByRole('listitem')).toHaveLength(2) // only Swift's bids
    expect(history).toHaveTextContent('was L2 when placed')
    expect(within(history).getByText('₹1,33,000')).toHaveClass('line-through') // superseded
    await userEvent.click(toggle)
    expect(within(rankingTable()).queryByRole('list', { name: 'Bid history' })).not.toBeInTheDocument()
  })

  it('loads older activity on request', async () => {
    mockApi({
      '/api/rfqs/rfq-1': () => respond(detail()),
      '/api/rfqs/rfq-1/activity': (url) =>
        url.searchParams.get('before_id')
          ? respond({ items: [entry(1, 'RFQ_CREATED', 'Acme Exports created RFQ RFQ-2026-0001')], next_before_id: null })
          : respond({ items: ACTIVITY, next_before_id: 2 }),
    })
    await openAuction()
    await userEvent.click(await screen.findByRole('button', { name: 'Load older activity' }))
    expect(await screen.findByText('Acme Exports created RFQ RFQ-2026-0001')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load older activity' })).not.toBeInTheDocument()
  })

  it('tells suppliers when an upcoming auction opens', async () => {
    actAs('s1')
    const upcoming = detail()
    upcoming.rfq = { ...upcoming.rfq, status: 'SCHEDULED', bid_start_at: inMinutes(30) }
    mockAuction({ detail: () => upcoming })
    await openAuction()
    expect(screen.getByText(/^Bidding opens at/)).toBeInTheDocument()
    expect(screen.getByText('Opens in')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Place a bid' })).not.toBeInTheDocument()
  })

  it('puts server field errors on the field and reports network failures', async () => {
    actAs('s1')
    let answer: () => Response | Promise<Response> = () =>
      respond(
        {
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Quote must be valid until at least the pickup / service date',
            details: [{ field: 'quote_validity_date', message: 'Quote must be valid until at least the pickup / service date' }],
          },
        },
        422,
      )
    mockAuction({ submit: () => answer() as Response })
    await openAuction()
    const form = screen.getByRole('form', { name: 'Place a bid' })
    fireEvent.change(within(form).getByLabelText('Freight'), { target: { value: '90000' } })
    await userEvent.click(within(form).getByRole('button', { name: 'Place a lower bid' }))
    const validity = within(form).getByLabelText('Quote valid until')
    await waitFor(() => expect(validity).toHaveAccessibleDescription('Quote must be valid until at least the pickup / service date'))
    expect(validity).toHaveFocus()

    fireEvent.change(validity, { target: { value: '2027-01-15' } })
    expect(validity).not.toHaveAttribute('aria-invalid')
    answer = () => Promise.reject(new TypeError('Failed to fetch'))
    await userEvent.click(within(form).getByRole('button', { name: 'Place a lower bid' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Can’t reach the server')
  })

  it('explains when the trigger fired but the close is already at the forced close', async () => {
    actAs('s1')
    mockAuction({
      submit: () =>
        respond(
          {
            bid: {},
            rank: 1,
            rank_label: 'L1',
            extension: { applied: false, previous_close_at: inMinutes(20), new_close_at: inMinutes(20), capped: true, reason: 'New L1' },
            rfq: { status: 'ACTIVE', current_close_at: inMinutes(20), extension_count: 4 },
          },
          201,
        ),
    })
    await openAuction()
    const form = screen.getByRole('form', { name: 'Place a bid' })
    fireEvent.change(within(form).getByLabelText('Carrier'), { target: { value: 'New Carrier' } })
    fireEvent.change(within(form).getByLabelText('Freight'), { target: { value: '90000' } })
    fireEvent.change(within(form).getByLabelText('Transit time'), { target: { value: '18' } })
    fireEvent.change(within(form).getByLabelText(/Notes/), { target: { value: 'Includes BAF' } })
    await userEvent.click(within(form).getByRole('button', { name: 'Place a lower bid' }))
    expect(await screen.findByText('The close is already at the forced close, so no extension.')).toBeInTheDocument()
  })

  it('shows a retryable error when the server fails', async () => {
    let fail = true
    mockApi({
      '/api/rfqs/rfq-1': () => (fail ? respond({ error: { code: 'INTERNAL_ERROR', message: 'x' } }, 500) : respond(detail())),
      '/api/rfqs/rfq-1/activity': () => respond({ items: ACTIVITY, next_before_id: null }),
    })
    renderApp('/rfqs/rfq-1')
    expect(await screen.findByText('Couldn’t load this auction', {}, { timeout: 4000 })).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Mumbai to Rotterdam' })).toBeInTheDocument()
  })
})
