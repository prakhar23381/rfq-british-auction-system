import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { RfqListItem } from '../api/types'
import { callsTo, listing, mockApi, renderApp, respond } from '../test/app'
import { openSocket, serverSends } from '../test/fakeWebSocket'
import { STORAGE_KEY } from '../user/userContext'

const MIN = 60_000
const inMinutes = (minutes: number) => new Date(Date.now() + minutes * MIN).toISOString()

function item(overrides: Partial<RfqListItem>): RfqListItem {
  return {
    id: 'rfq-1',
    reference_id: 'RFQ-2026-0001',
    name: 'Mumbai to Rotterdam',
    status: 'ACTIVE',
    lowest_bid: { amount: '125000.00', currency: 'INR', supplier_name: 'Swift Cargo' },
    bid_start_at: inMinutes(-30),
    bid_close_at: inMinutes(-6),
    current_close_at: inMinutes(4),
    forced_close_at: inMinutes(20),
    extension_count: 2,
    bid_count: 7,
    supplier_count: 3,
    trigger_window_minutes: 10,
    version: 40,
    ...overrides,
  }
}

const ACTIVE = item({})
const UPCOMING = item({
  id: 'rfq-2',
  reference_id: 'RFQ-2026-0002',
  name: 'Chennai to Singapore',
  status: 'SCHEDULED',
  lowest_bid: null,
  bid_start_at: inMinutes(60),
  bid_close_at: inMinutes(90),
  current_close_at: inMinutes(90),
  forced_close_at: inMinutes(120),
  extension_count: 0,
  bid_count: 0,
  supplier_count: 0,
  version: 3,
})
const CLOSED = item({
  id: 'rfq-3',
  reference_id: 'RFQ-2026-0003',
  name: 'Delhi to Dubai',
  status: 'CLOSED',
  current_close_at: inMinutes(-60),
  extension_count: 0,
  supplier_count: 1,
  version: 12,
})
const FORCED = item({
  id: 'rfq-4',
  reference_id: 'RFQ-2026-0004',
  name: 'Pune to Hamburg',
  status: 'FORCE_CLOSED',
  current_close_at: inMinutes(-10),
  forced_close_at: inMinutes(-10),
  extension_count: 4,
  version: 25,
})
const ALL = [ACTIVE, UPCOMING, CLOSED, FORCED]

// The table also renders a card list for phones (hidden by CSS): query inside the table.
const table = () => screen.getByRole('table')
const link = (name: string) => within(table()).getByRole('link', { name })
const queryLink = (name: string) => screen.queryByRole('table') && within(table()).queryByRole('link', { name })
const findLink = async (name: string) => within(await screen.findByRole('table')).findByRole('link', { name })
const rowFor = (name: string) => link(name).closest('tr') as HTMLElement

describe('Auction listing', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows every column the assignment asks for (R12, R13)', async () => {
    mockApi({ '/api/rfqs': () => respond(listing(ALL)) })
    renderApp()

    const active = await findLink('Mumbai to Rotterdam')
    expect(active).toHaveAttribute('href', '/rfqs/rfq-1')
    const row = rowFor('Mumbai to Rotterdam')
    expect(row).toHaveTextContent('RFQ-2026-0001')
    expect(row).toHaveTextContent('₹1,25,000')
    expect(row).toHaveTextContent('Swift Cargo')
    expect(row).toHaveTextContent('+2 ext')
    expect(row).toHaveTextContent('Active')
    // Close is 4 minutes away, inside the 10 minute trigger window: the countdown is amber.
    const timer = within(row).getByRole('timer')
    expect(timer.textContent).toMatch(/^0[34]:\d\d$/)
    expect(timer).toHaveClass('text-amber')

    expect(rowFor('Chennai to Singapore')).toHaveTextContent('No bids yet')
    expect(rowFor('Chennai to Singapore')).toHaveTextContent(/Upcoming/)
    expect(rowFor('Chennai to Singapore')).toHaveTextContent(/opens in/)
    expect(rowFor('Delhi to Dubai')).toHaveTextContent('Closed')
    expect(rowFor('Pune to Hamburg')).toHaveTextContent('Force closed')
    expect(rowFor('Pune to Hamburg')).toHaveTextContent('+4 ext')
  })

  it('filters by status with counts on the tabs', async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      '/api/rfqs': (url) => {
        const status = url.searchParams.get('status')
        const items = status ? ALL.filter((i) => i.status === status) : ALL
        return respond(listing(items, { status_counts: listing(ALL).status_counts }))
      },
    })
    renderApp()
    const tabs = await screen.findByRole('radiogroup', { name: 'Filter by status' })
    await waitFor(() => expect(within(tabs).getByRole('radio', { name: /All/ })).toHaveTextContent('All4'))
    expect(within(tabs).getByRole('radio', { name: /Active/ })).toHaveTextContent('Active1')

    await user.click(within(tabs).getByRole('radio', { name: /Force closed/ }))
    await waitFor(() => expect(queryLink('Mumbai to Rotterdam')).not.toBeInTheDocument())
    expect(link('Pune to Hamburg')).toBeInTheDocument()
    expect(within(tabs).getByRole('radio', { name: /Force closed/ })).toHaveAttribute('aria-checked', 'true')
    expect(callsTo(fetchMock, '/api/rfqs').at(-1)?.searchParams.get('status')).toBe('FORCE_CLOSED')

    // Arrow keys move between tabs.
    await user.keyboard('{ArrowRight}')
    expect(within(tabs).getByRole('radio', { name: /All/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('searches after a pause in typing, not on every key', async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      '/api/rfqs': (url) => {
        const q = url.searchParams.get('search')?.toLowerCase()
        return respond(listing(q ? ALL.filter((i) => i.name.toLowerCase().includes(q)) : ALL))
      },
    })
    renderApp()
    await screen.findByRole('table')
    await user.type(screen.getByRole('searchbox', { name: 'Search auctions' }), 'chennai')

    await waitFor(() => expect(queryLink('Mumbai to Rotterdam')).not.toBeInTheDocument())
    expect(link('Chennai to Singapore')).toBeInTheDocument()
    const searches = callsTo(fetchMock, '/api/rfqs').map((url) => url.searchParams.get('search'))
    expect(searches.filter(Boolean)).toEqual(['chennai'])
  })

  it('explains an empty search and clears it', async () => {
    const user = userEvent.setup()
    mockApi({
      '/api/rfqs': (url) => respond(listing(url.searchParams.get('search') ? [] : ALL)),
    })
    renderApp('/?search=atlantis')
    expect(await screen.findByText('No auctions match')).toBeInTheDocument()
    expect(screen.getByText('Nothing matches “atlantis”.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await findLink('Mumbai to Rotterdam')).toBeInTheDocument()
    expect(screen.getByRole('searchbox')).toHaveValue('')
  })

  it('invites buyers to create the first RFQ, and tells suppliers to wait', async () => {
    mockApi()
    const first = renderApp()
    expect(await screen.findByText('No auctions yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Create the first RFQ' })).toHaveAttribute('href', '/rfqs/new')
    first.unmount()

    window.localStorage.setItem(STORAGE_KEY, 's1')
    renderApp()
    expect(await screen.findByText('When a buyer creates an RFQ it appears here, live.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Create the first RFQ' })).not.toBeInTheDocument()
  })

  it('shows an error with a retry', async () => {
    const user = userEvent.setup()
    let fail = true
    mockApi({
      '/api/rfqs': () =>
        fail ? respond({ error: { code: 'NOT_FOUND', message: 'x' } }, 404) : respond(listing(ALL)),
    })
    renderApp()
    expect(await screen.findByText('Couldn’t load auctions')).toBeInTheDocument()
    fail = false
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await findLink('Mumbai to Rotterdam')).toBeInTheDocument()
  })

  it('pages through long lists', async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      '/api/rfqs': (url) => respond(listing(ALL, { total: 45, page: Number(url.searchParams.get('page') ?? 1) })),
    })
    renderApp()
    expect(await screen.findByText('1–20 of 45')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '← Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next →' }))
    expect(await screen.findByText('21–40 of 45')).toBeInTheDocument()
    expect(callsTo(fetchMock, '/api/rfqs').at(-1)?.searchParams.get('page')).toBe('2')
  })

  describe('live updates', () => {
    it('subscribes to the listing channel and applies newer rows only', async () => {
      const fetchMock = mockApi({ '/api/rfqs': () => respond(listing(ALL)) })
      renderApp()
      await screen.findByRole('table')
      const socket = openSocket()
      expect(socket.sent).toContainEqual({ action: 'subscribe', channel: 'listing' })
      const fetchesBefore = callsTo(fetchMock, '/api/rfqs').length

      serverSends({
        type: 'listing.updated',
        channel: 'listing',
        data: {
          version: 41,
          item: { ...ACTIVE, version: 41, bid_count: 8, lowest_bid: { amount: '110000.00', currency: 'INR', supplier_name: 'BlueWave Logistics' } },
        },
      })
      expect(rowFor('Mumbai to Rotterdam')).toHaveTextContent('₹1,10,000')
      expect(rowFor('Mumbai to Rotterdam')).toHaveTextContent('BlueWave Logistics')
      expect(rowFor('Mumbai to Rotterdam')).toHaveClass('animate-flash')

      // A late, older event must not move the row backwards.
      serverSends({
        type: 'listing.updated',
        channel: 'listing',
        data: { version: 40, item: { ...ACTIVE, version: 40, lowest_bid: { amount: '999999.00', currency: 'INR', supplier_name: 'Old' } } },
      })
      expect(rowFor('Mumbai to Rotterdam')).toHaveTextContent('₹1,10,000')

      // Then the list is refetched once (order and membership may have changed).
      await waitFor(() => expect(callsTo(fetchMock, '/api/rfqs').length).toBe(fetchesBefore + 1))
      // The refetch still returns version 40: the newer live row stays.
      expect(rowFor('Mumbai to Rotterdam')).toHaveTextContent('₹1,10,000')
    })

    it('lets a newer REST row replace an older live row', async () => {
      let rest = ACTIVE
      const fetchMock = mockApi({ '/api/rfqs': () => respond(listing([rest])) })
      renderApp()
      await screen.findByRole('table')
      openSocket()
      serverSends({
        type: 'listing.updated',
        channel: 'listing',
        data: { version: 41, item: { ...ACTIVE, version: 41, lowest_bid: { amount: '110000.00', currency: 'INR', supplier_name: 'BlueWave Logistics' } } },
      })
      // Meanwhile another bid happened whose event this tab missed; the refetch has it.
      rest = { ...ACTIVE, version: 42, lowest_bid: { amount: '105000.00', currency: 'INR', supplier_name: 'Swift Cargo' } }
      const before = callsTo(fetchMock, '/api/rfqs').length
      await waitFor(() => expect(callsTo(fetchMock, '/api/rfqs').length).toBe(before + 1))
      await waitFor(() => expect(rowFor('Mumbai to Rotterdam')).toHaveTextContent('₹1,05,000'))
    })

    it('refetches when a new RFQ is created and after a resync', async () => {
      let items = [ACTIVE]
      const fetchMock = mockApi({ '/api/rfqs': () => respond(listing(items)) })
      renderApp()
      await screen.findByRole('table')
      openSocket()

      items = [ACTIVE, UPCOMING]
      serverSends({ type: 'rfq.created', channel: 'listing', data: { version: 3, item: UPCOMING } })
      expect(await findLink('Chennai to Singapore')).toBeInTheDocument()

      const before = callsTo(fetchMock, '/api/rfqs').length
      serverSends({ type: 'resync', channel: null, data: {} })
      await waitFor(() => expect(callsTo(fetchMock, '/api/rfqs').length).toBe(before + 1))
    })

    it('shows “Closing…” at zero and asks the server for the outcome', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        const closing = item({ current_close_at: new Date(Date.now() + 1500).toISOString() })
        let closed = false
        const fetchMock = mockApi({
          '/api/rfqs': () => respond(listing([closed ? { ...closing, status: 'CLOSED', version: 41 } : closing])),
        })
        renderApp()
        await screen.findByRole('table')
        const before = callsTo(fetchMock, '/api/rfqs').length

        closed = true // e.g. no status event arrived (worker down): the REST status is derived
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1600)
        })
        expect(rowFor('Mumbai to Rotterdam')).toHaveTextContent('Closing…')
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1600)
        })
        await waitFor(() => expect(rowFor('Mumbai to Rotterdam')).toHaveTextContent('Closed'))
        expect(callsTo(fetchMock, '/api/rfqs').length).toBe(before + 1)
      } finally {
        vi.useRealTimers()
      }
    })
  })
})
