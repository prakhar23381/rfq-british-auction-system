/**
 * An auction's whole life as the browser sees it: it opens on time, late bids extend it, the
 * forced close caps it, and it force-closes on schedule (Celery jobs → WebSocket → UI).
 */
import { expect, test } from '@playwright/test'

import { actingAs, bidViaApi, createAuction, uniqueName, users } from './support'

test('extends until the forced close, then force-closes on time', async ({ browser }) => {
  test.setTimeout(150_000)
  const { buyer, suppliers } = await users()
  const [s1, s2, s3] = suppliers
  // Opens in 4 s, closes at 30 s, forced close at 70 s; X = 2 min covers the whole auction.
  const rfq = await createAuction(buyer, { name: uniqueName('E2E force close'), startIn: 4, closeIn: 30, forcedIn: 70, x: 2, y: 1 })

  const { context, page } = await actingAs(browser, s3)
  await page.goto(`/rfqs/${rfq.id}`)
  await expect(page.getByText('Opens in', { exact: true })).toBeVisible()
  await expect(page.getByText(/^Bidding opens at/)).toBeVisible()

  // Opens without a reload (the start job publishes auction.status).
  await expect(page.getByText('Closes in', { exact: true })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('Bidding is open', { exact: true })).toBeVisible()
  await expect(page.getByRole('form', { name: 'Place a bid' })).toBeVisible()

  // Every bid is in the window (BID_RECEIVED): +1 min each, until the forced close.
  let total = 60_000
  for (const supplier of [s1, s2, s1, s2]) {
    expect((await bidViaApi(rfq.id, supplier, total)).status).toBe(201)
    total -= 1000
  }
  await expect(page.getByText(/Extended \+[0-9a-z ]+ \(\d×\)/)).toBeVisible()
  const log = page.getByRole('list', { name: 'Activity log' })
  await expect(log.getByText('capped').first()).toBeVisible()
  await expect(log).toContainText('No extension') // the trigger fired at the cap: logged, not applied

  // Force-closes on time, live, and the form shuts.
  await expect(page.getByText('Closed at', { exact: true })).toBeVisible({ timeout: 70_000 })
  await expect(page.getByText('Auction force closed', { exact: true })).toBeVisible() // the toast
  await expect(page.getByText('Force closed', { exact: true }).first()).toBeVisible() // status badge
  await expect(page.getByText('Bidding has closed for this auction.')).toBeVisible()
  await expect(page.getByRole('button', { name: /Place (a lower )?bid/ })).toBeDisabled()
  await expect(log).toContainText('force closed')

  // The API agrees, and late bids are refused.
  const late = await bidViaApi(rfq.id, s2, 1000)
  expect(late.status).toBe(409)
  expect((late.body.error as { code: string }).code).toBe('AUCTION_CLOSED')
  await context.close()
})
