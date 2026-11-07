import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { RfqCreate } from '../api/types'
import { callsTo, listing, mockApi, renderApp, respond } from '../test/app'
import { setTimeZone } from '../test/timeZone'

const MIN = 60_000

let restoreTimeZone: () => void
beforeAll(() => {
  restoreTimeZone = setTimeZone('Asia/Kolkata')
})
afterAll(() => restoreTimeZone())
afterEach(() => vi.unstubAllGlobals())

function created(body: RfqCreate) {
  return {
    rfq: {
      id: 'new-rfq-id',
      reference_id: body.reference_id ?? 'RFQ-2026-0042',
      name: body.name,
      status: 'SCHEDULED',
      pickup_date: body.pickup_date,
      bid_start_at: body.bid_start_at,
      bid_close_at: body.bid_close_at,
      current_close_at: body.bid_close_at,
      forced_close_at: body.forced_close_at,
      extension_count: 0,
      closed_at: null,
      created_at: new Date().toISOString(),
      buyer: { id: 'b1', name: 'Asha Mehta', company_name: 'Acme Exports' },
      version: 1,
    },
    auction_config: body.auction_config,
    ranking: [],
    stats: {
      bid_count: 0,
      supplier_count: 0,
      extension_count: 0,
      total_extended_minutes: 0,
      first_l1_amount: null,
      current_l1_amount: null,
      savings_pct: null,
    },
  }
}

/** POST /api/rfqs answers with `answer(body)`; GET returns an empty listing. */
function mockCreate(answer: (body: RfqCreate) => Response = (body) => respond(created(body), 201)) {
  return mockApi({
    '/api/rfqs': (_, init) =>
      init?.method === 'POST' ? answer(JSON.parse(String(init.body)) as RfqCreate) : respond(listing([])),
  })
}

const posts = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls
    .filter(([input, init]) => String(input) === '/api/rfqs' && init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)) as RfqCreate)

const field = (label: RegExp | string) => screen.getByLabelText(label)
const submit = () => userEvent.click(screen.getByRole('button', { name: 'Create RFQ' }))

async function openForm() {
  renderApp('/rfqs/new')
  return screen.findByRole('heading', { level: 1, name: 'Create a British auction' })
}

describe('Create RFQ page', () => {
  it('starts with sensible defaults and explains them (R1–R5)', async () => {
    mockCreate()
    await openForm()
    expect(field('RFQ name')).toHaveValue('')
    expect(field(/Trigger window/)).toHaveValue(10)
    expect(field(/Extension duration/)).toHaveValue(5)
    expect(screen.getByRole('radio', { name: /Lowest bidder \(L1\) changes/ })).toBeChecked()
    expect(screen.getByRole('switch', { name: /British auction/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('Your time zone · IST')).toBeInTheDocument()

    const preview = screen.getByRole('heading', { name: 'How it will run' }).closest('section') as HTMLElement
    // Close + 30 min forced close with Y = 5: at most 6 extensions.
    expect(preview).toHaveTextContent('at most 6 extensions')
    expect(preview).toHaveTextContent(/Monitoring window: \d\d:\d\d–\d\d:\d\d/)
    expect(within(preview).getByRole('img')).toHaveAccessibleName(/^Bidding \d\d:\d\d to \d\d:\d\d/)
  })

  it('creates the RFQ with UTC times and opens it', async () => {
    const fetchMock = mockCreate()
    await openForm()
    await userEvent.type(field('RFQ name'), '  Chennai to Singapore  ')
    await userEvent.click(screen.getByRole('radio', { name: /Bid received/ }))
    await submit()

    // The new auction's page opens (from the cached response, no extra request needed).
    expect(await screen.findByRole('heading', { level: 1, name: 'Chennai to Singapore' })).toBeInTheDocument()
    expect(await screen.findByText('RFQ created')).toBeInTheDocument()
    const [body] = posts(fetchMock)
    expect(body).toMatchObject({
      name: 'Chennai to Singapore',
      reference_id: null,
      auction_config: { trigger_window_minutes: 10, extension_duration_minutes: 5, trigger_type: 'BID_RECEIVED' },
    })
    const start = Date.parse(body.bid_start_at)
    expect(body.bid_start_at).toMatch(/Z$/)
    expect(start - Date.now()).toBeGreaterThan(MIN)
    expect(start - Date.now()).toBeLessThanOrEqual(3 * MIN)
    expect(Date.parse(body.bid_close_at) - start).toBe(30 * MIN)
    expect(Date.parse(body.forced_close_at) - Date.parse(body.bid_close_at)).toBe(30 * MIN)
  })

  it('shows inline errors and sends nothing while the form is invalid', async () => {
    const fetchMock = mockCreate()
    await openForm()
    await submit()
    expect(field('RFQ name')).toHaveAccessibleDescription('Enter a name for the RFQ.')
    expect(field('RFQ name')).toHaveFocus()

    await userEvent.type(field('RFQ name'), 'Delhi to Dubai')
    fireEvent.change(field('Bid close'), { target: { value: '2030-01-01T10:00' } })
    fireEvent.change(field('Forced bid close'), { target: { value: '2030-01-01T10:00' } })
    await submit()
    // The default pickup date is now before the close: focus goes to the first problem.
    expect(field(/Pickup/)).toHaveFocus()
    expect(field(/Pickup/)).toHaveAccessibleDescription('Pickup / service date can’t be before the bid close date.')
    fireEvent.change(field(/Pickup/), { target: { value: '2030-01-02' } })
    await submit()
    expect(field('Forced bid close')).toHaveAttribute('aria-invalid', 'true')
    expect(field('Forced bid close')).toHaveAccessibleDescription('Forced close must be after the bid close time.')
    expect(field('Forced bid close')).toHaveFocus()
    expect(screen.getByText('Fix the highlighted fields to see how this auction will run.')).toBeInTheDocument()
    expect(posts(fetchMock)).toHaveLength(0)

    // Fixing it clears the error straight away.
    fireEvent.change(field('Forced bid close'), { target: { value: '2030-01-01T10:20' } })
    expect(field('Forced bid close')).not.toHaveAttribute('aria-invalid')
  })

  it('validates a field when you leave it', async () => {
    mockCreate()
    await openForm()
    await userEvent.type(field(/Trigger window/), '0') // "100"
    await userEvent.clear(field(/Trigger window/))
    await userEvent.type(field(/Trigger window/), '0')
    expect(field(/Trigger window/)).not.toHaveAttribute('aria-invalid') // not yet touched
    await userEvent.tab()
    expect(field(/Trigger window/)).toHaveAccessibleDescription('Enter whole minutes from 1 to 120.')
  })

  it('updates the preview as the settings change', async () => {
    mockCreate()
    await openForm()
    await userEvent.clear(field(/Extension duration/))
    await userEvent.type(field(/Extension duration/), '7')
    const preview = screen.getByRole('heading', { name: 'How it will run' }).closest('section') as HTMLElement
    // 30 min of room with Y = 7: ⌈30 / 7⌉ = 5, the last one cut to 2 min.
    expect(preview).toHaveTextContent('at most 5 extensions, the last one cut to 2 min')
    expect(screen.getByRole('radio', { name: /Bid received/ }).closest('label')).toHaveTextContent(/moves the close to \d\d:\d\d/)
  })

  it('offers to move a schedule whose start has passed', async () => {
    mockCreate()
    await openForm()
    fireEvent.change(field('Bid start'), { target: { value: '2020-01-01T10:00' } })
    fireEvent.blur(field('Bid start'))
    expect(field('Bid start')).toHaveAccessibleDescription('Bid start can’t be in the past.')
    await userEvent.click(screen.getByRole('button', { name: 'Move the schedule to start in 2 minutes' }))
    expect(field('Bid start')).not.toHaveAttribute('aria-invalid')
  })

  it('shows server errors next to the field they belong to', async () => {
    const fetchMock = mockCreate(() =>
      respond(
        {
          error: {
            code: 'DUPLICATE_REFERENCE',
            message: 'Reference ID RFQ-2026-0001 is already in use',
            details: [{ field: 'reference_id', message: 'Already in use' }],
          },
        },
        409,
      ),
    )
    await openForm()
    await userEvent.type(field('RFQ name'), 'Delhi to Dubai')
    await userEvent.type(field(/Reference ID/), 'rfq-2026-0001')
    expect(field(/Reference ID/)).toHaveValue('RFQ-2026-0001')
    await submit()

    await waitFor(() => expect(field(/Reference ID/)).toHaveAccessibleDescription('Already in use'))
    expect(field(/Reference ID/)).toHaveFocus()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(posts(fetchMock)[0].reference_id).toBe('RFQ-2026-0001')

    await userEvent.type(field(/Reference ID/), 'X')
    expect(field(/Reference ID/)).not.toHaveAttribute('aria-invalid')
  })

  it('maps the forced-close rule when the server enforces it', async () => {
    mockCreate(() =>
      respond(
        {
          error: {
            code: 'FORCED_CLOSE_NOT_AFTER_CLOSE',
            message: 'Forced bid close time must be later than the bid close time',
            details: [{ field: 'forced_close_at', message: 'Forced bid close time must be later than the bid close time' }],
          },
        },
        422,
      ),
    )
    await openForm()
    await userEvent.type(field('RFQ name'), 'Delhi to Dubai')
    await submit()
    await waitFor(() =>
      expect(field('Forced bid close')).toHaveAccessibleDescription('Forced bid close time must be later than the bid close time'),
    )
  })

  it('shows a banner for errors that belong to no field', async () => {
    const fetchMock = mockCreate(() => respond({ error: { code: 'INTERNAL_ERROR', message: 'boom' } }, 500))
    await openForm()
    await userEvent.type(field('RFQ name'), 'Delhi to Dubai')
    await submit()
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong on the server. Please try again.')
    expect(screen.getByRole('button', { name: 'Create RFQ' })).toBeEnabled()
    expect(callsTo(fetchMock, '/api/rfqs').length).toBeGreaterThan(0)
  })
})
