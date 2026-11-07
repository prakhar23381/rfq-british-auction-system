import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockApi, renderApp, respond, USERS } from './test/app'
import { STORAGE_KEY } from './user/userContext'

const createLinks = () => screen.queryAllByRole('link', { name: 'Create RFQ' })
const actingAsButton = () => screen.findByRole('button', { name: /Acting as/ })

describe('App shell', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('acts as the first buyer by default, who can create RFQs', async () => {
    mockApi()
    renderApp()
    expect(await actingAsButton()).toHaveTextContent('Acme Exports')
    expect(createLinks().length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('British auctions')
    expect(await screen.findByText('All systems normal')).toBeInTheDocument()
  })

  it('switching to a supplier changes the navigation and is remembered', async () => {
    mockApi()
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
    mockApi()
    window.localStorage.setItem(STORAGE_KEY, 's1')
    const first = renderApp()
    expect(await actingAsButton()).toHaveTextContent('BlueWave Logistics')
    first.unmount()

    // Even if suppliers came first in the list, the fallback is a buyer.
    mockApi({ '/api/users': () => respond({ items: [USERS[1], USERS[0], USERS[2]] }) })
    window.localStorage.setItem(STORAGE_KEY, 'deleted-by-a-reseed')
    renderApp()
    expect(await actingAsButton()).toHaveTextContent('Acme Exports')
  })

  it('keeps suppliers out of the create page, with a one-click switch', async () => {
    mockApi()
    const user = userEvent.setup()
    window.localStorage.setItem(STORAGE_KEY, 's1')
    renderApp('/rfqs/new')

    expect(await screen.findByText('Only a buyer can create an RFQ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Act as Acme Exports' }))
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Create a British auction')
  })

  it('supports the keyboard in the user menu', async () => {
    mockApi()
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
    mockApi()
    renderApp('/no/such/page')
    expect(await screen.findByText('This page doesn’t exist')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to auctions' })).toHaveAttribute('href', '/')
  })

  it('explains an auction that does not exist', async () => {
    mockApi({ '/api/rfqs/*': () => respond({ error: { code: 'NOT_FOUND', message: 'RFQ not found' } }, 404) })
    renderApp('/rfqs/abc-123')
    expect(await screen.findByText('This auction doesn’t exist')).toBeInTheDocument()
  })

  it('explains when the API is down', async () => {
    const down = () => respond({ error: { code: 'INTERNAL_ERROR', message: 'x' } }, 500)
    mockApi({ '/api/users': down, '/api/health': down, '/api/rfqs': down })
    renderApp()
    expect(await screen.findByRole('button', { name: /Users unavailable/ }, { timeout: 3000 })).toBeInTheDocument()
    expect(await screen.findByText('API unreachable')).toBeInTheDocument()
    expect(await screen.findByText('Couldn’t load auctions', {}, { timeout: 3000 })).toBeInTheDocument()
  })

  it('shows degraded systems in the sidebar', async () => {
    mockApi({
      '/api/health': () => respond({ status: 'error', db: 'ok', redis: 'error', realtime: 'error' }),
    })
    renderApp()
    await waitFor(() => expect(screen.getByText('Degraded: redis, realtime')).toBeInTheDocument())
  })
})
