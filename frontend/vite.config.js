import { readFileSync } from 'node:fs'
import { defineConfig, loadEnv } from 'vite'
import { configDefaults } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Security headers live in vercel.json (production and previews). `vite preview` serves the same ones, so the
// browser tests run under the real Content-Security-Policy; in e2e mode the API, Firebase and auth-domain origins
// are swapped for the local servers. A production build fails if the API it calls isn't allowed by the CSP.
const vercel = JSON.parse(readFileSync(new URL('./vercel.json', import.meta.url), 'utf8'))
const headers = Object.fromEntries(vercel.headers[0].headers.map((h) => [h.key, h.value]))
export const PROD_API = 'https://vaulta-f6t8.onrender.com'

function localHeaders(env) {
  const csp = headers['Content-Security-Policy']
    .replace(PROD_API, new URL(env.VITE_API_BASE_URL).origin)
    .replace('https://identitytoolkit.googleapis.com https://securetoken.googleapis.com', new URL(env.VITE_FIREBASE_AUTH_EMULATOR).origin)
    .replace('https://vaulta-a3d7a.firebaseapp.com', `http://${env.VITE_FIREBASE_AUTH_DOMAIN}`)
    .replace('; upgrade-insecure-requests', '')
  const { 'Strict-Transport-Security': _hsts, ...rest } = headers   // eslint-disable-line no-unused-vars
  return { ...rest, 'Content-Security-Policy': csp }
}

function cspCoversApi(env, mode) {
  return {
    name: 'csp-covers-api',
    buildStart() {
      if (mode !== 'production' || !env.VITE_API_BASE_URL) return
      const origin = new URL(env.VITE_API_BASE_URL).origin
      const connect = headers['Content-Security-Policy'].split(';').find((d) => d.trim().startsWith('connect-src'))
      if (!connect.split(/\s+/).includes(origin)) {
        this.error(`VITE_API_BASE_URL (${origin}) isn't in vercel.json's connect-src: the app couldn't reach its API. Update vercel.json.`)
      }
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
  plugins: [
    cspCoversApi(env, mode),
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'script-defer',   // never render-blocking
      includeAssets: ['favicon.svg'],
      // The service worker precaches the built static files only. No runtime caching at all:
      // API responses and financial data are never stored by it. OCR assets (~7 MB) load on demand.
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        globIgnores: ['ocr/**'],
        runtimeCaching: [],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/auth\//, /^\/internal\//, /^\/unsubscribe/],
      },
      manifest: {
        name: 'Vaulta',
        short_name: 'Vaulta',
        description: 'Tracks every rupee you spend, automatically.',
        theme_color: '#0A1A0E',
        background_color: '#F2F7F3',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  test: { exclude: [...configDefaults.exclude, 'e2e/**'] },   // e2e/ is Playwright's (npm run test:e2e)
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  preview: { headers: mode === 'e2e' ? localHeaders(env) : {} },
  }
})