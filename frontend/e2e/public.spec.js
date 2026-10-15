import { test, expect, checkLayout } from './fixtures'

test('landing → demo → home renders every card', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Vaulta tracks every rupee you spend, automatically. Set it up once, then just ask.' })).toBeVisible()
  for (const point of ['Automatic tracking', 'Reports that come to you', 'Ask anything']) await expect(page.getByRole('heading', { name: point })).toBeVisible()
  await expect(page.getByText('Raw alert emails are never stored.')).toBeVisible()
  await checkLayout(page, testInfo)

  await page.getByRole('button', { name: 'Try the demo' }).click()
  await expect(page.getByText("You're viewing a demo with sample data.")).toBeVisible()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('outlook')).toContainText('On pace for')
  for (const title of ['Budgets', 'Upcoming · 14 days', 'Needs attention', 'Coverage', 'Recent transactions']) {
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  }
  await expect(page.getByText('Statements ·').first()).toBeVisible()
  await page.getByText('How is this worked out?').click()
  await expect(page.getByTestId('safe-explanation')).toContainText('overall budget')
  await checkLayout(page, testInfo)
})

test('demo is read-only', async ({ page, guard }, testInfo) => {
  guard.allow(/status of 403/)
  await page.goto('/welcome')
  await page.getByRole('button', { name: 'Try the demo' }).click()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 30_000 })
  await page.getByLabel('Quick add a transaction').fill('150 auto cash')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'read-only' })).toBeVisible()
  await checkLayout(page, testInfo)

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await page.getByLabel('Let me ask questions in chat').click()
  await expect(page.getByRole('alert').filter({ hasText: 'read-only' })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Let me ask questions in chat')).toBeChecked()   // nothing changed

  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: 'Menu' }).click()
  await page.getByRole('button', { name: 'Exit demo' }).click()
  await expect(page).toHaveURL(/\/welcome$/)
})

test('security page states the claims and how each works', async ({ page }, testInfo) => {
  await page.goto('/welcome')
  await page.getByRole('link', { name: 'How each of these works →' }).click()
  await expect(page.getByRole('heading', { name: 'Security and privacy' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2 })).toHaveCount(5)
  await expect(page.getByText('How it works:')).toHaveCount(5)
  await checkLayout(page, testInfo)
})

test('installable: manifest, icons, service worker caches static files only', async ({ page }) => {
  await page.goto('/welcome')
  const manifest = await (await page.request.get('/manifest.webmanifest')).json()
  expect(manifest.display).toBe('standalone')
  for (const icon of manifest.icons) expect((await page.request.get(icon.src)).ok()).toBeTruthy()
  await page.waitForFunction(async () => (await navigator.serviceWorker.getRegistration())?.active, null, { timeout: 30_000 })
  await page.getByRole('button', { name: 'Try the demo' }).click()
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
  await page.getByRole('button', { name: 'Try the demo' }).click()
  await expect(page.getByText('Safe to spend today')).toBeVisible({ timeout: 30_000 })
  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: 'Ask the assistant' }).click()
  const chat = page.getByRole('complementary', { name: 'AI Assistant' })
  await chat.getByLabel('Ask the assistant').fill('Set my food budget to 9000')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText('Set a ₹9,000 monthly budget for Food & Dining')).toBeVisible()
  await expect(chat.getByRole('note')).toContainText('The demo is read-only')
  await expect(chat.getByRole('button', { name: 'Confirm' })).toHaveCount(0)
  await checkLayout(page, testInfo)
})
