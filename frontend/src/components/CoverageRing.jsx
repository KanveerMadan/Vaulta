import { Check } from '@phosphor-icons/react'

const PART_LABELS = {
  basics: 'Your banks and income',
  statements: 'Statement history',
  email: 'Bank alerts by email',
  telegram: 'Telegram',
  review: 'First review',
}

/** The coverage meter: a ring that fills as sources connect, with the parts that make it up. */
export function Ring({ percent, size = 168, stroke = 10, label = true }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}
      role="progressbar" aria-label="Tracking coverage" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--sunken))" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--accent))" strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(percent, 100) / 100)} className="coverage-arc" />
      </svg>
      {label && (
        <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden="true">
          <span className="num font-display font-semibold text-ink leading-none" style={{ fontSize: size * 0.24 }}>{percent}<span className="text-muted" style={{ fontSize: size * 0.12 }}>%</span></span>
          <span className="text-micro text-muted mt-1">covered</span>
        </div>
      )}
    </div>
  )
}

export function CoverageParts({ parts, max }) {
  return (
    <ul className="space-y-2.5">
      {Object.entries(max).map(([k, points]) => {
        const got = parts[k] || 0
        const full = got >= points
        return (
          <li key={k} className="flex items-center gap-3 text-sm">
            <span className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 transition-colors duration-slow
              ${full ? 'bg-accent text-on-accent' : got > 0 ? 'bg-accent-tint text-accent-text' : 'border border-line-strong'}`}>
              {got > 0 && <Check size={12} weight="bold" aria-hidden />}
            </span>
            <span className={`flex-1 ${got > 0 ? 'text-ink' : 'text-muted'}`}>{PART_LABELS[k] || k}</span>
            <span className="num text-micro text-muted">{got}/{points}</span>
          </li>
        )
      })}
    </ul>
  )
}
