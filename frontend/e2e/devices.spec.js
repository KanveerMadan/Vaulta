// Every device profile (playwright.config.js DEVICES): the key screens laid out without sideways scrolling or small
// tap targets, screenshots per device, plus the things that go wrong on phones and iOS in particular: the landing page
// without WebGL, sticky headers, a focused field under the keyboard, and the installed (standalone) app.
// Baselines: e2e/devices.spec.js-snapshots/<screen>-<device>-<os>.png (update with --update-snapshots).
import { fileURLToPath } from 'node:url'
import { test, expect, checkLayout, isTouch, newAccount, callApi, seedData, signIn, openMenu, openChatPanel, finishSetup, centre } from './fixtures'

const STATEMENT = fileURLToPath(new URL('../../fixtures/statements/hdfc.csv', import.meta.url))
const SNAP = { maxDiffPixelRatio: 0.02, animations: 'disabled', fullPage: false }

// Playwright's screenshots inject a <style> (pausing animations, hiding the caret); WebKit applies the page's strict
// CSP to it and logs a refusal. That one message is the tool's, not the app's: the full-suite WebKit projects, which
// take no screenshots, still fail on any CSP refusal.
test.beforeEach(({ guard }) => guard.allow(/Refused to apply a stylesheet because its hash, its nonce, or 'unsafe-inline'/))
const dynamic = (page) => [page.locator('.num'), page.locator('[data-value]'), page.locator('time'), page.getByTestId('outlook')]

async function settle(page) {
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), null, { timeout: 5000 }).catch(() => {})
  await page.waitForTimeout(200)
  // The figures and dates here depend on the day and are masked, but a mask takes the size of what it covers: a longer
  // weekday or a different forecast moved the masks and failed the comparison the next day. Pin those sizes (set
  // through the CSSOM, which the page's strict CSP allows, unlike an injected stylesheet).
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('main time')) Object.assign(el.style, { display: 'inline-block', width: '11em', overflow: 'hidden', whiteSpace: 'nowrap', verticalAlign: 'bottom' })
    for (const el of document.querySelectorAll('main [data-testid="outlook"]')) Object.assign(el.style, { height: '210px', overflow: 'hidden' })
  })
}

/** No sideways scrolling on any device (checkLayout adds tap-target sizes on touch devices). */
async function fits(page, testInfo) {
  const width = page.viewportSize().width
  const wide = await page.evaluate(() => Math.max(document.scrollingElement.scrollWidth, window.innerWidth))
  expect(wide, `page is ${wide}px wide on a ${width}px screen`).toBeLessThanOrEqual(width + 1)
  await checkLayout(page, testInfo)
}

async function account(request) {
  const a = await newAccount(request)
  await callApi(request, a, 'GET', '/auth/me')
  await seedData(request, a)
  return a
}

test('landing, also without WebGL', async ({ page }, testInfo) => {
  await page.goto('/welcome'); await settle(page)
  await fits(page, testInfo)
  await expect(page).toHaveScreenshot('landing.png', SNAP)

  // A browser without WebGL (old phones, some locked-down machines): the landing page doesn't rely on it
  const ctx = await page.context().browser().newContext({ ...testInfo.project.use, baseURL: testInfo.project.use.baseURL })
  const bare = await ctx.newPage()
  await bare.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      return /webgl/i.test(type) ? null : original.call(this, type, ...rest)
    }
  })
  const errors = []
  bare.on('pageerror', (e) => errors.push(e.message))
  await bare.goto(new URL('/welcome', page.url()).toString())
  await expect(bare.getByRole('heading', { level: 1 })).toBeVisible()
  await bare.evaluate(() => window.scrollBy(0, 3000))
  await expect(bare.getByRole('heading', { name: 'What happens to your data' })).toBeVisible()
  expect(errors).toEqual([])
  await ctx.close()
})

test('home, transactions, chat, sticky header, keyboard', async ({ page, request }, testInfo) => {
  const a = await account(request)
  await signIn(page, a)
  await expect(page.getByText('Safe to spend today')).toBeVisible()
  await settle(page)
  await fits(page, testInfo)
  await expect(page).toHaveScreenshot('home.png', { ...SNAP, mask: [...dynamic(page), page.locator('section[aria-label="Recent transactions"]'),
    page.locator('section[aria-label="Coverage"]'), page.locator('section[aria-label="Needs attention"]')] })

  // the phone header stays at the top while the page scrolls
  const header = page.locator('header.sticky').first()
  if (await header.isVisible()) {
    await page.evaluate(() => window.scrollBy(0, 1500))          // (mobile WebKit has no mouse wheel)
    await page.waitForTimeout(300)
    // pinned to the top of the layout viewport; WebKit may also shift the visual viewport (iOS-style) at the end
    expect(await header.evaluate((h) => Math.round(h.getBoundingClientRect().top + (window.visualViewport?.offsetTop || 0)))).toBe(0)
    await page.evaluate(() => window.scrollTo(0, 0))
  }

  // a focused field ends up in view (on touch screens it's scrolled to the middle once the keyboard is up)
  const quick = page.getByLabel('Quick add a transaction')
  await quick.focus()
  await page.waitForTimeout(500)
  await expect(quick).toBeInViewport()

  await page.goto('/transactions'); await settle(page)
  await expect(page.getByRole('list', { name: 'Transactions' }).getByRole('listitem').first()).toBeVisible()
  await fits(page, testInfo)
  await expect(page).toHaveScreenshot('transactions.png', { ...SNAP, mask: [...dynamic(page), page.getByRole('list', { name: 'Transactions' })] })

  await page.goto('/'); await settle(page)
  await openChatPanel(page)
  const chat = page.getByRole('complementary', { name: 'AI Assistant' })
  const input = chat.getByLabel('Ask the assistant')
  await input.fill('How much did I spend on food this month?')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByLabel('Vaulta is answering')).toHaveCount(0, { timeout: 20_000 })   // the answer is in
  await settle(page)
  await expect(input).toBeInViewport()                             // the chat box isn't pushed off-screen
  await fits(page, testInfo)
  await expect(page).toHaveScreenshot('chat.png', { ...SNAP, mask: [...dynamic(page), chat.locator('[aria-live="polite"]')] })
})

test('import preview', async ({ page, request }, testInfo) => {
  const a = await newAccount(request)
  await callApi(request, a, 'GET', '/auth/me')
  await finishSetup(request, a)
  await signIn(page, a)
  await openMenu(page)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Connect', exact: true }).click()
  await page.getByRole('button', { name: /upload/i }).first().click()
  await page.locator('input[type=file]').setInputFiles(STATEMENT)
  await expect(page.getByText(/transactions from HDFC Bank/)).toBeVisible()
  await expect(page.getByText(/Category guesses are worked out on this device/)).toBeVisible()   // the on-device model has loaded
  await settle(page)
  await fits(page, testInfo)
  await expect(page).toHaveScreenshot('import-preview.png', { ...SNAP, mask: dynamic(page) })
})

test('Money Wrapped', async ({ page, request }, testInfo) => {
  const a = await account(request)
  const annual = await callApi(request, a, 'POST', '/api/reports/generate', { period_type: 'annual', date: new Date().toISOString().slice(0, 10) })
  await signIn(page, a)
  await page.goto(`/reports/${annual.id}/wrapped`)
  await expect(page.getByText('Money Wrapped').first()).toBeVisible()
  await settle(page)
  await fits(page, testInfo)
  await expect(page).toHaveScreenshot('wrapped.png', { ...SNAP, mask: dynamic(page) })
})

test('guided tour and getting-started checklist', async ({ page, request }, testInfo) => {
  const a = await account(request)
  await callApi(request, a, 'PATCH', '/api/tour', { status: 'active', step: 1 })     // a step with no figures in it
  await signIn(page, a)
  const card = page.getByTestId('tour').getByRole('dialog')
  await expect(card).toHaveAccessibleName('Add anything in one line')
  await settle(page)
  await centre(page, 'quick-add')     // settle() resizes masked blocks: put the step back where the tour put it
  // the card (or, on phones, the bottom sheet) is fully on screen and its buttons are big enough to tap
  const box = await card.boundingBox()
  const [w, h] = await page.evaluate(() => [document.documentElement.clientWidth, document.documentElement.clientHeight])
  expect(box.x >= 0 && box.y >= 0 && box.x + box.width <= w + 1 && box.y + box.height <= h + 1, JSON.stringify({ box, w, h })).toBe(true)
  await checkLayout(page, testInfo)
  // the page's own figures change daily: mask those inside the page, never over the tour on top of it
  const inPage = [page.locator('main .num'), page.locator('main [data-value]'), page.locator('main time'), page.locator('main [data-testid="outlook"]')]
  await expect(page).toHaveScreenshot('tour.png', { ...SNAP, mask: inPage })
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('tour')).toHaveCount(0)
  const checklist = page.getByTestId('getting-started')
  await checklist.scrollIntoViewIfNeeded(); await settle(page)
  await fits(page, testInfo)
  await expect(checklist).toHaveScreenshot('checklist.png', { ...SNAP, mask: [checklist.locator('.num')] })
})

test('installed app (standalone display mode)', async ({ page, request }, testInfo) => {
  // No engine here can emulate display-mode: standalone, so check what the installed app relies on: the shipped CSS
  // pads the sticky header for the status bar in standalone mode, and the header carries that class
  test.skip(!isTouch(testInfo), 'phones and tablets')
  const a = await account(request)
  await signIn(page, a)
  await expect(page.getByText('Safe to spend today')).toBeVisible()
  const rule = await page.evaluate(() => [...document.styleSheets].flatMap((sheet) => [...sheet.cssRules])
    .some((r) => r.conditionText?.includes('display-mode: standalone') && r.cssText.includes('standalone-safe-top') && r.cssText.includes('safe-area-inset-top')))
  expect(rule).toBe(true)
  const header = page.locator('header.sticky').first()
  if (await header.isVisible()) await expect(header).toHaveClass(/standalone-safe-top/)
  const manifest = await (await page.request.get('/manifest.webmanifest')).json()
  expect(manifest.display).toBe('standalone')
  await fits(page, testInfo)
})
