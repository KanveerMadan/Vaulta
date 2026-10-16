// Browser tests: a fresh local backend + database, the Firebase Auth emulator and a fake LLM. See e2e/README.md.
import { defineConfig, devices } from '@playwright/test'

const PY = process.env.E2E_PYTHON || '../backend/venv/bin/python'
const reuse = !process.env.CI && !!process.env.E2E_REUSE
// Visual baselines depend on the OS the *browser* runs on. To render Linux baselines from a Mac, run the browser in
// Playwright's Linux image (e2e/README.md): PW_WS_ENDPOINT points at it and PW_BROWSER_OS=linux names the files.
const browserOS = process.env.PW_BROWSER_OS || process.platform
const remote = process.env.PW_WS_ENDPOINT ? { connectOptions: { wsEndpoint: process.env.PW_WS_ENDPOINT, exposeNetwork: '<loopback>' } } : {}

const FULL_SUITE_IGNORE = /(visual|devices)\.spec\.js/
const DEVICES = [
  ['iphone-se', devices['iPhone SE']],
  ['iphone-15-pro', devices['iPhone 15 Pro']],
  ['pixel-7', devices['Pixel 7']],
  ['galaxy-s24', devices['Galaxy S24']],
  ['ipad-mini', devices['iPad Mini']],
  ['ipad-mini-landscape', devices['iPad Mini landscape']],
  ['ipad-pro-11', devices['iPad Pro 11']],
  ['laptop-1366', { browserName: 'chromium', viewport: { width: 1366, height: 768 } }],
  ['monitor-2560', { browserName: 'chromium', viewport: { width: 2560, height: 1440 } }],
]

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  workers: process.env.E2E_WORKERS ? Number(process.env.E2E_WORKERS) : 3,
  retries: 0,
  reporter: [['list']],
  snapshotPathTemplate: `{testDir}/{testFileName}-snapshots/{arg}{-projectName}-${browserOS}{ext}`,
  use: { baseURL: 'http://localhost:4173', trace: 'retain-on-failure', ...remote },
  projects: [
    { name: 'desktop', testIgnore: /devices\.spec\.js/, use: { browserName: 'chromium', viewport: { width: 1280, height: 800 } } },
    { name: 'mobile', testIgnore: /devices\.spec\.js/, use: { browserName: 'chromium', viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } },
    // the same flows with prefers-reduced-motion: every animated surface has a designed still version
    { name: 'reduced-motion', testMatch: /(public|app|visual)\.spec\.js/, use: { browserName: 'chromium', viewport: { width: 1280, height: 800 }, contextOptions: { reducedMotion: 'reduce' } } },
    // The whole suite on the other two engines (visual baselines stay Chromium; devices.spec covers each device)
    // Playwright's patched Firefox closes a page that reloads under the PWA's service worker (an automation
    // limitation): Firefox runs with service workers blocked; the service worker is tested on Chromium and WebKit
    { name: 'firefox', testIgnore: FULL_SUITE_IGNORE, use: { ...devices['Desktop Firefox'], viewport: { width: 1280, height: 800 }, serviceWorkers: 'block' } },
    { name: 'webkit', testIgnore: FULL_SUITE_IGNORE, use: { ...devices['Desktop Safari'], viewport: { width: 1280, height: 800 } } },
    { name: 'webkit-iphone', testIgnore: FULL_SUITE_IGNORE, use: { ...devices['iPhone 15 Pro'] } },
    // Each device: layout checks and per-device screenshots of the key screens (e2e/devices.spec.js)
    ...DEVICES.map(([name, use]) => ({ name, testMatch: /devices\.spec\.js/, use })),
  ],
  webServer: [
    { command: 'npx firebase emulators:start --only auth --project demo-vaulta --config e2e/firebase.json',
      url: 'http://127.0.0.1:9099/', reuseExistingServer: reuse, timeout: 120_000 },
    { command: `${PY} e2e/servers/fake_llm.py`, url: 'http://127.0.0.1:8002/', reuseExistingServer: reuse },
    { command: `${PY} e2e/servers/backend.py`, url: 'http://127.0.0.1:8001/health', reuseExistingServer: reuse, timeout: 120_000, stdout: 'ignore' },
    { command: 'npx vite build --mode e2e --outDir dist-e2e && npx vite preview --mode e2e --outDir dist-e2e --port 4173 --strictPort',
      url: 'http://localhost:4173/', reuseExistingServer: reuse, timeout: 180_000 },
  ],
})
