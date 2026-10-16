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
const connectSrc = headers['Content-Security-Policy'].split(';').find((d) => d.trim().startsWith('connect-src')).trim().split(/\s+/)
// The API's origin: the one https connect-src entry that isn't Firebase Auth
export const PROD_API = connectSrc.find((o) => o.startsWith('https://') && !o.endsWith('.googleapis.com'))

function localHeaders(env) {
  const csp = headers['Content-Security-Policy']
    .replace(PROD_API, new URL(env.VITE_API_BASE_URL).origin)
    .replace('https://identitytoolkit.googleapis.com https://securetoken.googleapis.com', new URL(env.VITE_FIREBASE_AUTH_EMULATOR).origin)
    // Firebase frames the auth domain; against the emulator it frames the emulator itself
    .replace('https://vaulta-a3d7a.firebaseapp.com', `http://${env.VITE_FIREBASE_AUTH_DOMAIN} ${new URL(env.VITE_FIREBASE_AUTH_EMULATOR).origin}`)
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
      if (!connectSrc.includes(origin)) {
        this.error(`VITE_API_BASE_URL (${origin}) isn't in vercel.json's connect-src: the app couldn't reach its API. Update vercel.json.`)
      }
    },
  }
}

// /.well-known/security.txt (RFC 9116) from VITE_SECURITY_CONTACT; the privacy page needs VITE_PRIVACY_CONTACT.
// A production build without them fails, so the security page and privacy policy never ship without a contact.
function securityTxt(env, mode) {
  return {
    name: 'security-txt',
    buildStart() {
      if (mode !== 'production') return
      for (const name of ['VITE_SECURITY_CONTACT', 'VITE_PRIVACY_CONTACT']) {
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(env[name] || '')) this.error(`${name} must be set to an email address for a production build.`)
      }
    },
    generateBundle() {
      if (!env.VITE_SECURITY_CONTACT) return
      const expires = new Date(Date.now() + 180 * 864e5).toISOString().replace(/\.\d+Z$/, 'Z')
      this.emitFile({ type: 'asset', fileName: '.well-known/security.txt', source:
        `Contact: mailto:${env.VITE_SECURITY_CONTACT}\nExpires: ${expires}\nPreferred-Languages: en\n` })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
  plugins: [
    cspCoversApi(env, mode),
    securityTxt(env, mode),
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