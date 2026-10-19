// Cold starts (lib/wake.js): wait for a sleeping API, then resend only what is safe to send twice.
import { describe, expect, it } from 'vitest'
import { canResend, isColdError, useWake, wake, WAKE_DEADLINE_MS } from './wake.js'

function clock() {
  let t = 0
  return { now: () => t, pause: async (ms) => { t += ms } }
}
const answers = (...oks) => { let i = 0; return async () => { const ok = oks[Math.min(i++, oks.length - 1)]; if (ok === 'throw') throw new TypeError('fetch failed'); return { ok } } }

describe('wake', () => {
  it('treats no answer and 502/503/504 as asleep; not real answers, cancels or being offline', () => {
    expect(isColdError({ code: 'ERR_NETWORK' }, true)).toBe(true)
    expect(isColdError({ code: 'ECONNABORTED' }, true)).toBe(true)
    for (const status of [502, 503, 504]) expect(isColdError({ response: { status } }, true)).toBe(true)
    for (const status of [400, 401, 403, 404, 500]) expect(isColdError({ response: { status } }, true)).toBe(false)
    expect(isColdError({ code: 'ERR_CANCELED' }, true)).toBe(false)
    expect(isColdError({ code: 'ERR_NETWORK' }, false)).toBe(false)
  })

  it('resends reads, and writes only when they never reached the server', () => {
    expect(canResend({ method: 'get' }, { code: 'ECONNABORTED' })).toBe(true)
    expect(canResend({ method: 'post' }, { code: 'ERR_NETWORK' })).toBe(true)
    expect(canResend({ method: 'post' }, { code: 'ECONNABORTED' })).toBe(false)       // timed out: it may have run
    expect(canResend({ method: 'post' }, { response: { status: 503 } })).toBe(false)
  })

  it('an API that is already up shows nothing', async () => {
    const seen = []; const off = useWake.subscribe((s) => seen.push(s.state))
    expect(await wake('', { fetchFn: answers(true), ...clock() })).toBe(true)
    off()
    expect(seen.filter((s) => s !== 'awake')).toEqual([])
  })

  it('shows "waking" until /health answers, then "awake"', async () => {
    const seen = []; const off = useWake.subscribe((s) => seen.push(s.state))
    expect(await wake('', { fetchFn: answers('throw', false, 'throw', true), ...clock() })).toBe(true)
    off()
    expect(seen).toContain('waking')
    expect(useWake.getState().state).toBe('awake')
  })

  it('gives up after two minutes with "slow", polling with backoff', async () => {
    let calls = 0
    const c = clock()
    const fetchFn = async () => { calls++; throw new TypeError('fetch failed') }
    expect(await wake('', { fetchFn, ...c })).toBe(false)
    expect(useWake.getState().state).toBe('slow')
    expect(c.now()).toBeGreaterThanOrEqual(WAKE_DEADLINE_MS)
    expect(calls).toBeLessThan(25)                        // 1s, 2s, 4s, then every 8s
  })

  it('callers waiting at the same time share one wait', async () => {
    let calls = 0
    const fetchFn = async () => { calls++; return { ok: true } }
    await Promise.all([wake('', { fetchFn, ...clock() }), wake('', { fetchFn, ...clock() })])
    expect(calls).toBe(1)
  })
})
