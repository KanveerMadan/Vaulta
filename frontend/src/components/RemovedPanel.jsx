import { NEVER_READ, REMOVED_LABELS } from '../import/pii'

// Split a description into words and separators, so we can show which words were taken out.
const tokens = (s) => s.split(/([\s/\-|:]+)/).filter(Boolean)

/** Words of `raw` that aren't in `clean` are struck out; masked words in `clean` are highlighted. */
function Diff({ raw, clean }) {
  const kept = new Map()
  for (const t of tokens(clean)) kept.set(t, (kept.get(t) || 0) + 1)
  let k = 0
  return (
    <div className="space-y-1.5">
      <p className="font-mono text-[12px] leading-relaxed text-ink-2 break-all">
        {tokens(raw).map((t, i) => {
          if (/^[\s/\-|:]+$/.test(t)) return <span key={i}>{t}</span>
          if (kept.get(t)) { kept.set(t, kept.get(t) - 1); return <span key={i}>{t}</span> }
          return <span key={i} className="removed-token" style={{ '--i': k++ }}>{t}</span>
        })}
      </p>
      <p className="font-mono text-[12px] leading-relaxed text-ink break-all">
        <span className="text-muted" aria-hidden>→ </span>
        {tokens(clean).map((t, i) => (/\*\*\*|^SELF$|^X+$|•/.test(t)
          ? <mark key={i} className="bg-accent-tint text-accent-text rounded-[3px] px-0.5">{t}</mark>
          : <span key={i}>{t}</span>))}
      </p>
    </div>
  )
}

/**
 * The trust moment of an import: everything taken out of the statement before anything is sent,
 * shown on the user's own rows. `rawRows` stay in this component's memory and are never sent.
 */
export default function RemovedPanel({ rawRows, cleanRows, removed }) {
  const examples = rawRows
    .map((r, i) => ({ raw: r.description_raw, clean: cleanRows[i].description_raw }))
    .filter((x) => x.raw !== x.clean)
    .slice(0, 3)
  const counts = Object.entries(removed).filter(([, n]) => n > 0)

  return (
    <section aria-labelledby="removed-title" className="rounded-md border border-line bg-sunken/60 p-4 space-y-4">
      <div>
        <h3 id="removed-title" className="text-sm font-semibold text-ink">Removed on this device, before anything is sent</h3>
        <p className="text-micro text-muted mt-0.5">This happened in your browser. Only the cleaned rows below can be imported.</p>
      </div>
      <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5">
        {NEVER_READ.map((label, i) => (
          <li key={label} className="text-sm text-ink-2 flex items-start gap-2">
            <span aria-hidden className="mt-[3px] text-danger font-semibold leading-none">×</span>
            <span className="never-read" style={{ '--i': i }}><span className="sr-only">Not read: </span>{label}</span>
          </li>
        ))}
      </ul>
      {counts.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Cleaned in your rows">
          {counts.map(([k, n]) => (
            <li key={k} className="text-micro font-medium rounded-sm bg-surface border border-line px-2 py-1 text-ink-2">
              {REMOVED_LABELS[k] || k}: <span className="num font-semibold text-ink">{n}</span>
            </li>
          ))}
        </ul>
      )}
      {examples.length > 0 && (
        <div className="space-y-3 rule pt-3">
          <p className="text-micro font-semibold text-muted">From your file</p>
          {examples.map((x, i) => <Diff key={i} raw={x.raw} clean={x.clean} />)}
        </div>
      )}
    </section>
  )
}
