// Phase 6.5 sign-in flows against the Firebase Auth emulator: email verification, password reset, linking Google
// and a password to one account, re-authentication for sensitive actions, signing out everywhere, deleting the login.
import { test, expect, API, checkLayout, newAccount, signIn, signInToken, emulatorEmails, accountExists, callApi } from './fixtures'

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
  const refused = await request.post(`${API}/api/budgets`, { data: { category: 'Travel', monthly_limit: '100' }, headers: { Authorization: `Bearer ${token}` } })
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
