// vercel.json is checked with Vercel's own route parser: an invalid pattern fails every deployment (it did, unnoticed,
// from Phase 6 to the release branch), and nothing else in CI reads this file.
import { describe, expect, it } from 'vitest'
import { getTransformedRoutes } from '@vercel/routing-utils'
import config from '../vercel.json'

const { routes, error } = getTransformedRoutes({ rewrites: config.rewrites, headers: config.headers, redirects: config.redirects })
const headersFor = (path) => Object.assign({}, ...routes.filter((r) => r.headers && new RegExp(r.src).test(path)).map((r) => r.headers))

describe('vercel.json', () => {
  it('is accepted by Vercel', () => {
    expect(error).toBeNull()
  })

  it('serves the app shell for routes and files as themselves', () => {
    const rewrite = routes.find((r) => r.dest === '/index.html')
    expect(new RegExp(rewrite.src).test('/transactions')).toBe(true)
    expect(new RegExp(rewrite.src).test('/reports/42')).toBe(true)
    expect(new RegExp(rewrite.src).test('/assets/index-abc.js')).toBe(false)
    expect(new RegExp(rewrite.src).test('/sw.js')).toBe(false)
  })

  it('caches hashed assets for good and never caches the shell or service worker', () => {
    expect(headersFor('/assets/index-abc.js')['Cache-Control']).toBe('public, max-age=31536000, immutable')
    for (const path of ['/index.html', '/sw.js', '/registerSW.js', '/manifest.webmanifest', '/workbox-cf7f91f8.js']) {
      expect(headersFor(path)['Cache-Control'], path).toBe('no-cache')
    }
    expect(headersFor('/transactions')['Content-Security-Policy']).toMatch(/frame-ancestors 'none'/)
  })
})
