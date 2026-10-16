// Automated accessibility checks (axe, WCAG 2.0/2.1/2.2 A and AA) on every page, in light and dark.
import AxeBuilder from '@axe-core/playwright'
import { test, expect, newAccount, signIn, seedData, callApi } from './fixtures'

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function audit(page, label) {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  const report = violations.map((v) => `${label}: ${v.id} (${v.impact}) ${v.help}\n  ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join('\n  ')}`)
  expect(report, report.join('\n')).toEqual([])
}

for (const scheme of ['light', 'dark']) {
  test.describe(`${scheme} theme`, () => {
    test.use({ colorScheme: scheme })

    test('public pages', async ({ page }) => {
      for (const path of ['/welcome', '/security', '/login']) {
        await page.goto(path)
        await audit(page, `${scheme} ${path}`)
      }
    })

    test('workspace pages', async ({ page, request }) => {
      const account = await newAccount(request)
      await callApi(request, account, 'GET', '/auth/me')
      await seedData(request, account)
      const report = await callApi(request, account, 'POST', '/api/reports/generate', { period_type: 'monthly' })
      await signIn(page, account)
      for (const path of ['/', '/transactions', '/budgets', '/goals', '/cash', '/recurring', '/reports', `/reports/${report.id}`,
        '/people', '/rules', '/connect', '/settings', '/review']) {
        await page.goto(path)
        await audit(page, `${scheme} ${path}`)
      }
    })

    test('onboarding and Money Wrapped', async ({ page, request }) => {
      const account = await newAccount(request)
      await callApi(request, account, 'GET', '/auth/me')
      await seedData(request, account)
      await callApi(request, account, 'PATCH', '/api/onboarding', { status: 'active', step: 'basics' })
      const annual = await callApi(request, account, 'POST', '/api/reports/generate', { period_type: 'annual', date: new Date().toISOString().slice(0, 10) })
      await signIn(page, account)
      await page.goto('/onboarding')
      await audit(page, `${scheme} /onboarding`)
      await page.goto(`/reports/${annual.id}/wrapped`)
      await audit(page, `${scheme} wrapped`)
      for (let i = 0; i < 9; i++) await page.keyboard.press('ArrowRight')
      await audit(page, `${scheme} wrapped share`)
    })
  })
}
