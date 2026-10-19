import { useEffect, useRef, useState } from 'react'
import { motion, useInView, useReducedMotion } from 'motion/react'
import { ArrowDown, EnvelopeSimple } from '@phosphor-icons/react'
import Money from '../../ui/Money'
import Meter from '../../ui/Meter'
import BarChart from '../../ui/BarChart'
import { formatINR } from '../../lib/money'
import { useDemoSnapshot } from './useDemoSnapshot'

const EASE = [0.2, 0.8, 0.2, 1]
const shortDay = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

function Offline() {
  return <p className="text-sm text-muted">The demo account isn't reachable right now. Try the demo in a minute to see live numbers.</p>
}

/** Everything below the story: the live product and the three feature scenes. */
export default function Scenes() {
  return (
    <>
      <LivePreview />
      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-24 grid gap-20">
        <CaptureScene />
        <AskScene />
        <ReportScene />
      </section>
    </>
  )
}

/** The story ends here: the real home screen, rendered from the demo account. */
export function LivePreview() {
  const ref = useRef(null)
  const { data, failed } = useDemoSnapshot(ref)
  const home = data?.home
  const budgets = home ? [...(home.budgets.overall ? [home.budgets.overall] : []), ...home.budgets.categories].slice(0, 4) : []
  return (
    <section ref={ref} aria-labelledby="live" className="border-y border-line bg-surface">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20 grid lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] gap-10 items-start">
        <div>
          <h2 id="live" className="font-display text-display-s text-ink">This is the product, live.</h2>
          <p className="mt-3 text-ink-2 max-w-[36ch]">Rendered right now from the demo account, by the same code that runs your home screen.</p>
        </div>
        <div className="rounded-lg border border-line bg-canvas p-5 sm:p-7 min-h-[22rem]" aria-busy={!home && !failed}>
          {failed ? <Offline /> : !home ? (
            <div className="space-y-4" aria-hidden><div className="skeleton h-4 w-32" /><div className="skeleton h-14 w-56" /><div className="skeleton h-3 w-full" /><div className="skeleton h-3 w-4/5" /></div>
          ) : (
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-5">
                <div>
                  <p className="text-sm text-muted">Safe to spend today</p>
                  {home.safe_to_spend?.amount != null && <Money value={home.safe_to_spend.amount} className="block font-display text-[3.4rem] leading-none tracking-tight text-ink mt-1" />}
                </div>
                <div className="rule pt-4">
                  <p className="text-sm text-ink-2">On pace for <Money value={home.outlook.forecast} className="font-semibold text-ink" /></p>
                  {home.outlook.difference != null && (
                    <p className="text-sm text-muted"><Money value={Math.abs(home.outlook.difference)} /> {Number(home.outlook.difference) > 0 ? 'over' : 'under'} budget</p>
                  )}
                </div>
                {home.upcoming?.length > 0 && (
                  <div className="rule pt-4 space-y-1.5">
                    <p className="eyebrow">Coming up</p>
                    {home.upcoming.slice(0, 3).map((u) => (
                      <p key={u.id} className="flex justify-between text-sm"><span className="text-ink">{u.name}</span><span className="text-muted"><Money value={u.typical_amount} className="text-ink" /> · {shortDay(u.next_expected)}</span></p>
                    ))}
                  </div>
                )}
              </div>
              <div className="space-y-4">
                <p className="eyebrow">Budgets this month</p>
                {budgets.map((b) => <Meter key={b.category} label={b.category} spent={Number(b.spent)} limit={Number(b.limit)} compact />)}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

/** A bank alert email arrives; a transaction appears; the email is gone. */
export function CaptureScene() {
  const ref = useRef(null)
  const reduce = useReducedMotion()
  const seen = useInView(ref, { once: true, amount: 0.5 })
  const on = reduce || seen
  const t = (delay) => (reduce ? { duration: 0 } : { duration: 0.5, delay, ease: EASE })
  return (
    <div ref={ref} className="grid lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] gap-10 items-center">
      <div>
        <h2 className="font-display text-display-s text-ink">Automatic tracking</h2>
        <p className="mt-3 text-ink-2 max-w-[38ch]">Forward your bank's alert emails once. Each one becomes a transaction within seconds, and the email itself is never stored.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center" aria-hidden="true">
        <motion.div initial={false} animate={on ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }} transition={t(0)}
          className="rounded-md border border-line bg-surface p-4 text-[13px] space-y-2 shadow-1">
          <p className="flex items-center gap-2 text-muted"><EnvelopeSimple size={16} />alerts@hdfcbank.net</p>
          <p className="font-medium text-ink">You have done a UPI txn. Check details!</p>
          <p className="text-ink-2 leading-relaxed">
            Dear Customer, <span className={`rounded-[3px] transition-colors duration-slow ${on ? 'bg-accent-tint text-accent-text' : ''}`}>Rs.450.00</span> has been debited from account **1234 to VPA{' '}
            <span className={`rounded-[3px] transition-colors duration-slow ${on ? 'bg-accent-tint text-accent-text' : ''}`}>swiggy@icici</span> on 15-10-26.
          </p>
          <motion.p initial={false} animate={on ? { opacity: 1 } : { opacity: 0 }} transition={t(1.1)} className="text-micro text-danger font-medium">Email discarded after reading</motion.p>
        </motion.div>
        <ArrowDown size={20} className="mx-auto text-faint sm:-rotate-90" />
        <motion.div initial={false} animate={on ? { opacity: 1, x: 0 } : { opacity: 0, x: -12 }} transition={t(0.7)}
          className="rounded-md border border-accent-line bg-surface p-4 flex items-center gap-3 shadow-2">
          <span className="w-9 h-9 rounded-sm bg-sunken flex items-center justify-center font-display font-semibold text-ink-2">S</span>
          <span className="flex-1 min-w-0"><span className="block text-sm font-medium text-ink">Swiggy</span><span className="block text-micro text-muted">Food & Dining · just now</span></span>
          <span className="num font-semibold text-ink">{'−'}₹450</span>
        </motion.div>
      </div>
    </div>
  )
}

function useTyping(text, run) {
  const reduce = useReducedMotion()
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!run || !text || reduce) return undefined
    if (n >= text.length) return undefined
    const id = setTimeout(() => setN((x) => x + 3), 22)
    return () => clearTimeout(id)
  }, [run, text, n, reduce])
  return reduce ? text : text?.slice(0, n)
}

/** A chat exchange that types itself, answered with the demo account's real numbers. */
export function AskScene() {
  const ref = useRef(null)
  const { data, failed } = useDemoSnapshot(ref)
  const seen = useInView(ref, { once: true, amount: 0.5 })
  const food = data?.summary?.categories?.find((c) => c.category === 'Food & Dining')
  const question = 'How much have I spent on food this month?'
  const answer = food ? [
    `${formatINR(food.total)} on Food & Dining so far this month, across ${food.transaction_count} payment${food.transaction_count === 1 ? '' : 's'}.`,
    food.budget_limit ? ` That's ${Math.round(Number(food.total) / Number(food.budget_limit) * 100)}% of your ${formatINR(food.budget_limit)} budget, with ${formatINR(Math.max(Number(food.budget_limit) - Number(food.total), 0))} left.` : '',
  ].join('') : null
  const typedQ = useTyping(question, seen)
  const typedA = useTyping(answer, seen && typedQ === question)
  const top = (data?.summary?.categories || []).slice(0, 4)

  return (
    <div ref={ref} className="grid lg:grid-cols-[minmax(0,7fr)_minmax(0,4fr)] gap-10 items-center">
      <div className="order-2 lg:order-1 rounded-lg border border-line bg-surface p-5 space-y-4 min-h-[16rem]">
        <div className="flex justify-end min-h-[2.5rem]">
          {typedQ && <p className="max-w-[85%] rounded-md rounded-br-sm bg-inverse text-on-inverse px-3 py-2 text-sm">{typedQ}</p>}
        </div>
        {failed ? <Offline /> : (
          <div className="text-sm text-ink leading-relaxed" aria-live="polite">
            <p>{typedA || (seen ? <span className="text-muted">Working it out…</span> : ' ')}</p>
            {typedA === answer && top.length > 0 && (
              <div className="mt-3 rounded-sm border border-line overflow-hidden animate-rise">
                <p className="px-3 pt-2 eyebrow">Spending this month</p>
                <table className="w-full text-[13px]">
                  <tbody>{top.map((c) => <tr key={c.category} className="border-t border-line"><td className="px-3 py-1.5 text-ink-2">{c.category}</td><td className="px-3 py-1.5 text-right num">{formatINR(c.total)}</td></tr>)}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="order-1 lg:order-2">
        <h2 className="font-display text-display-s text-ink">Ask anything</h2>
        <p className="mt-3 text-ink-2 max-w-[36ch]">Every figure in an answer is computed from your transactions, not guessed. Changes like a new budget wait for your tap.</p>
      </div>
    </div>
  )
}

/** The monthly report, as an editorial page. */
export function ReportScene() {
  const ref = useRef(null)
  const { data, failed } = useDemoSnapshot(ref)
  const r = data?.report
  const d = r?.data
  return (
    <div ref={ref} className="grid lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] gap-10 items-start">
      <div>
        <h2 className="font-display text-display-s text-ink">Reports that come to you</h2>
        <p className="mt-3 text-ink-2 max-w-[36ch]">A weekly and a monthly summary arrive by email, readable in a minute. Alerts come the moment something needs you.</p>
      </div>
      <article className="rounded-lg border border-line bg-surface p-6 sm:p-8 min-h-[18rem]">
        {failed ? <Offline /> : !d ? <div className="space-y-3" aria-hidden><div className="skeleton h-8 w-48" /><div className="skeleton h-3 w-full" /><div className="skeleton h-3 w-5/6" /></div> : (
          <>
            <p className="eyebrow">Monthly report</p>
            <h3 className="mt-1 font-display text-3xl text-ink">{d.period.label}</h3>
            <p className="mt-3 text-ink-2 leading-relaxed max-w-[60ch]">{r.narrative.split('\n')[0]}</p>
            <dl className="mt-6 grid grid-cols-3 gap-4 rule pt-4">
              {[['Spent', d.totals.spend], ['Income', d.totals.income], ['Saved', d.totals.saved]].map(([k, v]) => (
                <div key={k}><dt className="text-micro text-muted">{k}</dt><dd><Money value={v} className="font-display text-xl text-ink" /></dd></div>
              ))}
            </dl>
            {d.top_categories?.length > 0 && (
              <div className="mt-6"><BarChart title="Where it went" data={d.top_categories.slice(0, 4).map((c) => ({ label: c.name, value: c.amount }))} /></div>
            )}
          </>
        )}
      </article>
    </div>
  )
}
