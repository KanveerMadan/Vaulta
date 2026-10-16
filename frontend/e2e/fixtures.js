// Shared setup for the browser tests: guards that fail a test on console errors, file uploads or
// off-origin requests; users created in the Firebase Auth emulator; data seeded through the real API.
import { test as base, expect } from '@playwright/test'

export const API = 'http://127.0.0.1:8001'
const EMULATOR = 'http://127.0.0.1:9099'
const ALLOWED_ORIGINS = new Set(['http://localhost:4173', API, EMULATOR])

export const test = base.extend({
  // Every page in every test: no console errors, no uploads, nothing sent anywhere but the app, the API and Firebase auth
  guard: [async ({ page }, use) => {
    const problems = []
    const allowed = []   // console messages a test expects (e.g. the 403 a demo write produces)
    const origins = new Set(ALLOWED_ORIGINS)   // + origins a test opts into (guard.allowOrigin), each documented there
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !allowed.some((re) => re.test(msg.text()))) problems.push(`console: ${msg.text()}`)
    })
    page.on('pageerror', (err) => problems.push(`page error: ${err.message}`))
    page.on('request', (req) => {
      const url = new URL(req.url())
      if (['data:', 'blob:'].includes(url.protocol)) return
      if (!origins.has(url.origin)) problems.push(`off-origin request: ${req.method()} ${req.url()}`)
      const type = req.headers()['content-type'] || ''
      const body = req.postDataBuffer()
      if (/multipart\/form-data|application\/octet-stream|application\/pdf|^image\/|text\/csv/.test(type)) problems.push(`file upload: ${req.url()} (${type})`)
      if (body && (body.subarray(0, 4).toString() === '%PDF' || body.includes('Closing Balance'))) problems.push(`file content sent: ${req.url()}`)
    })
    await use({ allow: (re) => allowed.push(re), allowOrigin: (origin) => origins.add(origin) })
    expect(problems, problems.join('\n')).toEqual([])
  }, { auto: true }],
})
export { expect }

let counter = 0

const IDT = `${EMULATOR}/identitytoolkit.googleapis.com/v1`
const PROJECT = 'demo-vaulta'
const OWNER = { Authorization: 'Bearer owner' }        // the emulator's admin credential

/** A fresh ID token for an emulator account (after its claims changed). */
export async function signInToken(request, email, password) {
  const res = await request.post(`${IDT}/accounts:signInWithPassword?key=e2e-fake-key`, { data: { email, password, returnSecureToken: true } })
  expect(res.ok()).toBeTruthy()
  return (await res.json()).idToken
}

/**
 * A new Firebase (emulator) account; returns {email, password, token, uid}. Its email is confirmed unless
 * `verified: false` (Vaulta refuses to create data for unconfirmed email/password accounts).
 */
export async function newAccount(request, { verified = true } = {}) {
  const email = `e2e-${Date.now()}-${process.pid}-${counter++}@vaulta.test`
  const password = 'e2e-password-123'
  const res = await request.post(`${IDT}/accounts:signUp?key=e2e-fake-key`, { data: { email, password, returnSecureToken: true } })
  expect(res.ok()).toBeTruthy()
  const { idToken, localId } = await res.json()
  if (!verified) return { email, password, token: idToken, uid: localId }
  const upd = await request.post(`${IDT}/projects/${PROJECT}/accounts:update`, { headers: OWNER, data: { localId, emailVerified: true } })
  expect(upd.ok()).toBeTruthy()
  return { email, password, token: await signInToken(request, email, password), uid: localId }
}

/** The emails the emulator would have sent (verification, password reset), newest last. */
export async function emulatorEmails(request, email) {
  const res = await request.get(`${EMULATOR}/emulator/v1/projects/${PROJECT}/oobCodes`)
  return (await res.json()).oobCodes.filter((c) => c.email === email)
}

/** Does the emulator still have an account for this email? */
export async function accountExists(request, email) {
  const res = await request.post(`${IDT}/projects/${PROJECT}/accounts:lookup`, { headers: OWNER, data: { email: [email] } })
  return ((await res.json()).users || []).length > 0
}

export async function callApi(request, account, method, path, data) {
  const res = await request.fetch(`${API}${path}`, { method, data, headers: { Authorization: `Bearer ${account.token}` } })
  expect(res.ok(), `${method} ${path}: ${res.status()} ${await res.text()}`).toBeTruthy()
  return res.status() === 204 ? null : res.json()
}

const iso = (d) => d.toISOString().slice(0, 10)
const daysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return d }

/** Three months of ordinary data through /api/import/batch, plus budgets, as the browser would send it. */
export async function seedData(request, account) {
  const rows = []
  const r = (d, desc, amount, extra = {}) => rows.push({ date: iso(d), description_raw: desc, amount, direction: 'debit', reference: null,
    source_type: 'bank_csv', source_label: 'HDFC Bank', type: 'transaction', ...extra })
  for (const back of [60, 30, 0]) {
    r(daysAgo(back + 2), 'NEFT CR-ACME CORP PAYROLL', '90000.00', { direction: 'credit' })
    r(daysAgo(back + 1), 'UPI-RAVI KUMAR-r***@okaxis-XXXX-Rent', '20000.00')
    r(daysAgo(back + 3), 'NETFLIX COM', '649.00')
    for (const [k, amt] of [[4, '450.00'], [9, '380.00'], [15, '520.00']]) r(daysAgo(back + k), 'SWIGGY BANGALORE', amt)
    r(daysAgo(back + 5), 'UPI-UBER INDIA-uber@axisbank-XXXX', '240.00')
  }
  r(daysAgo(20), 'UPI-PRIYA SHARMA-p***@okaxis-XXXX-Dinner', '800.00')
  r(daysAgo(18), 'UPI-PRIYA S-p***@ybl-XXXX-Movie', '400.00')
  r(daysAgo(9), 'ATW-512345XXXXXX6789-S1ANMU12-BANGALORE', '2000.00')
  await callApi(request, account, 'POST', '/api/import/batch', { rows })
  await callApi(request, account, 'POST', '/api/budgets', { category: 'Food & Dining', monthly_limit: '6000' })
  await callApi(request, account, 'PATCH', '/api/onboarding', { status: 'done', step: 'finish' })
}

/**
 * Sign in through the real login form (Firebase emulator). Unless `reauth: false`, a "Sign in again" prompt
 * (sensitive actions after RECENT_LOGIN_SECONDS, 30 s in browser tests) is answered with the password whenever
 * it appears; e2e/auth.spec.js tests the prompt itself.
 */
export async function signIn(page, account, { reauth = true } = {}) {
  if (reauth) {
    const prompt = page.getByRole('dialog', { name: 'Sign in again' })
    await page.addLocatorHandler(prompt, async () => {
      await prompt.getByLabel(/^Password for/).fill(account.password)
      await prompt.getByRole('button', { name: 'Confirm' }).click()
      await expect(prompt).toBeHidden()
    })
  }
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill(account.email)
  await page.getByPlaceholder('••••••••').fill(account.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'))
}

/** A signed-in user with data, on the home screen. */
export async function signedInWithData(page, request, options) {
  const account = await newAccount(request)
  await callApi(request, account, 'GET', '/auth/me')   // creates the Vaulta user
  await seedData(request, account)
  await signIn(page, account, options)
  await expect(page.getByText('Safe to spend today')).toBeVisible()
  return account
}

/** On phones: no horizontal scrolling and every visible control at least 44px tall and wide. */
export async function checkLayout(page, testInfo) {
  if (testInfo.project.name !== 'mobile') return
  await page.waitForTimeout(150)
  // Compare with the device width, not innerWidth: on a phone the browser widens the layout
  // viewport to fit overflowing content, so innerWidth would grow along with the bug.
  const device = testInfo.project.use.viewport.width
  const issues = await page.evaluate((width) => {
    const out = []
    const doc = document.scrollingElement
    if (doc.scrollWidth > width + 1 || window.innerWidth > width + 1) {
      const wide = [...document.querySelectorAll('body *')].filter((el) => el.getBoundingClientRect().right > width + 1)
        .slice(0, 3).map((el) => `${el.tagName}.${String(el.className).slice(0, 60)}`)
      out.push(`page wider than the ${width}px screen (${Math.max(doc.scrollWidth, window.innerWidth)}px): ${wide.join(' | ')}`)
    }
    for (const el of document.querySelectorAll('button, a[href], select, input, textarea, summary, [role="button"]')) {
      const style = getComputedStyle(el)
      if (style.visibility === 'hidden' || style.display === 'none' || el.closest('[aria-hidden="true"]')) continue
      let box = el.getBoundingClientRect()
      if (!box.width || !box.height) continue
      if (el.tagName === 'A' && style.display === 'inline') continue                  // links inside text are exempt
      if (el.type === 'checkbox' || el.type === 'radio') box = (el.closest('label') || el).getBoundingClientRect()
      if (el.type === 'file') continue
      if (box.height < 43.5 || (el.tagName !== 'INPUT' && el.tagName !== 'SELECT' && el.tagName !== 'TEXTAREA' && box.width < 43.5)) {
        out.push(`small tap target ${Math.round(box.width)}×${Math.round(box.height)}: <${el.tagName.toLowerCase()}> “${(el.innerText || el.getAttribute('aria-label') || el.placeholder || '').trim().slice(0, 40)}”`)
      }
    }
    return out
  }, device)
  expect(issues, `${page.url()}\n${issues.join('\n')}`).toEqual([])
}
