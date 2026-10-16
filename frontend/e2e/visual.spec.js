// Visual snapshots of key screens, light and dark, desktop and 360px (the project sets the viewport).
// Figures and dates depend on the day the data was seeded, so they are masked; layout,
// typography and colour are what these guard. Update with: npx playwright test e2e/visual.spec.js --update-snapshots
import { test, expect, newAccount, signIn, seedData, callApi } from './fixtures'

const SNAP = { maxDiffPixelRatio: 0.015, animations: 'disabled', fullPage: false }
const dynamic = (page) => [page.locator('.num'), page.locator('[data-value]'), page.locator('time'), page.getByTestId('outlook')]

async function settle(page) {
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(300)
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

    test('onboarding', async ({ page, request }) => {
      const account = await newAccount(request)
      await signIn(page, account)
      await page.goto('/onboarding'); await settle(page)
      await expect(page).toHaveScreenshot(`onboarding-${scheme}.png`, SNAP)
    })
  })
}
