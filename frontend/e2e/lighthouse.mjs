// Lighthouse (mobile profile: simulated slow 4G and a mid-range phone CPU) on the landing page and
// the signed-in home screen. Needs the browser-test servers running (see e2e/README.md):
//   E2E_REUSE=1 npx playwright test e2e/public.spec.js   # or start them by hand
//   node e2e/lighthouse.mjs [output.json]
import { chromium, request } from '@playwright/test'
import lighthouse from 'lighthouse'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { newAccount, seedData } from './fixtures.js'

const APP = 'http://localhost:4173'
const PORT = 9333
const out = process.argv[2]

// a signed-in user with three months of data
const r = await request.newContext()
const account = await newAccount(r)
const { email, password } = account
await r.get('http://127.0.0.1:8001/auth/me', { headers: { Authorization: `Bearer ${account.token}` } })
await seedData(r, account)

const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'lh-')), { args: [`--remote-debugging-port=${PORT}`] })
const page = await ctx.newPage()
await page.goto(`${APP}/login`, { waitUntil: 'networkidle' })
await page.getByPlaceholder('you@example.com').fill(email)
await page.getByPlaceholder('••••••••').fill(password)
await page.getByRole('button', { name: 'Log in' }).click()
await page.waitForURL(`${APP}/`)

const results = {}
for (const [name, path] of [['landing', '/welcome'], ['home', '/']]) {
  // a cold load: no service worker and no cached app files (the sign-in in IndexedDB stays)
  await page.evaluate(async () => {
    for (const reg of await navigator.serviceWorker.getRegistrations()) await reg.unregister()
    for (const key of await caches.keys()) await caches.delete(key)
  })
  const { lhr } = await lighthouse(`${APP}${path}`, {
    port: PORT, output: 'json', logLevel: 'error', disableStorageReset: true,
    onlyCategories: ['performance', 'accessibility', 'best-practices'],
  })
  results[name] = {
    performance: Math.round(lhr.categories.performance.score * 100),
    accessibility: Math.round(lhr.categories.accessibility.score * 100),
    bestPractices: Math.round(lhr.categories['best-practices'].score * 100),
    lcp: lhr.audits['largest-contentful-paint'].displayValue,
    cls: lhr.audits['cumulative-layout-shift'].displayValue,
    tbt: lhr.audits['total-blocking-time'].displayValue,
    fcp: lhr.audits['first-contentful-paint'].displayValue,
    netw: (lhr.audits['network-requests']?.details?.items || []).filter((x) => x.resourceType === 'Script' || x.resourceType === 'Font' || x.resourceType === 'Stylesheet' || x.resourceType === 'Fetch' || x.resourceType === 'XHR').map((x) => `${Math.round(x.networkRequestTime)}-${Math.round(x.networkEndTime)} ${Math.round(x.transferSize / 1024)}k ${x.url.replace('http://localhost:4173', '').replace('http://127.0.0.1:8001', 'API')}`),
    lcpInfo: Object.keys(lhr.audits).filter((k) => /lcp|largest|render-block|font/.test(k)).map((k) => `${k}: ${String(lhr.audits[k].displayValue ?? '')} ${JSON.stringify(lhr.audits[k].details ?? {}).slice(0, 400)}`),
    chain: Object.keys(lhr.audits['critical-request-chains']?.details?.chains || {}).length,
    failing: Object.values(lhr.audits).filter((a) => a.score !== null && a.score < 0.9 && a.scoreDisplayMode === 'binary').map((a) => a.id),
  }
}
await ctx.close()
console.log(JSON.stringify(results, null, 2))
if (out) writeFileSync(out, JSON.stringify(Object.fromEntries(Object.entries(results).map(([k, v]) =>
  [k, { performance: v.performance, accessibility: v.accessibility, bestPractices: v.bestPractices, lcp: v.lcp, cls: v.cls, tbt: v.tbt, fcp: v.fcp }])), null, 2) + '\n')
