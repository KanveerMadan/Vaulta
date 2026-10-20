import { test, expect, checkLayout, openMenu, openChatPanel, reopen, API } from './fixtures'

test('landing → demo → home renders every card', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Kahan gaye paise?' })).toBeVisible()
  for (const h of ['Set it up once. Then just ask.', 'Many finance apps want everything. We want three columns.', "Built so there's little to lose.", 'Fair questions.', "Your money's been talking. Start listening."]) {
    await expect(page.getByRole('heading', { name: h })).toBeAttached()
  }
  await checkLayout(page, testInfo)

  await page.getByRole('button', { name: /look around the demo|try the demo/i }).first().click()
  await expect(page.getByText("You're viewing a demo with sample data.")).toBeVisible()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('outlook')).toContainText('On pace for')
  for (const title of ['Budgets', 'Coming up', 'Needs attention', 'Coverage', 'Recent transactions']) {
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  }
  await expect(page.getByText('Statements', { exact: true })).toBeVisible()
  await page.getByText('How is this worked out?').click()
  await expect(page.getByTestId('safe-explanation')).toContainText('overall budget')
  await checkLayout(page, testInfo)
})

test('demo is read-only', async ({ page, guard }, testInfo) => {
  guard.allow(/status of 403/)
  await page.goto('/welcome')
  await page.getByRole('button', { name: /look around the demo|try the demo/i }).first().click()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 30_000 })
  await page.getByLabel('Quick add a transaction').fill('150 auto cash')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'read-only' })).toBeVisible()
  await checkLayout(page, testInfo)

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await page.getByLabel('Let me ask questions in chat').click()
  await expect(page.getByRole('alert').filter({ hasText: 'read-only' })).toBeVisible()
  await reopen(page)
  await expect(page.getByLabel('Let me ask questions in chat')).toBeChecked()   // nothing changed

  await openMenu(page)
  await page.getByRole('button', { name: 'Exit demo' }).click()
  await expect(page).toHaveURL(/\/welcome$/)
})

test('security page states the claims and how each works', async ({ page }, testInfo) => {
  await page.goto('/welcome')
  await page.getByRole('link', { name: 'How each one works' }).click()
  await expect(page.getByRole('heading', { name: 'Security and privacy' })).toBeVisible()
  const claims = page.getByRole('list', { name: 'Claims' }).getByRole('listitem')
  const count = await claims.count()
  expect(count).toBeGreaterThanOrEqual(10)
  // every claim links to a "how it works" section that exists, says how it's checked, and is reached by the link
  for (let i = 0; i < count; i++) {
    const link = claims.nth(i).getByRole('link', { name: 'How it works' })
    const target = (await link.getAttribute('href')).slice(1)
    const section = page.locator(`section#${target}`)
    await expect(section).toHaveCount(1)
    await expect(section.getByText("How it's checked:")).toBeVisible()
    await expect(section.getByRole('heading', { level: 3 })).toHaveText(await claims.nth(i).getByRole('heading', { level: 2 }).innerText())
  }
  await claims.nth(2).getByRole('link', { name: 'How it works' }).click()
  await expect(page).toHaveURL(/#how-encrypted$/)
  await expect(page.locator('section#how-encrypted')).toBeInViewport()
  await expect(page.getByText('Groq', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('link', { name: 'security@vaulta.test' })).toHaveAttribute('href', 'mailto:security@vaulta.test')
  await checkLayout(page, testInfo)
})

test('landing security tiles open their claim on /security, and the code on GitHub', async ({ page }) => {
  await page.goto('/welcome')
  const tiles = page.getByRole('region', { name: "Built so there's little to lose." }).getByRole('link')
  await expect(tiles).toHaveCount(6)
  const hrefs = await tiles.evaluateAll((as) => as.map((a) => a.getAttribute('href')))
  expect(hrefs.slice(0, 5).every((h) => /^\/security#claim-\d+$/.test(h))).toBe(true)
  expect(hrefs[5]).toBe('https://github.com/KanveerMadan/Vaulta')
  await tiles.first().click()
  await expect(page.locator(hrefs[0].replace('/security', ''))).toBeInViewport()
  await expect(page.locator(`${hrefs[0].replace('/security', '')} h2`)).toHaveText(/encrypted/)
})

test('sign in with Google is the big, filled action, in the hero and at the end; the demo is a quiet link', async ({ page }) => {
  await page.goto('/welcome')
  const primary = page.locator('[data-cta=primary]')
  await expect(primary.first()).toBeInViewport()                                 // above the fold
  const demo = page.locator('[data-cta=demo]')
  await expect(primary).toHaveCount(2)
  await expect(demo).toHaveCount(2)
  for (let i = 0; i < 2; i++) {
    await primary.nth(i).scrollIntoViewIfNeeded()
    await expect(primary.nth(i)).toHaveText(/Sign in with Google/)
    await expect(demo.nth(i)).toHaveText(/demo/)
    const [p, d] = [await primary.nth(i).boundingBox(), await demo.nth(i).boundingBox()]
    expect(p.height).toBeGreaterThanOrEqual(1.25 * d.height)                        // dominant: taller,
    expect(p.width * p.height).toBeGreaterThan(1.3 * d.width * d.height)            // bigger,
    const weight = (l) => l.evaluate((e) => Number(getComputedStyle(e).fontWeight))
    expect(await weight(primary.nth(i))).toBeGreaterThan(await weight(demo.nth(i))) // and bolder
    const bg = await primary.nth(i).evaluate((e) => getComputedStyle(e).backgroundColor)
    expect(bg).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/)                       // filled
  }
  await page.goto('/welcome')                                                      // fresh page, then: keyboard-focusable buttons
  for (const [el, kind] of [[primary.first(), 'primary'], [demo.first(), 'demo']]) {
    await el.focus()   // the page's active element (toBeFocused also needs the window focused, which parallel runs don't give)
    expect(await page.evaluate(() => document.activeElement?.dataset?.cta)).toBe(kind)
  }
})

test('privacy policy and security.txt', async ({ page, request }, testInfo) => {
  await page.goto('/welcome')
  await page.getByRole('navigation', { name: 'Footer' }).getByRole('link', { name: 'Privacy' }).click()
  await expect(page.getByRole('heading', { name: 'Privacy policy' })).toBeVisible()
  await expect(page.getByRole('note')).toContainText('Draft for review')
  for (const h of ['What vaulta.in collects and why', 'What vaulta.in never collects', 'Who else handles it', "How long it's kept", 'Your rights', 'Grievances and questions']) {
    await expect(page.getByRole('heading', { name: h })).toBeVisible()
  }
  await expect(page.getByText('Chat history: 30 days')).toBeVisible()
  await expect(page.getByRole('link', { name: 'privacy@vaulta.test' })).toBeVisible()
  await checkLayout(page, testInfo)
  const txt = await (await request.get('/.well-known/security.txt')).text()
  expect(txt).toMatch(/^Contact: mailto:security@vaulta\.test\nExpires: \d{4}-\d\d-\d\dT/)
})

test('installable: manifest, icons, service worker caches static files only', async ({ page }, testInfo) => {
  test.skip(testInfo.project.use.serviceWorkers === 'block', 'service workers are blocked in this project (playwright.config.js)')
  await page.goto('/welcome')
  const manifest = await (await page.request.get('/manifest.webmanifest')).json()
  expect(manifest.display).toBe('standalone')
  for (const icon of manifest.icons) expect((await page.request.get(icon.src)).ok()).toBeTruthy()
  await page.waitForFunction(async () => (await navigator.serviceWorker.getRegistration())?.active, null, { timeout: 30_000 })
  await page.getByRole('button', { name: /look around the demo|try the demo/i }).first().click()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 30_000 })
  const cached = await page.evaluate(async () => {
    const urls = []
    for (const name of await caches.keys()) for (const req of await (await caches.open(name)).keys()) urls.push(req.url)
    return urls
  })
  expect(cached.length).toBeGreaterThan(5)
  expect(cached.filter((u) => !u.startsWith('http://localhost:4173/') || /\/api\/|\/auth\//.test(u))).toEqual([])
})

test('demo chat: actions show a read-only card', async ({ page }, testInfo) => {
  await page.goto('/welcome')
  await page.getByRole('button', { name: /look around the demo|try the demo/i }).first().click()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 30_000 })
  await openChatPanel(page)
  const chat = page.getByRole('complementary', { name: 'AI Assistant' })
  await chat.getByLabel('Ask the assistant').fill('Set my food budget to 9000')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText('Set a ₹9,000 monthly budget for Food & Dining')).toBeVisible()
  await expect(chat.getByRole('note')).toContainText('The demo is read-only')
  await expect(chat.getByRole('button', { name: 'Confirm' })).toHaveCount(0)
  await checkLayout(page, testInfo)
})

test('reduced motion gets the designed still story', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'reduced-motion', 'reduced-motion project only')
  await page.goto('/welcome')
})

test('public pages have their own title, description and canonical on vaulta.in; the app has none', async ({ page }) => {
  for (const [path, title] of [['/welcome', 'vaulta.in: Private Expense Tracker for India'], ['/security', 'Security and privacy · vaulta.in'], ['/privacy', 'Privacy policy · vaulta.in'], ['/terms', 'Terms of service · vaulta.in']]) {
    await page.goto(path)
    await expect(page).toHaveTitle(title)
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', `https://vaulta.in${path}`)
    await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /.{60,}/)
  }
  await page.goto('/login')
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0)
  for (const file of ['/robots.txt', '/sitemap.xml', '/og.png']) expect((await page.request.get(file)).status(), file).toBe(200)
})

test('a sleeping API: "Waking up vaulta.in…", then the demo opens on its own', async ({ page, guard }) => {
  guard.allow(/Failed to load resource|ERR_FAILED|ERR_CONNECTION_REFUSED|NetworkError|Load failed|network connection was lost|Could not connect|CORS request did not succeed/i)   // a refused connection, as each browser logs it
  await page.goto('/welcome')
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  // the API refuses connections for 5 seconds, as a free instance does while it starts
  const asleepUntil = Date.now() + 5000
  await page.route(`${API}/**`, (route) => (Date.now() < asleepUntil ? route.abort('connectionrefused') : route.continue()))
  await page.getByRole('button', { name: /look around the demo|try the demo/i }).first().click()
  await expect(page.getByText('Waking up vaulta.in…')).toBeVisible()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('Waking up vaulta.in…')).toHaveCount(0)
})

test('reduced motion: the statement story is still, and the animation code never loads', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const scripts = []
  page.on('request', (r) => { if (r.resourceType() === 'script') scripts.push(r.url()) })
  await page.goto('/welcome')
  const why = page.getByRole('region', { name: 'Many finance apps want everything. We want three columns.' })
  await why.scrollIntoViewIfNeeded()
  await expect(why.getByText('What reaches vaulta.in')).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.waitForTimeout(500)
  expect(scripts.filter((u) => /WhyStage|StatementStage/.test(u))).toEqual([])
  // nothing waits to fade in
  const hidden = await page.locator('main [class*="motion-safe:opacity-0"]').evaluateAll((els) => els.filter((e) => getComputedStyle(e).opacity !== '1').length)
  expect(hidden).toBe(0)
})
