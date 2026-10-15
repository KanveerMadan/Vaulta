import { useEffect, useRef, useState } from 'react'
import Money from './Money'

/**
 * A budget track: spent against a limit, with 80% and 100% marks. Over the limit is said in
 * words and shown with a hatched fill, not by colour alone. Crossing a mark gives a short pulse.
 */
export default function Meter({ label, spent, limit, compact = false }) {
  const pct = limit > 0 ? (spent / limit) * 100 : 0
  const state = pct > 100 ? 'over' : pct >= 80 ? 'near' : 'ok'
  const prev = useRef(state)
  const [pulse, setPulse] = useState(false)
  useEffect(() => {
    if (prev.current !== state && state !== 'ok') {
      setPulse(true)
      const id = setTimeout(() => setPulse(false), 600)
      prev.current = state
      return () => clearTimeout(id)
    }
    prev.current = state
    return undefined
  }, [state])

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink font-medium truncate">{label}</span>
        <span className="shrink-0 text-ink-2">
          <Money value={spent} /> <span className="text-muted">of</span> <Money value={limit} className="text-muted" />
          {state === 'over' && <span className="ml-2 tag-negative">over by <Money value={spent - limit} tone={false} /></span>}
          {state === 'near' && !compact && <span className="ml-2 tag-warning">{Math.round(pct)}%</span>}
        </span>
      </div>
      <div role="meter" aria-label={`${label} budget`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(Math.round(pct), 100)}
        aria-valuetext={`${Math.round(pct)}% of budget used${state === 'over' ? ', over budget' : ''}`}
        className={`relative h-2 rounded-full bg-sunken overflow-hidden ${pulse ? 'meter-pulse' : ''}`}>
        <div className={`h-full rounded-full transition-[width] duration-slow ease-out ${state === 'over' ? 'meter-over' : state === 'near' ? 'bg-warn' : 'bg-accent'}`}
          style={{ width: `${Math.min(pct, 100)}%` }} />
        <span aria-hidden className="absolute top-0 bottom-0 w-px bg-surface/80" style={{ left: '80%' }} />
      </div>
    </div>
  )
}
