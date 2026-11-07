/** Automated accessibility checks (axe-core, WCAG 2.1 AA rules) on every page and state. */
import AxeBuilder from '@axe-core/playwright'
import { expect, type Page, test } from '@playwright/test'

import { actingAs, bidViaApi, createAuction, uniqueName, users } from './support'

async function expectAccessible(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect.soft(
    serious.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).slice(0, 3).join(', ')})`),
    `${label} has serious accessibility problems`,
  ).toEqual([])
}

test('pages have no serious accessibility violations', async ({ browser }) => {
  const { buyer, suppliers } = await users()
  const rfq = await createAuction(buyer, { name: uniqueName('E2E a11y'), closeIn: 900, forcedIn: 1200, x: 5, y: 5 })
  expect((await bidViaApi(rfq.id, suppliers[0], 50_000)).status).toBe(201)

  const b = await actingAs(browser, buyer)
  await b.page.goto('/')
  await b.page.getByRole('table', { name: 'British auctions' }).waitFor()
  await expectAccessible(b.page, 'Listing')

  await b.page.goto('/rfqs/new')
  await b.page.getByLabel('RFQ name').waitFor()
  await expectAccessible(b.page, 'Create RFQ')
  await b.page.getByRole('button', { name: 'Create RFQ' }).click() // with errors showing
  await expectAccessible(b.page, 'Create RFQ with errors')

  await b.page.goto(`/rfqs/${rfq.id}`)
  await b.page.getByRole('table', { name: /Supplier ranking/ }).waitFor()
  await expectAccessible(b.page, 'Details (buyer)')

  await b.page.getByRole('button', { name: /Acting as/ }).click()
  await expectAccessible(b.page, 'User menu open')
  await b.context.close()

  const s = await actingAs(browser, suppliers[0])
  await s.page.goto(`/rfqs/${rfq.id}`)
  await s.page.getByRole('form', { name: 'Place a bid' }).waitFor()
  await expectAccessible(s.page, 'Details with bid form (supplier)')
  await s.context.close()
})
