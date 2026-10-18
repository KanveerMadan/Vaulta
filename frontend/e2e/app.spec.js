import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, accountExists, checkLayout, openMenu, openChatPanel, isTouch, newAccount, signIn, signedInWithData, callApi, finishSetup, reopen } from './fixtures'

const STATEMENT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../fixtures/statements/hdfc.csv')
const menu = async (page, testInfo, name) => {
  await openMenu(page)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name, exact: true }).click()
}

test('sign up → onboarding, all four steps', async ({ page, request }, testInfo) => {
  const account = await newAccount(request)
  await signIn(page, account)
  await expect(page).toHaveURL(/\/onboarding$/)
  await expect(page.getByText('Tracking coverage 0%')).toBeVisible()
  await checkLayout(page, testInfo)

  // 1 Basics
  await page.getByLabel('Monthly take-home income (optional)').fill('85000')
  await page.getByLabel('Payday').selectOption('1')
  await page.getByRole('button', { name: 'HDFC Bank' }).click()
  await page.getByRole('button', { name: 'SBI Card' }).click()
  await page.getByRole('button', { name: 'PhonePe' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Connect' })).toBeVisible()
  await expect(page.getByText('Tracking coverage 10%')).toBeVisible()

  // 2 Connect: forwarding address, a Gmail filter for just the chosen banks, Send test, Telegram
  await expect(page.getByText(/@in\.vaulta\.test$/)).toBeVisible()
  const filter = await page.locator('code', { hasText: 'from:(' }).innerText()
  expect(filter).toContain('alerts@hdfcbank.net')
  expect(filter).toContain('onlinesbicard@sbicard.com')
  expect(filter).not.toContain('icicibank')
  await page.getByRole('button', { name: 'Send test' }).click()
  await expect(page.getByText('Waiting for your test…')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Link Telegram' })).toBeVisible()
  await checkLayout(page, testInfo)
  await page.getByRole('button', { name: 'Skip for now' }).click()

  // 3 Import history: what to download for those banks, then a real statement through the in-browser importer
  await expect(page.getByRole('heading', { name: 'Import history' })).toBeVisible()
  await expect(page.getByText('HDFC Bank: Account statement: CSV, Excel or the PDF e-statement')).toBeVisible()
  await expect(page.getByText('PhonePe: the PDF statement')).toBeVisible()
  await page.getByRole('button', { name: 'Import a statement' }).click()
  await page.locator('input[type=file]').setInputFiles(STATEMENT)
  await page.getByRole('button', { name: /^Import \d+ transactions$/ }).click()
  await expect(page.getByText('Added', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(page.getByText(/month.* of history imported/)).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()

  // 4 First review: focused cards until done
  await expect(page.getByRole('heading', { name: 'First review' })).toBeVisible()
  await expect(page.getByText(/^\d+ left$|^Nothing to review right now\.$/)).toBeVisible()
  for (let i = 0; i < 60 && await page.getByText(/^\d+ left$/).isVisible(); i++) {
    const left = await page.getByText(/^\d+ left$/).innerText()
    await page.locator('.card button').filter({ hasNotText: 'Skip' }).first().click()
    await expect(page.getByText(left, { exact: true })).toBeHidden()
  }
  await expect(page.getByText(/^(All caught up|Nothing to review right now)\.$/)).toBeVisible()
  await checkLayout(page, testInfo)
  await page.getByRole('button', { name: 'Continue' }).click()

  // Finish
  await expect(page.getByRole('heading', { name: "You're set up." })).toBeVisible()
  await expect(page.getByText('What Vaulta does from here')).toBeVisible()
  await page.getByRole('button', { name: 'Go to home' }).click()
  await expect(page.getByText('Safe to spend today').first()).toBeVisible()
  // the guided tour starts by itself once setup is finished (e2e/tour.spec.js walks through it)
  await expect(page.getByRole('dialog', { name: 'Safe to spend today' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('tour')).toHaveCount(0)
  await reopen(page)
  await expect(page).not.toHaveURL(/onboarding/)                // done: not sent back
})

test('statement import: file → preview → confirm → transactions appear', async ({ page, request }, testInfo) => {
  const account = await newAccount(request)
  await callApi(request, account, 'GET', '/auth/me')
  await finishSetup(request, account)
  await signIn(page, account)
  await menu(page, testInfo, 'Connect')
  await page.getByRole('button', { name: /upload/i }).first().click()
  await page.locator('input[type=file]').setInputFiles(STATEMENT)
  await expect(page.getByText('processed on your device and never uploaded').first()).toBeVisible()
  await expect(page.getByText(/transactions from HDFC Bank/)).toBeVisible()
  // the fixture has rows the parser can't read (a bad date, an empty narration): its running balances say so
  await expect(page.getByTestId('balance-check')).toContainText("Balances don't add up")
  await checkLayout(page, testInfo)
  await page.getByRole('button', { name: /^Import \d+ transactions$/ }).click()
  await expect(page.getByText('Added', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await menu(page, testInfo, 'Home')
  const recent = page.locator('section', { hasText: 'Recent transactions' })
  await expect(recent.getByText('Swiggy').first()).toBeVisible()
  await expect(recent.getByText('ATM withdrawal').first()).toBeVisible()
  await checkLayout(page, testInfo)
})

test('quick add', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await page.getByLabel('Quick add a transaction').fill('150 auto cash')
  await expect(page.getByText('Transport', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.locator('section', { hasText: 'Recent transactions' }).getByText('Auto').first()).toBeVisible()
  await checkLayout(page, testInfo)
})

test('inline recategorize → rule toast → undo', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  const recent = page.locator('section', { hasText: 'Recent transactions' })
  await expect(recent.getByText('Netflix')).toBeVisible()            // the list has loaded
  const entertainment = recent.getByTitle('Change category').filter({ hasText: 'Entertainment' })
  const before = await entertainment.count()
  for (let i = 1; i <= 2; i++) {        // a rule is learned from two consistent corrections
    await recent.getByTitle('Change category').filter({ hasText: 'Food & Dining' }).first().click()
    await recent.getByLabel('Category').selectOption('Entertainment')
    if (i === 1) await expect(entertainment).toHaveCount(before + 1)   // saved and the list refreshed
  }
  const toast = page.getByRole('status').filter({ hasText: 'Swiggy' })
  await expect(toast).toContainText('Entertainment')
  await expect(entertainment).toHaveCount(before + 3)                 // the learned rule moved the third Swiggy too
  await checkLayout(page, testInfo)
  await toast.getByRole('button', { name: 'Undo' }).click()
  await expect(toast).toBeHidden()
})

test('review queue card answer', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  const attention = page.locator('section', { hasText: 'Needs attention' })
  const badge = attention.locator('span.num').first()
  const before = Number(await badge.innerText())
  const question = await attention.locator('p.font-medium').first().innerText()
  await attention.locator('button').filter({ hasNotText: 'Skip' }).first().click()
  await expect(attention.getByText(question, { exact: true })).toBeHidden()
  if (before > 1) await expect(badge).toHaveText(String(before - 1))
  await checkLayout(page, testInfo)
})

test('set a budget', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await menu(page, testInfo, 'Budgets')
  await page.getByLabel('Transport monthly limit').fill('3000')
  const saved = page.waitForResponse((r) => r.url().includes('/api/budgets') && ['POST', 'PATCH'].includes(r.request().method()))
  await page.getByLabel('Transport monthly limit').press('Enter')
  expect((await saved).ok()).toBe(true)                 // saved before leaving the page
  await checkLayout(page, testInfo)
  await menu(page, testInfo, 'Home')
  await expect(page.locator('section', { hasText: 'Budgets' }).getByLabel('Transport budget')).toBeVisible()
})

test('create a goal and put money towards it', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await menu(page, testInfo, 'Goals')
  await page.getByLabel('Name').fill('Laptop')
  await page.getByLabel('Target amount (₹)').fill('60000')
  const due = new Date(); due.setMonth(due.getMonth() + 6)
  await page.getByLabel('By').fill(due.toISOString().slice(0, 10))
  await page.getByRole('button', { name: 'Create goal' }).click()
  const goal = page.getByRole('region', { name: 'Laptop' })
  await expect(goal.getByText('Not started')).toBeVisible()
  await goal.getByLabel('Amount to put towards Laptop').fill('12000')
  await goal.getByRole('button', { name: 'Add' }).click()
  await expect(goal.getByText('₹12,000').first()).toBeVisible()
  await expect(goal.getByText('Estimate:')).toBeVisible()
  await checkLayout(page, testInfo)
})

const openChat = async (page) => {
  await openChatPanel(page)
  return page.getByRole('complementary', { name: 'AI Assistant' })
}

test('chat: question answered from tools (mocked LLM)', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await page.getByLabel('Ask a question').fill('How much did I spend this month?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  const chat = page.getByRole('complementary', { name: 'AI Assistant' })
  await expect(chat.getByText("Here's your spending this month, from your own transactions.").first()).toBeVisible()
  await expect(chat.getByText('Spending', { exact: true })).toBeVisible()
  await checkLayout(page, testInfo)
})

test('chat: action needs confirmation', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  const chat = await openChat(page, testInfo)
  await chat.getByLabel('Ask the assistant').fill('Set my food budget to 7000')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText('Set a ₹7,000 monthly budget for Food & Dining')).toBeVisible()
  await checkLayout(page, testInfo)
  await chat.getByRole('button', { name: 'Confirm' }).click()
  await expect(chat.getByText('Budget set: ₹7,000 a month for Food & Dining.')).toBeVisible()
})

test('alerts bell', async ({ page, request }, testInfo) => {
  const account = await signedInWithData(page, request)
  // spending past 80% of the Food budget raises an alert
  await callApi(request, account, 'POST', '/api/import/batch', { rows: [{ date: new Date().toISOString().slice(0, 10),
    description_raw: 'SWIGGY BANGALORE', amount: '5500.00', direction: 'debit', reference: null, source_type: 'bank_csv',
    source_label: 'HDFC Bank', type: 'transaction' }] })
  await reopen(page)
  const bell = page.getByRole('button', { name: /^Alerts, \d+ unread$/ })
  await expect(bell).toBeVisible()
  await bell.click()
  await expect(page.getByRole('dialog', { name: 'Alerts' }).getByText(/Food & Dining budget (80% used|used up)/)).toBeVisible()
  await checkLayout(page, testInfo)
  await expect(page.getByTestId('unread-count')).toBeHidden()
})

test('cash page', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await menu(page, testInfo, 'Cash')
  await expect(page.getByText('ATM withdrawal').first()).toBeVisible()
  await page.getByPlaceholder('₹ in hand now').fill('1500')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText(/₹500/).first()).toBeVisible()
  await checkLayout(page, testInfo)
})

test('people merge', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await menu(page, testInfo, 'People')
  const merge = page.getByLabel(/^Merge Priya S into another person$/)
  await expect(merge).toBeVisible()
  page.once('dialog', (d) => d.accept())
  await merge.selectOption(await merge.locator('option', { hasText: 'Priya Sharma' }).getAttribute('value'))
  await expect(page.getByLabel(/^Merge Priya S into another person$/)).toBeHidden()
  await checkLayout(page, testInfo)
})

test('reports page', async ({ page, request }, testInfo) => {
  const account = await signedInWithData(page, request)
  const last = new Date(); last.setDate(0)
  await callApi(request, account, 'POST', '/api/reports/generate', { period_type: 'monthly', date: last.toISOString().slice(0, 10) })
  await menu(page, testInfo, 'Reports')
  await page.getByRole('link', { name: /^[A-Z][a-z]+ \d{4} ₹/ }).first().click()
  await expect(page.getByRole('heading', { name: 'Summary' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Top categories' })).toBeVisible()
  await checkLayout(page, testInfo)
})

test('settings toggles and Telegram link code', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await menu(page, testInfo, 'Settings')
  const weekly = page.getByRole('checkbox', { name: 'Build' }).first()
  await expect(weekly).toBeChecked()
  await weekly.click()
  await expect(weekly).not.toBeChecked()
  await reopen(page)                                     // the assertion below waits for the data
  await expect(page.getByRole('checkbox', { name: 'Build' }).first()).not.toBeChecked()
  const priceTelegram = page.locator('li', { hasText: 'Subscription price change' }).getByRole('checkbox', { name: 'Telegram' })
  await priceTelegram.click()
  await expect(priceTelegram).not.toBeChecked()
  await page.getByLabel('Quiet hours start').selectOption('23')
  await expect(page.getByLabel('Quiet hours start')).toHaveValue('23')

  await page.getByRole('button', { name: 'Link Telegram' }).click()
  await expect(page.getByText(/^Or send \/start [A-Z0-9]{8} to the bot/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open @VaultaTestBot and link' })).toHaveAttribute('href', /t\.me\/VaultaTestBot\?start=[A-Z0-9]{8}/)
  await checkLayout(page, testInfo)
})

test('transactions: search, j/k, e to recategorize (optimistic)', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await menu(page, testInfo, 'Transactions')
  await expect(page.getByRole('heading', { name: 'Transactions' })).toBeVisible()
  const list = page.getByRole('list', { name: 'Transactions' })
  await expect(list.getByRole('listitem').first()).toBeVisible()
  await checkLayout(page, testInfo)
  if (!isTouch(testInfo)) {
    await page.keyboard.press('j')
    await page.keyboard.press('j')
    await expect(list.locator('[data-selected]')).toHaveCount(1)
    await page.keyboard.press('e')
    await list.getByLabel('Category').selectOption('Travel')
    await expect(list.locator('[data-selected]').getByTitle('Change category')).toHaveText('Travel')
    await page.keyboard.press('/')
    await expect(page.getByPlaceholder('Search merchants…')).toBeFocused()
  }
  await page.getByPlaceholder('Search merchants…').fill('netflix')
  await expect(page).toHaveURL(/q=netflix/)
  await expect(list.getByRole('listitem')).toHaveCount(3)
  await expect(list.getByText('Netflix').first()).toBeVisible()
})

test('subcategory, tags, tag filter and why this category', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  await menu(page, testInfo, 'Transactions')
  const list = page.getByRole('list', { name: 'Transactions' })
  await page.getByPlaceholder('Search merchants…').fill('netflix')
  await expect(list.getByRole('listitem')).toHaveCount(3)
  const row = list.getByRole('listitem').first()
  await row.getByTitle('Change category').click()
  const saved = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/api/transactions/'))
  await row.getByLabel('Category').selectOption('entertainment.music_streaming')
  await expect(row.getByTitle('Change category')).toHaveText('Entertainment › Music & audio')
  await saved                                                            // "why" is read from the saved row
  const more = async () => { if (page.viewportSize().width < 640) await row.getByRole('button', { name: /^More for / }).click() }
  await more()
  await row.getByRole('button', { name: /^Why .* is filed here$/ }).click()
  await expect(row.getByRole('status')).toContainText('You chose this category.')
  await more()
  await row.getByRole('button', { name: /^Tags for / }).click()
  await row.getByLabel('Tags, separated by commas').fill('Goa trip, Reimbursable')
  await row.getByLabel('Tags, separated by commas').press('Enter')
  await expect(row.getByRole('button', { name: '#Goa trip' })).toBeVisible()
  await checkLayout(page, testInfo)
  await page.getByPlaceholder('Search merchants…').fill('')
  await expect(page).not.toHaveURL(/q=netflix/)
  await list.getByRole('button', { name: '#Goa trip' }).first().click()
  await expect(page).toHaveURL(/tag=Goa/)
  await expect(list.getByRole('listitem')).toHaveCount(1)
  await expect(page.getByLabel('Tag', { exact: true })).toHaveValue('Goa trip')
})

test('command palette: jump, search and quick add', async ({ page, request }, testInfo) => {
  await signedInWithData(page, request)
  if (!isTouch(testInfo)) await page.keyboard.press('Control+k')
  else await page.getByRole('button', { name: 'Search and commands' }).click()
  const palette = page.getByRole('dialog', { name: 'Search and commands' })
  await expect(palette).toBeVisible()
  await palette.getByRole('combobox').fill('budg')
  await palette.getByRole('combobox').press('Enter')
  await expect(page).toHaveURL(/\/budgets$/)
  if (!isTouch(testInfo)) await page.keyboard.press('Control+k')
  else await page.getByRole('button', { name: 'Search and commands' }).click()
  await palette.getByRole('combobox').fill('320 autorickshaw cash')
  await expect(palette.getByRole('option').first()).toContainText('Add ₹320')
  await checkLayout(page, testInfo)
  await palette.getByRole('combobox').press('Enter')
  await expect(page.getByRole('status').filter({ hasText: 'Added' })).toBeVisible()
})

test('the workspace never loads the animation library', async ({ page, request }) => {
  const { readdirSync, readFileSync } = await import('node:fs')
  const dir = new URL('../dist-e2e/assets/', import.meta.url)
  const motionChunks = readdirSync(dir).filter((f) => f.endsWith('.js') && readFileSync(new URL(f, dir), 'utf8').includes('MotionValue'))
  expect(motionChunks.length).toBeGreaterThan(0)
  const scripts = []
  page.on('request', (r) => { if (r.resourceType() === 'script') scripts.push(r.url()) })
  await signedInWithData(page, request)
  for (const path of ['/transactions', '/budgets', '/goals', '/cash', '/reports', '/settings']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
  }
  expect(scripts.filter((u) => motionChunks.some((c) => u.endsWith(c)))).toEqual([])
})

test('Money Wrapped: story, privacy toggles and the share image', async ({ page, request }, testInfo) => {
  const account = await signedInWithData(page, request)
  const annual = await callApi(request, account, 'POST', '/api/reports/generate', { period_type: 'annual', date: new Date().toISOString().slice(0, 10) })
  await page.goto(`/reports/${annual.id}/wrapped`)
  await expect(page.getByText('Money Wrapped').first()).toBeVisible()
  const next = page.getByRole('button', { name: 'Next scene' })
  for (let i = 0; i < 12 && await next.isEnabled(); i++) await next.click()
  await expect(page.getByText('Your card to share')).toBeVisible()
  const card = page.getByRole('figure', { name: 'Share card preview' })
  await expect(card).toContainText('One place,')                      // merchant names off by default
  await page.getByLabel('Show merchant names').check()
  await expect(card).not.toContainText('One place,')
  await page.getByLabel('Show amounts').uncheck()
  await expect(card).toContainText('₹ hidden')
  await checkLayout(page, testInfo)
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Save image' }).click()])
  const bytes = await (await import('node:fs')).promises.readFile(await download.path())
  expect(download.suggestedFilename()).toMatch(/^vaulta-wrapped-\d{4}\.png$/)
  expect(bytes.subarray(1, 4).toString()).toBe('PNG')
  expect(bytes.length).toBeGreaterThan(20_000)
  await page.keyboard.press('Escape')
  // test: a UUID from the API
  // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
  await expect(page).toHaveURL(new RegExp(`/reports/${annual.id}$`))
})

test('your data: export a zip, see it in Activity, then delete everything', async ({ page, request }, testInfo) => {
  const account = await signedInWithData(page, request)
  await menu(page, testInfo, 'Settings')
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export my data' }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/^vaulta-export-\d{4}-\d{2}-\d{2}\.zip$/)
  const zip = await download.createReadStream().then(async (s) => { const c = []; for await (const x of s) c.push(x); return Buffer.concat(c) })
  expect(zip.subarray(0, 2).toString()).toBe('PK')                              // a real zip
  expect(zip.includes(Buffer.from('vaulta-export/data.json'))).toBe(true)
  const activity = page.getByRole('list', { name: 'Account activity' })
  await expect(activity.getByText('Exported your data')).toBeVisible()
  await checkLayout(page, testInfo)

  await page.getByLabel('Type DELETE to confirm').fill('DELETE')
  await page.getByRole('button', { name: 'Delete my account and data' }).click()
  await page.waitForURL('**/welcome')
  expect(await accountExists(request, account.email)).toBe(false)             // the login itself is gone
  const login = await request.post('http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=e2e-fake-key',
    { data: { email: account.email, password: account.password, returnSecureToken: true } })
  expect(login.ok()).toBe(false)
})

test('the app is served with the strict Content-Security-Policy', async ({ page }) => {
  const res = await page.goto('/welcome')
  const csp = res.headers()['content-security-policy']
  expect(csp).toContain("frame-ancestors 'none'")
  expect(csp).toContain("object-src 'none'")
  const script = csp.split(';').find((d) => d.trim().startsWith('script-src'))
  expect(script).not.toContain("'unsafe-inline'")
  expect(script).not.toContain("'unsafe-eval'")
  expect(res.headers()['x-content-type-options']).toBe('nosniff')
  expect(res.headers()['x-frame-options']).toBe('DENY')
})
