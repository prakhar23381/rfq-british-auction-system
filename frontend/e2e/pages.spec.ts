/** Page-level checks against the real API: validation, roles, 404s, phone widths. */
import { expect, test } from '@playwright/test'

import { actingAs, createAuction, expectNoHorizontalScroll, uniqueName, users } from './support'

test('the create form blocks invalid schedules and maps server errors', async ({ browser }) => {
  const { buyer } = await users()
  const { context, page } = await actingAs(browser, buyer)
  await page.goto('/rfqs/new')
  await page.getByLabel('RFQ name').fill(uniqueName('E2E validation'))
  const close = await page.getByLabel('Bid close', { exact: true }).inputValue()
  await page.getByLabel('Forced bid close').fill(close)
  await page.getByRole('button', { name: 'Create RFQ' }).click()
  await expect(page.getByLabel('Forced bid close')).toHaveAttribute('aria-invalid', 'true')
  await expect(page.getByText('Forced close must be after the bid close time.')).toBeVisible()
  await expect(page).toHaveURL(/\/rfqs\/new$/)

  // A reference ID that already exists comes back from the server onto that field.
  const taken = await createAuction(buyer, { name: uniqueName('E2E taken ref'), closeIn: 600, forcedIn: 900, x: 5, y: 5 })
  await page.getByLabel('Forced bid close').fill(await page.evaluate(() => {
    const pad = (n: number) => String(n).padStart(2, '0')
    const d = new Date(Date.now() + 3 * 3_600_000)
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  }))
  await page.getByLabel(/Reference ID/).fill(taken.reference_id)
  await page.getByRole('button', { name: 'Create RFQ' }).click()
  await expect(page.getByText('Already in use')).toBeVisible()
  await expect(page.getByLabel(/Reference ID/)).toBeFocused()
  await context.close()
})

test('suppliers cannot create RFQs; unknown pages and auctions are explained', async ({ browser }) => {
  const { suppliers } = await users()
  const { context, page } = await actingAs(browser, suppliers[0])
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Create RFQ' })).toHaveCount(0)
  await page.goto('/rfqs/new')
  await expect(page.getByText('Only a buyer can create an RFQ')).toBeVisible()
  await page.goto('/nope')
  await expect(page.getByText('This page doesn’t exist')).toBeVisible()
  await page.goto('/rfqs/00000000-0000-0000-0000-000000000000')
  await expect(page.getByText('This auction doesn’t exist')).toBeVisible()
  await context.close()
})

test('switching user changes what you can do', async ({ browser }) => {
  const { buyer, suppliers } = await users()
  const { context, page } = await actingAs(browser, buyer)
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Create RFQ' }).first()).toBeVisible()
  await page.getByRole('button', { name: /Acting as/ }).click()
  await page.getByRole('menuitemradio', { name: new RegExp(suppliers[1].company_name) }).click()
  await expect(page.getByRole('link', { name: 'Create RFQ' })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('button', { name: /Acting as/ })).toContainText(suppliers[1].company_name)
  await context.close()
})

test('every page fits a 390 px phone without sideways scrolling', async ({ browser }) => {
  const { buyer, suppliers } = await users()
  const rfq = await createAuction(buyer, { name: uniqueName('E2E phone'), closeIn: 600, forcedIn: 900, x: 5, y: 5 })
  for (const [user, path] of [
    [buyer, '/'],
    [buyer, '/rfqs/new'],
    [buyer, `/rfqs/${rfq.id}`],
    [suppliers[0], `/rfqs/${rfq.id}`],
    [suppliers[0], '/nope'],
  ] as const) {
    const { context, page } = await actingAs(browser, user, { width: 390, height: 844 })
    await page.goto(path)
    await page.getByRole('heading', { level: 1 }).or(page.getByText('This page doesn’t exist')).first().waitFor()
    await expectNoHorizontalScroll(page)
    await context.close()
  }
})
