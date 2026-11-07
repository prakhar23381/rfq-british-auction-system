/** Helpers for rendering the whole app against a mocked API. */
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'

import { App } from '../App'
import type { RfqListItem, RfqListResponse, User } from '../api/types'
import { Providers } from '../providers'
import { createQueryClient } from '../queryClient'

export const USERS: User[] = [
  { id: 'b1', name: 'Asha Mehta', email: 'asha@acme.test', company_name: 'Acme Exports', role: 'BUYER' },
  { id: 's1', name: 'Ravi Kumar', email: 'ravi@bluewave.test', company_name: 'BlueWave Logistics', role: 'SUPPLIER' },
  { id: 's2', name: 'Meera Iyer', email: 'meera@swift.test', company_name: 'Swift Cargo', role: 'SUPPLIER' },
]

export function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export const HEALTHY = { status: 'ok', db: 'ok', redis: 'ok', realtime: 'ok' }

export function listing(items: RfqListItem[], overrides: Partial<RfqListResponse> = {}): RfqListResponse {
  const counts = { SCHEDULED: 0, ACTIVE: 0, CLOSED: 0, FORCE_CLOSED: 0 }
  for (const item of items) counts[item.status] += 1
  return { items, page: 1, page_size: 20, total: items.length, status_counts: counts, ...overrides }
}

type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>

/**
 * Stubs fetch. `routes` maps a path ("/api/rfqs") to a handler; users and health have
 * defaults. Returns the mock, whose calls can be inspected.
 */
export function mockApi(routes: Record<string, Handler> = {}) {
  const handlers: Record<string, Handler> = {
    '/api/users': () => respond({ items: USERS }),
    '/api/health': () => respond(HEALTHY),
    '/api/rfqs': () => respond(listing([])),
    ...routes,
  }
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input), 'http://app.test')
    const handler = handlers[url.pathname]
    return handler
      ? handler(url, init)
      : respond({ error: { code: 'NOT_FOUND', message: `No mock for ${url.pathname}` } }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** URLs of the calls made to `path`, e.g. to check query parameters. */
export function callsTo(fetchMock: ReturnType<typeof mockApi>, path: string): URL[] {
  return fetchMock.mock.calls
    .map(([input]) => new URL(String(input), 'http://app.test'))
    .filter((url) => url.pathname === path)
}

export function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={createQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  )
}
