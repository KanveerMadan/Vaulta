// The API runs on a free Render instance that sleeps after 15 idle minutes and takes up to about a minute to start
// (go-live: no keep-awake). A request that gets no answer, or 502/503/504 while the instance starts, puts the app in
// "waking": WakeNotice says so, /health is polled with backoff for up to two minutes, then the request is sent
// again: GETs always, anything else only if it never reached the server (so nothing is done twice) or the caller
// marked it `idempotent` (the server makes sending it twice harmless, like import batches). After two
// minutes the notice turns into "taking longer than usual" with Try again, and the request fails as before.
import { create } from 'zustand'

export const useWake = create(() => ({ state: 'awake' }))   // 'awake' | 'waking' | 'slow'

export const WAKE_DEADLINE_MS = 120_000
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** True when the error looks like a sleeping API rather than a real answer. */
export function isColdError(err, online = typeof navigator === 'undefined' || navigator.onLine) {
  if (!online || err?.code === 'ERR_CANCELED') return false
  return !err?.response || [502, 503, 504].includes(err.response.status)
}

/** Safe to send again after waking: reads and idempotent writes always; other writes only when they never reached the server. */
export function canResend(config, err) {
  return (config.method || 'get').toLowerCase() === 'get' || config.idempotent === true ||
    (!err.response && err.code === 'ERR_NETWORK')
}

let waking = null
/** Poll `${base}/health` until it answers (true) or the deadline passes (false). Concurrent callers share one wait. */
export function wake(base, { fetchFn = fetch, now = Date.now, pause = sleep } = {}) {
  waking ??= (async () => {
    const start = now()
    for (let delay = 1000; ; delay = Math.min(delay * 2, 8000)) {
      try {
        const res = await fetchFn(`${base}/health`, { cache: 'no-store', signal: AbortSignal.timeout(15_000) })
        if (res.ok) { useWake.setState({ state: 'awake' }); return true }
      } catch { /* still asleep */ }
      // only now say so: an API that's up and answered 503 on purpose shows nothing
      useWake.setState({ state: 'waking' })
      if (now() - start >= WAKE_DEADLINE_MS) { useWake.setState({ state: 'slow' }); return false }
      await pause(delay)
    }
  })().finally(() => { waking = null })
  return waking
}

/** Start the API early, silently (the landing page's demo button is then quicker). */
export function warmUp(base) {
  fetch(`${base}/health`, { cache: 'no-store' }).catch(() => {})
}
