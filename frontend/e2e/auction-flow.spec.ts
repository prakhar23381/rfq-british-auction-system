/**
 * The main flow across two people at once (Stage 12 DoD): a buyer creates an RFQ in the UI,
 * suppliers bid in their own windows, and everyone sees bids, rank changes and extensions
 * live, without reloading.
 */
import { expect, test } from '@playwright/test'

import { actingAs, bidViaApi, uniqueName, users } from './support'

test('buyer creates an RFQ; suppliers bid; everyone sees it live', async ({ browser }) => {
  const { buyer, suppliers } = await users()
  const [alpha, beta] = suppliers
  const name = uniqueName('E2E Chennai to Singapore')

  // --- Buyer creates the RFQ through the form ---------------------------------------------
  const b = await actingAs(browser, buyer)
  await b.page.goto('/rfqs/new')
  await b.page.getByLabel('RFQ name').fill(name)
  // Start now (the current minute is allowed), close in 4 min, forced close 2 min later.
  const times = await b.page.evaluate(() => {
    const pad = (n: number) => String(n).padStart(2, '0')
    const local = (d: Date) =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    const now = new Date()
    return {
      start: local(now),
      close: local(new Date(now.getTime() + 4 * 60_000)),
      forced: local(new Date(now.getTime() + 6 * 60_000)),
    }
  })
  await b.page.getByLabel('Bid start').fill(times.start)
  await b.page.getByLabel('Bid close', { exact: true }).fill(times.close)
  await b.page.getByLabel('Forced bid close').fill(times.forced)
  await b.page.getByLabel('Trigger window (X)').fill('10') // the whole auction is "late"
  await b.page.getByLabel('Extension duration (Y)').fill('1')
  await b.page.getByText('Bid received', { exact: true }).click() // the card's label, as a person would
  await expect(b.page.getByRole('radio', { name: /Bid received/ })).toBeChecked()
  await expect(b.page.getByText(/at most 2 extensions/)).toBeVisible()
  await b.page.getByRole('button', { name: 'Create RFQ' }).click()

  await expect(b.page.getByRole('heading', { level: 1, name })).toBeVisible()
  await expect(b.page.getByText('RFQ created')).toBeVisible()
  const url = b.page.url()
  const rfqId = url.split('/').pop() as string
  await expect(b.page.getByText('Closes in')).toBeVisible({ timeout: 20_000 })

  // --- Supplier A bids through the form; the buyer sees it live --------------------------
  const a = await actingAs(browser, alpha)
  await a.page.goto(url)
  const form = a.page.getByRole('form', { name: 'Place a bid' })
  await expect(form.getByText(/You’re inside the trigger window/)).toBeVisible()
  await form.getByLabel('Carrier').fill('Alpha Ocean Line')
  await form.getByLabel('Freight').fill('48000')
  await form.getByLabel('Origin').fill('1500.50')
  await form.getByLabel('Destination').fill('500')
  await expect(form.getByText('₹50,000.50')).toBeVisible() // live total
  await form.getByLabel('Transit time').fill('19')
  await form.getByRole('button', { name: 'Place bid' }).click()
  await expect(a.page.getByText('Bid placed · you’re L1')).toBeVisible()

  const buyerRanking = b.page.getByRole('table', { name: /Supplier ranking/ })
  await expect(buyerRanking.getByRole('row').nth(1)).toContainText(alpha.company_name)
  await expect(buyerRanking.getByRole('row').nth(1)).toContainText('₹50,000.50')
  await expect(b.page.getByText(/^Auction extended to \d\d:\d\d$/)).toBeVisible() // toast on the buyer side
  await expect(b.page.getByText('+1 ext').first()).toBeVisible()

  // --- Supplier B undercuts from another window: A is told, the buyer sees the new order ---
  const res = await bidViaApi(rfqId, beta, 45_000)
  expect(res.status).toBe(201)
  await expect(a.page.getByText('You’ve been outbid · now L2')).toBeVisible()
  await expect(buyerRanking.getByRole('row').nth(1)).toContainText(beta.company_name)
  await expect(buyerRanking.getByRole('row').nth(2)).toContainText(alpha.company_name)

  // A's form now knows A is L2 and must go lower than its own bid.
  await expect(form).toContainText('Your current bid ₹50,000.50 (L2)')
  await form.getByLabel('Freight').fill('49000')
  await form.getByRole('button', { name: 'Place a lower bid' }).click()
  await expect(form.getByRole('alert')).toHaveText('Your new total must be lower than your current bid.')

  // --- The activity log explains each extension -----------------------------------------
  const log = b.page.getByRole('list', { name: 'Activity log' })
  await expect(log).toContainText(`Bid received from ${beta.company_name}`)
  await expect(log.getByText(/\d\d:\d\d → \d\d:\d\d/).first()).toBeVisible()

  // --- The listing shows the new lowest bid, live -----------------------------------------
  await b.page.getByRole('link', { name: 'Auctions' }).first().click()
  await b.page.getByRole('searchbox', { name: 'Search auctions' }).fill(name)
  const row = b.page.getByRole('table', { name: 'British auctions' }).getByRole('row', { name: new RegExp(name) })
  await expect(row).toContainText('₹45,000')
  await bidViaApi(rfqId, alpha, 44_000)
  await expect(row).toContainText('₹44,000')
  await expect(row).toContainText(alpha.company_name)
  await expect(row).toContainText(/\+\d ext/)

  // --- A reload mid-auction shows the same state ------------------------------------------
  await a.page.reload()
  await expect(a.page.getByRole('table', { name: /Supplier ranking/ }).getByRole('row').nth(1)).toContainText(alpha.company_name)

  await Promise.all([a.context.close(), b.context.close()])
})
