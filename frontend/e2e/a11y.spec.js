// Automated accessibility checks (axe, WCAG 2.0/2.1/2.2 A and AA) on every page, in light and dark.
import AxeBuilder from '@axe-core/playwright'
import { test, expect, newAccount, signIn, seedData, callApi, finishSetup } from './fixtures'

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function audit(page, label) {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)
  // measure colours once fades have finished (a button mid-fade has, briefly, too little contrast)
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), null, { timeout: 5000 }).catch(() => {})
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  const report = violations.map((v) => `${label}: ${v.id} (${v.impact}) ${v.help}\n  ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join('\n  ')}`)
  expect(report, report.join('\n')).toEqual([])
}

for (const scheme of ['light', 'dark']) {
  test.describe(`${scheme} theme`, () => {
    test.use({ colorScheme: scheme })

    test('public pages', async ({ page }) => {
      for (const path of ['/welcome', '/security', '/privacy', '/login', '/verify-email']) {
        await page.goto(path)
        await audit(page, `${scheme} ${path}`)
      }
      await page.goto('/login')                                           // the other sign-in screens
      await page.getByRole('button', { name: 'Forgot password?' }).click()
      await audit(page, `${scheme} /login (reset)`)
      await page.getByRole('button', { name: 'Back to log in' }).click()
      await page.getByRole('button', { name: 'Sign up' }).click()
      await audit(page, `${scheme} /login (sign up)`)
    })

    test('sign in again prompt', async ({ page, request }) => {
      const account = await newAccount(request)
      await callApi(request, account, 'GET', '/auth/me')
      await finishSetup(request, account)
      await signIn(page, account, { reauth: false })
      await page.goto('/settings')
      await page.getByRole('heading', { name: 'Settings' }).waitFor()
      await page.evaluate(() => window.dispatchEvent(new CustomEvent('vaulta:reauth', { detail: { resolve() {}, reject() {} } })))
      await page.getByRole('dialog', { name: 'Sign in again' }).waitFor()
      await audit(page, `${scheme} sign in again`)
    })

    test('workspace pages', async ({ page, request }) => {
      test.setTimeout(150_000)                     // 14 pages, each audited after it settles
      const account = await newAccount(request)
      await callApi(request, account, 'GET', '/auth/me')
      await seedData(request, account)
      const report = await callApi(request, account, 'POST', '/api/reports/generate', { period_type: 'monthly' })
      await signIn(page, account)
      for (const path of ['/', '/transactions', '/budgets', '/goals', '/cash', '/recurring', '/reports', `/reports/${report.id}`,
        '/people', '/rules', '/connect', '/settings', '/review', '/try']) {
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
