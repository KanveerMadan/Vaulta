// Visual snapshots of key screens, light and dark, desktop and 360px (the project sets the viewport).
// Figures and dates depend on the day the data was seeded, so they are masked; layout,
// typography and colour are what these guard. Update with: npx playwright test e2e/visual.spec.js --update-snapshots
import { test, expect, newAccount, signIn, seedData, callApi, centre } from './fixtures'

const SNAP = { maxDiffPixelRatio: 0.015, animations: 'disabled', fullPage: false }
const dynamic = (page) => [page.locator('.num'), page.locator('[data-value]'), page.locator('time'), page.getByTestId('outlook')]

async function settle(page) {
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(300)
  // The figures and dates here depend on the day and are masked, but a mask takes the size of what it covers: a longer
  // weekday or a different forecast moved the masks and failed the comparison the next day. Pin those sizes (set
  // through the CSSOM, which the page's strict CSP allows, unlike an injected stylesheet).
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('main time')) Object.assign(el.style, { display: 'inline-block', width: '11em', overflow: 'hidden', whiteSpace: 'nowrap', verticalAlign: 'bottom' })
    for (const el of document.querySelectorAll('main [data-testid="outlook"]')) Object.assign(el.style, { height: '210px', overflow: 'hidden' })
  })
}

for (const scheme of ['light', 'dark']) {
  test.describe(`${scheme}`, () => {
    test.use({ colorScheme: scheme })

    test('public screens', async ({ page }) => {
      await page.goto('/welcome'); await settle(page)
      await expect(page).toHaveScreenshot(`landing-${scheme}.png`, SNAP)
      await page.goto('/security'); await settle(page)
      await expect(page).toHaveScreenshot(`security-${scheme}.png`, SNAP)
      await page.goto('/login'); await settle(page)
      await expect(page).toHaveScreenshot(`login-${scheme}.png`, SNAP)
    })

    test('workspace screens', async ({ page, request }) => {
      const account = await newAccount(request)
      await callApi(request, account, 'GET', '/auth/me')
      await seedData(request, account)
      const report = await callApi(request, account, 'POST', '/api/reports/generate', { period_type: 'monthly' })
      await signIn(page, account)
      const mask = (p) => ({ ...SNAP, mask: dynamic(p) })
      await page.goto('/'); await settle(page)
      await expect(page).toHaveScreenshot(`home-${scheme}.png`, { ...mask(page), mask: [...dynamic(page), page.locator('section[aria-label="Recent transactions"]'), page.locator('section[aria-label="Coverage"]'), page.locator('section[aria-label="Needs attention"]')] })
      await page.goto('/budgets'); await settle(page)
      await expect(page).toHaveScreenshot(`budgets-${scheme}.png`, mask(page))
      await page.goto(`/reports/${report.id}`); await settle(page)
      await expect(page).toHaveScreenshot(`report-${scheme}.png`, { ...mask(page), mask: [...dynamic(page), page.locator('h1'), page.locator('header p'), page.locator('section[aria-labelledby="summary-title"]'), page.locator('main section ul, main section ol, main section figure')] })
      await page.goto('/settings'); await settle(page)
      await expect(page).toHaveScreenshot(`settings-${scheme}.png`, mask(page))
    })

    test('guided tour, getting-started checklist and samples', async ({ page, request }) => {
      const account = await newAccount(request)
      await callApi(request, account, 'GET', '/auth/me')
      await seedData(request, account)
      await callApi(request, account, 'PATCH', '/api/tour', { status: 'active', step: 1 })    // the quick-add step
      await signIn(page, account)
      const card = page.getByTestId('tour').getByRole('dialog')
      await expect(card).toHaveAccessibleName('Add anything in one line')
      await settle(page)
      await centre(page, 'quick-add')     // settle() resizes masked blocks: put the step back where the tour put it
      const inPage = [page.locator('main .num'), page.locator('main [data-value]'), page.locator('main time'), page.locator('main [data-testid="outlook"]')]
      await expect(page).toHaveScreenshot(`tour-${scheme}.png`, { ...SNAP, mask: inPage })      // never over the tour itself
      await page.keyboard.press('Escape')
      const checklist = page.getByTestId('getting-started')
      await checklist.scrollIntoViewIfNeeded(); await settle(page)
      await expect(checklist).toHaveScreenshot(`checklist-${scheme}.png`, { ...SNAP, mask: [checklist.locator('.num')] })
      await page.goto('/try'); await settle(page)
      await expect(page).toHaveScreenshot(`try-${scheme}.png`, SNAP)
    })

    test('onboarding', async ({ page, request }) => {
      const account = await newAccount(request)
      await signIn(page, account)
      await page.goto('/onboarding'); await settle(page)
      await expect(page).toHaveScreenshot(`onboarding-${scheme}.png`, SNAP)
    })
  })
}
