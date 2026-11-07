import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import type { User } from './api/types'
import { Providers } from './providers'
import { createQueryClient } from './queryClient'
import { STORAGE_KEY } from './user/userContext'

const USERS: User[] = [
  { id: 'b1', name: 'Asha Mehta', email: 'asha@acme.test', company_name: 'Acme Exports', role: 'BUYER' },
  { id: 's1', name: 'Ravi Kumar', email: 'ravi@bluewave.test', company_name: 'BlueWave Logistics', role: 'SUPPLIER' },
  { id: 's2', name: 'Meera Iyer', email: 'meera@swift.test', company_name: 'Swift Cargo', role: 'SUPPLIER' },
]

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const fetchMock = vi.fn<typeof fetch>()

function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={createQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  )
}

const createLinks = () => screen.queryAllByRole('link', { name: 'Create RFQ' })
const actingAsButton = () => screen.findByRole('button', { name: /Acting as/ })

describe('App shell', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (input) => {
      const url = String(input)
      if (url.startsWith('/api/users')) return respond({ items: USERS, server_time: new Date().toISOString() })
      if (url.startsWith('/api/health'))
        return respond({ status: 'ok', db: 'ok', redis: 'ok', realtime: 'ok', server_time: new Date().toISOString() })
      return respond({ error: { code: 'NOT_FOUND', message: 'nope' } }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('acts as the first buyer by default, who can create RFQs', async () => {
    renderApp()
    expect(await actingAsButton()).toHaveTextContent('Acme Exports')
    expect(createLinks().length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('British auctions')
    expect(await screen.findByText('All systems normal')).toBeInTheDocument()
  })

  it('switching to a supplier changes the navigation and is remembered', async () => {
    const user = userEvent.setup()
    renderApp()
    await user.click(await actingAsButton())

    const menu = screen.getByRole('menu', { name: 'Act as' })
    expect(within(menu).getByRole('group', { name: 'Buyers' })).toHaveTextContent('Acme Exports')
    expect(within(menu).getByRole('menuitemradio', { name: /Acme Exports/ })).toHaveAttribute('aria-checked', 'true')
    await user.click(within(menu).getByRole('menuitemradio', { name: /Swift Cargo/ }))

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(await actingAsButton()).toHaveTextContent('Swift Cargo')
    expect(createLinks()).toHaveLength(0)
    expect(await screen.findByText('Acting as Swift Cargo')).toBeInTheDocument() // toast
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('s2')
  })

  it('restores the stored user, and falls back to a buyer when it is gone', async () => {
    window.localStorage.setItem(STORAGE_KEY, 's1')
    const first = renderApp()
    expect(await actingAsButton()).toHaveTextContent('BlueWave Logistics')
    first.unmount()

    // Even if suppliers came first in the list, the fallback is a buyer.
    fetchMock.mockImplementation(async () => respond({ items: [USERS[1], USERS[0], USERS[2]] }))
    window.localStorage.setItem(STORAGE_KEY, 'deleted-by-a-reseed')
    renderApp()
    expect(await actingAsButton()).toHaveTextContent('Acme Exports')
  })

  it('keeps suppliers out of the create page, with a one-click switch', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(STORAGE_KEY, 's1')
    renderApp('/rfqs/new')

    expect(await screen.findByText('Only a buyer can create an RFQ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Act as Acme Exports' }))
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Create a British auction')
  })

  it('supports the keyboard in the user menu', async () => {
    const user = userEvent.setup()
    renderApp()
    const button = await actingAsButton()
    button.focus()
    await user.keyboard('{ArrowDown}')
    const menu = screen.getByRole('menu')
    expect(within(menu).getByRole('menuitemradio', { name: /Acme Exports/ })).toHaveFocus()

    await user.keyboard('{ArrowDown}')
    expect(within(menu).getByRole('menuitemradio', { name: /BlueWave/ })).toHaveFocus()
    await user.keyboard('{End}')
    expect(within(menu).getByRole('menuitemradio', { name: /Swift Cargo/ })).toHaveFocus()
    await user.keyboard('{ArrowDown}') // wraps around
    expect(within(menu).getByRole('menuitemradio', { name: /Acme Exports/ })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(button).toHaveFocus()
  })

  it('shows a 404 page for unknown routes', async () => {
    renderApp('/no/such/page')
    expect(await screen.findByText('This page doesn’t exist')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to auctions' })).toHaveAttribute('href', '/')
  })

  it('opens the detail route with its id', async () => {
    renderApp('/rfqs/abc-123')
    expect(await screen.findByText('abc-123')).toBeInTheDocument()
  })

  it('explains when the users cannot be loaded', async () => {
    fetchMock.mockImplementation(async () => respond({ error: { code: 'INTERNAL_ERROR', message: 'x' } }, 500))
    renderApp()
    expect(await screen.findByRole('button', { name: /Users unavailable/ }, { timeout: 3000 })).toBeInTheDocument()
    expect(await screen.findByText('API unreachable')).toBeInTheDocument()
  })

  it('shows degraded systems in the sidebar', async () => {
    fetchMock.mockImplementation(async (input) =>
      String(input).startsWith('/api/health')
        ? respond({ status: 'error', db: 'ok', redis: 'error', realtime: 'error', server_time: new Date().toISOString() })
        : respond({ items: USERS }),
    )
    renderApp()
    await waitFor(() => expect(screen.getByText('Degraded: redis, realtime')).toBeInTheDocument())
  })
})
