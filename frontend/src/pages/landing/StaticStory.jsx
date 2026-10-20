import { formatINR } from '../../lib/money'
import { CAPTIONS, GROUPS, HOLDER, REMOVED, ROWS } from './story'

const amount = (r) => `${r.flow === 'in' ? '+' : '−'}${formatINR(r.amount)}`

/** The reduced-motion story: the same four states, side by side, nothing moves. */
export default function StaticStory() {
  return (
    <section aria-label="How vaulta.in handles your statement" className="max-w-6xl mx-auto px-4 sm:px-6 pb-20 grid gap-6 md:grid-cols-2">
      <figure className="card p-5 space-y-3">
        <figcaption><h2 className="font-display text-xl text-ink">{CAPTIONS[0].title}</h2><p className="text-sm text-ink-2 mt-1">{CAPTIONS[0].body}</p></figcaption>
        <div className="rounded-sm border border-line p-3 text-[12px] space-y-1">
          <p className="font-semibold text-ink">{HOLDER.bank} · {HOLDER.name} · a/c <span className="num">{HOLDER.account}</span></p>
          {ROWS.slice(0, 4).map((r) => (
            <p key={r.raw} className="flex gap-2"><span className="font-mono text-ink-2 truncate flex-1">{r.raw}</span><span className="num text-muted">{r.balance}</span></p>
          ))}
        </div>
      </figure>
      <figure className="card p-5 space-y-3">
        <figcaption><h2 className="font-display text-xl text-ink">{CAPTIONS[1].title}</h2><p className="text-sm text-ink-2 mt-1">{CAPTIONS[1].body}</p></figcaption>
        <ul className="text-sm space-y-1.5">
          {REMOVED.map((x) => <li key={x} className="flex gap-2 text-ink-2"><span className="text-danger font-semibold" aria-hidden>×</span><span className="line-through decoration-danger">{x}</span></li>)}
        </ul>
      </figure>
      <figure className="card p-5 space-y-3">
        <figcaption><h2 className="font-display text-xl text-ink">{CAPTIONS[2].title}</h2><p className="text-sm text-ink-2 mt-1">{CAPTIONS[2].body}</p></figcaption>
        <ul className="divide-y divide-line text-sm">
          {ROWS.map((r) => <li key={r.raw} className="flex gap-3 py-1.5"><span className="num text-muted w-12">{r.date}</span><span className="flex-1 text-ink truncate">{r.clean}</span><span className="num font-semibold">{amount(r)}</span></li>)}
        </ul>
      </figure>
      <figure className="card p-5 space-y-3">
        <figcaption><h2 className="font-display text-xl text-ink">{CAPTIONS[3].title}</h2><p className="text-sm text-ink-2 mt-1">{CAPTIONS[3].body}</p></figcaption>
        <dl className="text-sm space-y-2">
          {GROUPS.map((g, gi) => (
            <div key={g}>
              <dt className="text-micro font-semibold uppercase tracking-wide text-muted">{g}</dt>
              {ROWS.filter((r) => r.group === gi).map((r) => (
                <dd key={r.raw} className="flex gap-2"><span className="flex-1 text-ink">{r.clean}{r.recurring && <span className="ml-2 tag-positive">{r.recurring}</span>}</span><span className="num">{amount(r)}</span></dd>
              ))}
            </div>
          ))}
        </dl>
      </figure>
    </section>
  )
}
