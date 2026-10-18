// Simulations and the preview layer (Phase 8 steps 3–4): samples through the real pipelines, labelled, never counted,
// one-click clear; the statement sample never leaves the device; all of it works in the demo without saving.
import { test, expect, checkLayout, newAccount, callApi, seedData, signIn, openMenu } from './fixtures'

test('bank alert, statement and quick add samples, labelled and cleared in one click', async ({ page, request }, testInfo) => {
  const a = await newAccount(request)
  await callApi(request, a, 'GET', '/auth/me')
  await seedData(request, a)
  const before = await callApi(request, a, 'GET', '/api/transactions/summary?period=month')
  await signIn(page, a)
  await page.goto('/try')
  await expect(page.getByRole('heading', { name: 'Try it with samples' })).toBeVisible()
  await checkLayout(page, testInfo)

  // a bank alert, through the alert pipeline
  const alert = page.getByRole('region', { name: 'A bank alert email' })
  await alert.getByLabel('Bank').selectOption('icici')
  await alert.getByRole('button', { name: 'Send a sample alert' }).click()
  await expect(alert.getByText(/INR 342\.50 spent using ICICI Bank Credit Card/)).toBeVisible()
  await expect(alert.getByText('Sample', { exact: true })).toBeVisible()
  await expect(alert.getByText(/Uber/).first()).toBeVisible()
  await expect(alert.getByRole('link', { name: 'Forward your real alerts' })).toHaveAttribute('href', '/connect#forwarding')

  // a statement, read on this device: nothing is sent
  const posts = []
  page.on('request', (r) => { if (r.method() !== 'GET' && r.url().includes('/api/import')) posts.push(r.url()) })
  await page.getByRole('button', { name: 'Open a sample statement' }).click()
  const sheet = page.getByRole('dialog', { name: 'Sample statement' })
  await expect(sheet.getByText(/transactions from HDFC Bank/)).toBeVisible()
  await expect(sheet.getByText(/This is a sample\. Nothing is imported/)).toBeVisible()
  await expect(sheet.getByTestId('balance-check')).toContainText('Balances check out')
  await expect(sheet.getByText(/A\*\*\*@okaxis/).first()).toBeVisible()                    // the personal UPI ID, masked here
  await expect(sheet.getByRole('button', { name: /^Import \d+ transactions$/ })).toHaveCount(0)
  await expect(sheet.getByRole('link', { name: 'Import your own statement' })).toBeVisible()
  await sheet.getByRole('button', { name: 'Close' }).click()
  expect(posts).toEqual([])

  // quick add / Telegram
  const quick = page.getByRole('region', { name: 'Quick add and Telegram' })
  await quick.getByRole('button', { name: 'Try it' }).click()
  await expect(quick.getByText(/^₹150 · Auto · Transport · today · cash$/)).toBeVisible()
  await quick.getByRole('button', { name: 'Save it as a sample' }).click()
  await expect(quick.getByText(/Saved as a sample cash entry/)).toBeVisible()

  // listed and labelled, never counted, cleared in one click
  await openMenu(page)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Transactions', exact: true }).click()
  await expect(page.getByText(/2 sample transactions from trying Vaulta out/)).toBeVisible()
  await expect(page.getByRole('list', { name: 'Transactions' }).getByText('Sample', { exact: true })).toHaveCount(2)
  expect(await callApi(request, a, 'GET', '/api/transactions/summary?period=month')).toEqual(before)
  await page.getByRole('button', { name: 'Clear samples' }).click()
  await expect(page.getByText(/sample transactions? from trying/)).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Transactions' }).getByText('Sample', { exact: true })).toHaveCount(0)
})

test('the demo can try everything, and nothing is saved', async ({ page }) => {
  await page.goto('/welcome')
  await page.getByRole('button', { name: 'Try the demo' }).first().click()
  await expect(page.getByText("You're viewing a demo with sample data.")).toBeVisible()
  await page.getByRole('link', { name: 'Try the simulations' }).click()
  const alert = page.getByRole('region', { name: 'A bank alert email' })
  await alert.getByRole('button', { name: 'Send a sample alert' }).click()
  await expect(alert.getByText('In the demo nothing is saved.')).toBeVisible()
  await expect(alert.getByText(/Swiggy/).first()).toBeVisible()
  const quick = page.getByRole('region', { name: 'Quick add and Telegram' })
  await quick.getByRole('button', { name: 'Try it' }).click()
  await expect(quick.getByText('In the demo nothing is saved.')).toBeVisible()
  await page.getByRole('button', { name: 'Open a sample statement' }).click()
  await expect(page.getByRole('dialog', { name: 'Sample statement' }).getByText(/This is a sample\. Nothing is imported/)).toBeVisible()
})
