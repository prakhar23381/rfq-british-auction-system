/** Helpers shared by the end-to-end tests: API shortcuts and acting-as contexts. */
import { type Browser, type BrowserContext, expect, type Page, request } from '@playwright/test'

export const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'

export interface User {
  id: string
  name: string
  company_name: string
  role: 'BUYER' | 'SUPPLIER'
}

export async function users(): Promise<{ buyer: User; suppliers: User[] }> {
  const api = await request.newContext({ baseURL: API_URL })
  const res = await api.get('/api/users')
  expect(res.ok(), 'API reachable and seeded (make api, make seed)').toBeTruthy()
  const items = ((await res.json()) as { items: User[] }).items
  await api.dispose()
  const buyer = items.find((u) => u.role === 'BUYER')
  const suppliers = items.filter((u) => u.role === 'SUPPLIER')
  if (!buyer || suppliers.length < 3) throw new Error('Seed the database first: make seed')
  return { buyer, suppliers }
}

/** A browser context that acts as `user` (the app reads the choice from localStorage). */
export async function actingAs(browser: Browser, user: User, viewport = { width: 1440, height: 1000 }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport, timezoneId: 'Asia/Kolkata', locale: 'en-IN' })
  // Only on the first load: a later switch in the UI must survive reloads.
  await context.addInitScript((id) => {
    if (!window.localStorage.getItem('acting-user-id')) window.localStorage.setItem('acting-user-id', id)
  }, user.id)
  const page = await context.newPage()
  return { context, page }
}

interface AuctionOptions {
  name: string
  startIn?: number // seconds
  closeIn: number
  forcedIn: number
  x: number
  y: number
  trigger?: 'BID_RECEIVED' | 'ANY_RANK_CHANGE' | 'L1_CHANGE'
}

export async function createAuction(buyer: User, o: AuctionOptions): Promise<{ id: string; reference_id: string }> {
  const api = await request.newContext({ baseURL: API_URL })
  const at = (seconds: number) => new Date(Date.now() + seconds * 1000).toISOString()
  const res = await api.post('/api/rfqs', {
    headers: { 'X-User-Id': buyer.id },
    data: {
      name: o.name,
      pickup_date: new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10),
      bid_start_at: at(o.startIn ?? 0),
      bid_close_at: at(o.closeIn),
      forced_close_at: at(o.forcedIn),
      auction_config: {
        trigger_window_minutes: o.x,
        extension_duration_minutes: o.y,
        trigger_type: o.trigger ?? 'BID_RECEIVED',
      },
    },
  })
  expect(res.status(), await res.text()).toBe(201)
  const body = (await res.json()) as { rfq: { id: string; reference_id: string } }
  await api.dispose()
  return body.rfq
}

export async function bidViaApi(rfqId: string, supplier: User, total: number): Promise<{ status: number; body: Record<string, unknown> }> {
  const api = await request.newContext({ baseURL: API_URL })
  const res = await api.post(`/api/rfqs/${rfqId}/bids`, {
    headers: { 'X-User-Id': supplier.id },
    data: {
      carrier_name: `${supplier.company_name} Line`,
      freight_charges: `${total}.00`,
      origin_charges: '0.00',
      destination_charges: '0.00',
      transit_time_days: 20,
      quote_validity_date: new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10),
    },
  })
  const result = { status: res.status(), body: (await res.json()) as Record<string, unknown> }
  await api.dispose()
  return result
}

/** Unique names keep parallel tests (and reruns) from seeing each other's auctions. */
export function uniqueName(label: string): string {
  return `${label} ${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`
}

export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow, 'page scrolls sideways').toBeLessThanOrEqual(0)
}
