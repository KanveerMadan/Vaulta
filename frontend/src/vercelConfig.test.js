// vercel.json is checked with Vercel's own route parser: an invalid pattern fails every deployment (it did, unnoticed,
// from Phase 6 to the release branch), and nothing else in CI reads this file.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { getTransformedRoutes } from '@vercel/routing-utils'
import config from '../vercel.json'

const { routes, error } = getTransformedRoutes({ rewrites: config.rewrites, headers: config.headers, redirects: config.redirects })
// The patterns are Vercel's compiled form of our own vercel.json, tested against fixed paths: no user input.
// nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
const matches = (route, path) => new RegExp(route.src).test(path)
const headersFor = (path) => Object.assign({}, ...routes.filter((r) => r.headers && matches(r, path)).map((r) => r.headers))

describe('vercel.json', () => {
  it('is accepted by Vercel', () => {
    expect(error).toBeNull()
  })

  it('serves the app shell for routes and files as themselves', () => {
    const rewrite = routes.find((r) => r.dest === '/index.html')
    expect(matches(rewrite, '/transactions')).toBe(true)
    expect(matches(rewrite, '/reports/42')).toBe(true)
    expect(matches(rewrite, '/assets/index-abc.js')).toBe(false)
    expect(matches(rewrite, '/sw.js')).toBe(false)
  })

  it('caches hashed assets for good and never caches the shell or service worker', () => {
    expect(headersFor('/assets/index-abc.js')['Cache-Control']).toBe('public, max-age=31536000, immutable')
    for (const path of ['/index.html', '/sw.js', '/registerSW.js', '/manifest.webmanifest', '/workbox-cf7f91f8.js']) {
      expect(headersFor(path)['Cache-Control'], path).toBe('no-cache')
    }
    expect(headersFor('/transactions')['Content-Security-Policy']).toMatch(/frame-ancestors 'none'/)
  })

  it('sends the default and www hosts to vaulta.in for good (308), keeping the path', () => {
    for (const host of ['vaulta-henna.vercel.app', 'www.vaulta.in']) {
      const r = routes.find((x) => x.status === 308 && x.has?.[0]?.value === host)
      expect(r, host).toBeTruthy()
      expect(matches(r, '/security')).toBe(true)
      expect(r.headers.Location).toMatch(/^https:\/\/vaulta\.in\//)
    }
  })

  it('serves Firebase sign-in from vaulta.in, before the app shell', () => {
    const auth = routes.findIndex((r) => r.dest?.startsWith('https://vaulta-a3d7a.firebaseapp.com/__/auth/'))
    expect(auth).toBeGreaterThan(-1)
    expect(matches(routes[auth], '/__/auth/handler')).toBe(true)
    expect(auth).toBeLessThan(routes.findIndex((r) => r.dest === '/index.html'))
    const fb = routes.findIndex((r) => r.dest?.startsWith('https://vaulta-a3d7a.firebaseapp.com/__/firebase/'))
    expect(fb).toBeGreaterThan(-1)
    expect(fb).toBeLessThan(routes.findIndex((r) => r.dest === '/index.html'))
  })

  // Our CSP blocked the handler's inline script and frame-ancestors 'none' blocked the iframe vaulta.in embeds
  it("leaves Firebase's sign-in pages with Firebase's own headers", () => {
    for (const path of ['/__/auth/handler', '/__/auth/iframe', '/__/firebase/init.json']) {
      const h = headersFor(path)
      expect(h['Content-Security-Policy'], path).toBeUndefined()
      expect(h['X-Frame-Options'], path).toBeUndefined()
    }
  })

  // The service worker answered /__/auth/handler with the app, which redirected the Google popup to /welcome
  it('the service worker never answers /__/ with the app', () => {
    const viteConfig = readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8')
    const deny = viteConfig.match(/navigateFallbackDenylist: \[(.*)\]/)[1]
    expect(deny).toContain(String.raw`/^\/__\//`)
  })
})
