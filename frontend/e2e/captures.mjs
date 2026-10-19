// Records the showpieces as Playwright videos into docs/design/captures/ (needs the browser-test
// servers running, see e2e/README.md):   node e2e/captures.mjs
import { chromium, request } from '@playwright/test'
import { mkdirSync, renameSync, readdirSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { RECAPTCHA, newAccount, seedData } from './fixtures.js'

const APP = 'http://localhost:4173'
const OUT = fileURLToPath(new URL('../../docs/design/captures/', import.meta.url))
const TMP = fileURLToPath(new URL('../test-results/captures-tmp/', import.meta.url))
mkdirSync(OUT, { recursive: true })
const size = { width: 1280, height: 800 }
const phone = { width: 390, height: 844 }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

async function account(r, withData) {
  const a = await newAccount(r)
  await r.get('http://127.0.0.1:8001/auth/me', { headers: { Authorization: `Bearer ${a.token}`, ...RECAPTCHA } })
  if (withData) await seedData(r, a)
  return a
}

async function login(page, a) {
  await page.goto(`${APP}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('you@example.com').fill(a.email)
  await page.getByPlaceholder('••••••••').fill(a.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'))
}

async function record(name, viewport, fn) {
  rmSync(TMP, { recursive: true, force: true })
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport, recordVideo: { dir: TMP, size: viewport } })
  const page = await ctx.newPage()
  await fn(page)
  await ctx.close()
  await browser.close()
  const [file] = readdirSync(TMP)
  renameSync(TMP + file, `${OUT}${name}.webm`)
  console.log(`saved docs/design/captures/${name}.webm`)
}

const r = await request.newContext()

await record('landing-scroll-story', size, async (page) => {
  await page.goto(`${APP}/welcome`, { waitUntil: 'networkidle' })
  await wait(1500)
  for (let i = 0; i < 70; i++) { await page.mouse.wheel(0, 90); await wait(110) }
  await wait(1500)
  for (let i = 0; i < 40; i++) { await page.mouse.wheel(0, 120); await wait(90) }
  await wait(2500)
})

await record('landing-scroll-story-phone', phone, async (page) => {
  await page.goto(`${APP}/welcome`, { waitUntil: 'networkidle' })
  await wait(1200)
  for (let i = 0; i < 80; i++) { await page.mouse.wheel(0, 70); await wait(110) }
  await wait(2000)
})

const newUser = await account(r, false)
await record('onboarding', size, async (page) => {
  await login(page, newUser)
  await page.goto(`${APP}/onboarding`, { waitUntil: 'networkidle' })
  await wait(1200)
  await page.getByLabel('Monthly take-home income (optional)').fill('85000'); await wait(400)
  for (const b of ['HDFC Bank', 'SBI Card', 'Google Pay']) { await page.getByRole('button', { name: b }).click(); await wait(350) }
  await page.getByRole('button', { name: 'Continue' }).click(); await wait(1800)
  await page.getByRole('button', { name: 'Skip for now' }).click(); await wait(1200)
  await page.getByRole('button', { name: 'Import a statement' }).click(); await wait(600)
  await page.locator('input[type=file]').setInputFiles(fileURLToPath(new URL('../../fixtures/statements/hdfc.csv', import.meta.url)))
  await wait(4500)
  await page.getByRole('button', { name: /^Import \d+ transactions$/ }).click(); await wait(1800)
  await page.getByRole('button', { name: 'Close' }).click(); await wait(1500)
  await page.getByRole('button', { name: 'Continue' }).click(); await wait(1500)
  for (let i = 0; i < 6 && await page.getByText(/^\d+ left$/).isVisible(); i++) {
    await page.keyboard.press('1'); await wait(900)
  }
  for (let i = 0; i < 30 && await page.getByText(/^\d+ left$/).isVisible(); i++) { await page.keyboard.press('s'); await wait(250) }
  await page.getByRole('button', { name: 'Continue' }).click(); await wait(3500)
})

const yearUser = await account(r, true)
const annual = await (await r.post('http://127.0.0.1:8001/api/reports/generate', {
  data: { period_type: 'annual', date: new Date().toISOString().slice(0, 10) }, headers: { Authorization: `Bearer ${yearUser.token}` } })).json()
await record('money-wrapped', phone, async (page) => {
  await login(page, yearUser)
  await page.goto(`${APP}/reports/${annual.id}/wrapped`, { waitUntil: 'networkidle' })
  await wait(2200)
  for (let i = 0; i < 8; i++) { await page.keyboard.press('ArrowRight'); await wait(2000) }
  await page.getByLabel('Show merchant names').check(); await wait(1200)
  await page.getByLabel('Show amounts').uncheck(); await wait(2000)
})

rmSync(TMP, { recursive: true, force: true })
