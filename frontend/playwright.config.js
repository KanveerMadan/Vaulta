// Browser tests: a fresh local backend + database, the Firebase Auth emulator and a fake LLM. See e2e/README.md.
import { defineConfig } from '@playwright/test'

const PY = process.env.E2E_PYTHON || '../backend/venv/bin/python'
const reuse = !process.env.CI && !!process.env.E2E_REUSE
// Visual baselines depend on the OS the *browser* runs on. To render Linux baselines from a Mac, run the browser in
// Playwright's Linux image (e2e/README.md): PW_WS_ENDPOINT points at it and PW_BROWSER_OS=linux names the files.
const browserOS = process.env.PW_BROWSER_OS || process.platform
const remote = process.env.PW_WS_ENDPOINT ? { connectOptions: { wsEndpoint: process.env.PW_WS_ENDPOINT, exposeNetwork: '<loopback>' } } : {}

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
    { name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1280, height: 800 } } },
    { name: 'mobile', use: { browserName: 'chromium', viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } },
    // the same flows with prefers-reduced-motion: every animated surface has a designed still version
    { name: 'reduced-motion', testMatch: /(public|app|visual)\.spec\.js/, use: { browserName: 'chromium', viewport: { width: 1280, height: 800 }, contextOptions: { reducedMotion: 'reduce' } } },
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
