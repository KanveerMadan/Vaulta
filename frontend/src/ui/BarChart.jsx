import { useId, useState } from 'react'
import { formatINR, formatINRCompact } from '../lib/money'

/**
 * Horizontal bars for "spend by category" style data, drawn in SVG on the system's colours.
 * The same data is available as a table (toggle), and the chart itself is described for
 * screen readers. data: [{ label, value }]
 */
export default function BarChart({ data, title, valueLabel = 'Spent' }) {
  const id = useId()
  const [asTable, setAsTable] = useState(false)
  const max = Math.max(...data.map((d) => Number(d.value) || 0), 1)

  return (
    <figure className="space-y-2" aria-labelledby={`${id}-title`}>
      <div className="flex items-center justify-between gap-3">
        <figcaption id={`${id}-title`} className="eyebrow">{title}</figcaption>
        <button onClick={() => setAsTable((v) => !v)} className="text-micro font-medium text-accent-text hover:underline" aria-pressed={asTable}>
          {asTable ? 'Show chart' : 'Show as table'}
        </button>
      </div>
      {asTable ? (
        <table className="w-full text-sm">
          <thead><tr className="text-left text-muted"><th className="font-medium py-1">Category</th><th className="font-medium py-1 text-right">{valueLabel}</th></tr></thead>
          <tbody>{data.map((d) => <tr key={d.label} className="border-t border-line"><td className="py-1.5">{d.label}</td><td className="py-1.5 text-right num">{formatINR(d.value)}</td></tr>)}</tbody>
        </table>
      ) : (
        <ul className="space-y-2" role="img" aria-label={`${title}: ${data.map((d) => `${d.label} ${formatINR(d.value)}`).join(', ')}`}>
          {data.map((d, i) => (
            <li key={d.label} aria-hidden="true" className="grid grid-cols-[minmax(6rem,9rem)_1fr] items-center gap-3 text-sm">
              <span className="text-ink-2 truncate">{d.label}</span>
              <span className="flex items-center gap-2 min-w-0">
                <span className={`h-3.5 rounded-[3px] shrink-0 ${i === 0 ? 'bg-accent' : 'bg-accent-line'}`}
                  style={{ width: `max(3px, calc(${(Number(d.value) / max) * 100}% - 4.5rem))` }} />
                <span className="num font-semibold text-ink shrink-0">{formatINRCompact(d.value)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}
