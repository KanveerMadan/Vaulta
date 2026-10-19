import { useWake, wake } from '../lib/wake'
import api from '../lib/api'

/** Mounted once (App): shown while the API wakes from sleep (lib/wake.js). */
export default function WakeNotice() {
  const state = useWake((s) => s.state)
  if (state === 'awake') return null
  const slow = state === 'slow'
  return (
    <div role="status" aria-live="polite" className="fixed top-3 left-1/2 -translate-x-1/2 z-[80] w-[min(26rem,calc(100vw-2rem))]
      rounded-md border border-line bg-surface shadow-3 px-4 py-3.5 animate-rise">
      <p className="font-display text-base font-semibold text-ink">{slow ? 'Vaulta is taking longer than usual' : 'Waking up Vaulta…'}</p>
      <p className="mt-1 text-sm text-ink-2">
        {slow
          ? 'The server still isn’t answering. Check your connection, or try again in a minute.'
          : 'The server rests when no one is using it and is starting now. This can take up to a minute; your page will load on its own.'}
      </p>
      {slow
        ? <button className="btn-primary h-9 px-3 mt-3 text-[13px]" onClick={() => wake(api.defaults.baseURL).then((up) => up && window.location.reload())}>Try again</button>
        : <span aria-hidden className="mt-3 block h-px w-full bg-line overflow-hidden"><span className="block h-px w-1/3 bg-accent animate-pulse" /></span>}
    </div>
  )
}
