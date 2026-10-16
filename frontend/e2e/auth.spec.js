// Phase 6.5 sign-in flows against the Firebase Auth emulator: email verification, password reset, linking Google
// and a password to one account, re-authentication for sensitive actions, signing out everywhere, deleting the login.
import { test, expect, API, APP_CHECK, checkLayout, newAccount, signIn, signInToken, signedInWithData, emulatorEmails, callApi } from './fixtures'

const uniqueEmail = (tag) => `${tag}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@vaulta.test`
const STRONG = 'correct-horse-battery'

test('sign-up needs a confirmed email before importing', async ({ page, request }, testInfo) => {
  const email = uniqueEmail('verify')
  await page.goto('/login')
  await page.getByRole('button', { name: 'Sign up' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(STRONG)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Check your inbox' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Resend in \d+s/ })).toBeDisabled()       // rate limited
  await checkLayout(page, testInfo)

  // the server refuses data until the address is confirmed, whatever the UI shows
  const token = await signInToken(request, email, STRONG)
  const refused = await request.post(`${API}/api/budgets`, { data: { category: 'Travel', monthly_limit: '100' }, headers: { Authorization: `Bearer ${token}`, ...APP_CHECK } })
  expect(refused.status()).toBe(403)
  expect((await refused.json()).code).toBe('email_unverified')
  await page.goto('/transactions')
  await expect(page).toHaveURL(/\/verify-email$/)

  // open the link from the email, then confirm in the app
  const [mail] = (await emulatorEmails(request, email)).filter((c) => c.requestType === 'VERIFY_EMAIL')
  expect((await request.get(mail.oobLink)).ok()).toBe(true)
  await page.getByRole('button', { name: "I've confirmed my email" }).click()
  await expect(page).not.toHaveURL(/verify-email/)
  const fresh = await signInToken(request, email, STRONG)
  await callApi(request, { token: fresh }, 'POST', '/api/import/batch', { rows: [{ date: '2024-06-01', description_raw: 'SWIGGY', amount: '100.00',
    direction: 'debit', reference: null, source_type: 'bank_csv', source_label: 'HDFC Bank' }] })
})

test('signing up with an address that already has an account looks the same as a new one', async ({ page, request, guard }) => {
  guard.allow(/status of 400/)                              // Firebase's own EMAIL_EXISTS answer, handled by the page
  const existing = await newAccount(request)
  await page.goto('/login')
  await page.getByRole('button', { name: 'Sign up' }).click()
  await page.getByLabel('Email').fill(existing.email)
  await page.getByLabel('Password', { exact: true }).fill(STRONG)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Check your inbox' })).toBeVisible()
  await expect(page.getByText('If ')).toContainText(existing.email)
})

test('a stale session must sign in again before exporting', async ({ page, request, guard }, testInfo) => {
  guard.allow(/status of 400/)                              // Firebase's answer to the wrong password below
  const account = await signedInWithData(page, request, { reauth: false })
  await page.goto('/settings')
  await page.waitForTimeout(31_000)                       // RECENT_LOGIN_SECONDS is 30 in browser tests
  await page.getByRole('button', { name: 'Export my data' }).click()
  const prompt = page.getByRole('dialog', { name: 'Sign in again' })
  await expect(prompt).toBeVisible()
  await checkLayout(page, testInfo)
  await prompt.getByLabel(/^Password for/).fill('not-the-password')
  await prompt.getByRole('button', { name: 'Confirm' }).click()
  await expect(prompt.getByRole('alert')).toHaveText("That password didn't work.")
  const downloading = page.waitForEvent('download')
  await prompt.getByLabel(/^Password for/).fill(account.password)
  await prompt.getByRole('button', { name: 'Confirm' }).click()
  expect((await downloading).suggestedFilename()).toMatch(/^vaulta-export-/)   // the request was retried
  const kinds = (await callApi(request, { token: await signInToken(request, account.email, account.password) }, 'GET', '/api/activity')).map((e) => e.kind)
  expect(kinds).toContain('reauth_failed')
  expect(kinds).toContain('export')
})

test('sign out of all devices ends a second browser\'s session too', async ({ page, request, browser, guard }, testInfo) => {
  const account = await signedInWithData(page, request)
  const other = await browser.newContext({ viewport: page.viewportSize() })
  const second = await other.newPage()
  second.on('console', (m) => { if (m.type() === 'error' && !/status of (400|401)/.test(m.text())) throw new Error(m.text()) })
  await signIn(second, account)
  await expect(second.getByText('Safe to spend today')).toBeVisible()
  const third = await browser.newContext({ viewport: page.viewportSize() })
  const p3 = await third.newPage()
  await signIn(p3, account)
  await p3.goto('/goals')
  await page.waitForTimeout(1100)    // revocation counts whole seconds: sessions from the same second stay valid

  await page.goto('/settings')
  await page.getByRole('button', { name: 'Sign out of all devices' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText('You were signed out on all your devices')).toBeVisible()
  await checkLayout(page, testInfo)

  // the second browser, still open on the app: its ID token is within its hour, but the API refuses it
  await second.evaluate(() => { window.history.pushState({}, '', '/transactions'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await expect(second).toHaveURL(/\/login$/)
  await expect(second.getByText('Your session was signed out. Sign in again.')).toBeVisible()
  await second.getByPlaceholder('you@example.com').fill(account.email)            // and it returns to /transactions
  await second.getByPlaceholder('••••••••').fill(account.password)
  await second.getByRole('button', { name: 'Log in' }).click()
  await expect(second).toHaveURL(/\/transactions$/)

  // a third, reloaded afterwards: Firebase itself sees the revoked session, signs it out, login brings it back
  guard.allow(/status of 400/)
  await p3.reload()
  await expect(p3).toHaveURL(/\/login$/)
  await p3.getByPlaceholder('you@example.com').fill(account.email)                 // right here, not a fresh /login
  await p3.getByPlaceholder('••••••••').fill(account.password)
  await p3.getByRole('button', { name: 'Log in' }).click()
  await expect(p3).toHaveURL(/\/goals$/)
  await other.close()
  await third.close()
})

test('forgot password: same answer for any address, and the reset works', async ({ page, request, guard }, testInfo) => {
  guard.allow(/status of 400/)       // the emulator says EMAIL_NOT_FOUND (production has enumeration protection on)
  const account = await newAccount(request)
  await callApi(request, account, 'GET', '/auth/me')
  const answer = async (email) => {
    await page.goto('/login')
    await page.getByRole('button', { name: 'Forgot password?' }).click()
    await page.getByLabel('Email').fill(email)
    await page.getByRole('button', { name: 'Send reset link' }).click()
    const message = page.getByText(/^If there's an account/)
    await expect(message).toBeVisible()
    return message.innerText()
  }
  const unknown = await answer(uniqueEmail('nobody'))
  const known = await answer(account.email)
  expect(known).toBe(unknown)
  expect(known).toContain("If there's an account for that email")
  await checkLayout(page, testInfo)

  const [reset] = (await emulatorEmails(request, account.email)).filter((c) => c.requestType === 'PASSWORD_RESET')
  const done = await request.post('http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:resetPassword?key=e2e-fake-key',
    { data: { oobCode: reset.oobCode, newPassword: STRONG } })
  expect(done.ok()).toBe(true)
  await signIn(page, { ...account, password: STRONG })
  const kinds = (await callApi(request, { token: await signInToken(request, account.email, STRONG) }, 'GET', '/api/activity')).map((e) => e.kind)
  expect(kinds).toEqual(expect.arrayContaining(['password_reset_requested', 'password_reset_completed']))
})

test('change password in Settings', async ({ page, request, guard }) => {
  guard.allow(/status of 400/)       // the old session's token refresh, refused, before the browser signs back in
  const account = await signedInWithData(page, request)
  await page.goto('/settings')
  await page.getByLabel('New password').fill('short')
  await page.getByLabel('Type it again').fill('short')
  await page.getByRole('button', { name: 'Change password' }).click()
  await expect(page.getByRole('alert')).toHaveText('Use at least 10 characters.')
  await page.getByLabel('New password').fill(STRONG)
  await page.getByLabel('Type it again').fill(STRONG)
  await page.getByRole('button', { name: 'Change password' }).click()
  await expect(page.getByText('Password changed. Your other devices were signed out.')).toBeVisible()
  await page.goto('/budgets')                                    // this browser stays signed in
  await expect(page.getByRole('heading', { name: 'Budgets' })).toBeVisible()
  const old = await request.post('http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=e2e-fake-key',
    { data: { email: account.email, password: account.password, returnSecureToken: true } })
  expect(old.ok()).toBe(false)
})

/** Sign in with Google as `email`: the e2e build's hook (src/lib/firebase.js); the emulator's popup can't complete here. */
async function googleSignIn(page, email) {
  await page.goto('/login')
  await page.waitForFunction(() => typeof window.__e2eGoogleSignIn === 'function')
  return page.evaluate((e) => window.__e2eGoogleSignIn(e), email)
}

test('Google and a password sign in to one account', async ({ page, request }, testInfo) => {
  const account = await newAccount(request)
  await callApi(request, account, 'GET', '/auth/me')
  await callApi(request, account, 'POST', '/api/budgets', { category: 'Travel', monthly_limit: '4321' })
  await callApi(request, account, 'PATCH', '/api/onboarding', { status: 'done', step: 'finish' })

  expect(await googleSignIn(page, account.email)).toBe(account.uid)              // Firebase links: same account
  await page.waitForURL((u) => !u.pathname.startsWith('/login'))
  await page.goto('/budgets')
  await expect(page.getByText('Travel').first()).toBeVisible()                 // the password account's data

  await page.goto('/settings')
  const methods = page.getByRole('list', { name: 'Sign-in methods' })
  await expect(methods.getByRole('listitem')).toHaveText([/Email and password/, /Google/])
  await checkLayout(page, testInfo)

  page.once('dialog', (d) => d.accept())
  await methods.getByRole('button', { name: 'Remove Google' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText('Google was removed and every device was signed out')).toBeVisible()
  await signIn(page, account)
  await page.goto('/settings')
  await expect(page.getByRole('list', { name: 'Sign-in methods' }).getByRole('listitem')).toHaveText([/Email and password/])
  await expect(page.getByRole('button', { name: /^Remove/ })).toHaveCount(0)    // never the last method
  const kinds = (await callApi(request, { token: await signInToken(request, account.email, account.password) }, 'GET', '/api/activity')).map((e) => e.kind)
  expect(kinds).toEqual(expect.arrayContaining(['method_unlinked', 'signed_out_everywhere']))
})

test('App Check: the API refuses bot-target routes without a token from the app', async ({ request }) => {
  const account = await newAccount(request)
  await callApi(request, account, 'GET', '/auth/me')
  const body = { rows: [{ date: '2024-06-01', description_raw: 'SWIGGY', amount: '100.00', direction: 'debit', reference: null,
    source_type: 'bank_csv', source_label: 'HDFC Bank' }] }
  const bare = await request.post(`${API}/api/import/batch`, { data: body, headers: { Authorization: `Bearer ${account.token}` } })
  expect(bare.status()).toBe(401)
  expect((await bare.json()).code).toBe('app_check_failed')
  expect((await request.post(`${API}/auth/demo`)).status()).toBe(401)
  await callApi(request, account, 'POST', '/api/import/batch', body)               // the app's token: accepted
})

test('logging in: a wrong password and an unknown email read exactly the same', async ({ page, request, guard }) => {
  guard.allow(/status of 400/)                              // the emulator's own answers (production hides even those)
  const account = await newAccount(request)
  const attempt = async (email, password) => {
    await page.goto('/login')
    await page.getByPlaceholder('you@example.com').fill(email)
    await page.getByPlaceholder('••••••••').fill(password)
    await page.getByRole('button', { name: 'Log in' }).click()
    return page.getByRole('alert').innerText()
  }
  const wrongPassword = await attempt(account.email, 'not-the-password')
  const unknownEmail = await attempt(uniqueEmail('nobody'), 'not-the-password')
  expect(wrongPassword).toBe('Incorrect email or password.')
  expect(unknownEmail).toBe(wrongPassword)
})
