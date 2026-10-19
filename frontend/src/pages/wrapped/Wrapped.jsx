import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { CaretLeft, CaretRight, DownloadSimple, ShareNetwork, X } from '@phosphor-icons/react'
import { useApi } from '../../lib/format'
import { formatINR } from '../../lib/money'
import { drawShareCard, shareRows } from './shareCard'

/*
 * Money Wrapped: the annual report as a full-screen story. Tap the right side (or →, or swipe
 * left) for the next scene, the left side for the previous; Escape closes. Scenes advance only
 * when the user asks (no timer), so nothing moves on without them. Every figure comes from the
 * annual report (services/reports.py, wrapped section).
 */
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const SURFACES = {
  ink: 'bg-[#0B0E0C] text-[#E9EEEA]',
  green: 'bg-[#17643F] text-[#F4F6F3]',
  paper: 'bg-[#F4F6F3] text-[#101511]',
}

function Rise({ children, delay = 0, className = '' }) {
  const reduce = useReducedMotion()
  return (
    <motion.div className={className} initial={reduce ? false : { opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: reduce ? 0 : delay, ease: [0.2, 0.8, 0.2, 1] }}>
      {children}
    </motion.div>
  )
}

function Rule({ delay = 0, className = 'bg-current' }) {
  const reduce = useReducedMotion()
  return <motion.div aria-hidden className={`h-[3px] origin-left ${className}`} initial={reduce ? false : { scaleX: 0 }} animate={{ scaleX: 1 }}
    transition={{ duration: 0.8, delay: reduce ? 0 : delay, ease: [0.65, 0, 0.35, 1] }} />
}

function buildScenes(d) {
  const w = d.wrapped || {}
  const year = d.period.label
  const scenes = [{
    key: 'open', surface: 'ink', render: () => (
      <div className="h-full flex flex-col justify-end pb-24 px-8">
        <Rise><p className="text-lg opacity-70">Money Wrapped</p></Rise>
        <Rise delay={0.15}><p className="font-display text-[clamp(6rem,30vw,14rem)] leading-[0.85] tracking-[-0.05em]">{year}</p></Rise>
        <div className="mt-6 w-24 text-[#5CCB93]"><Rule delay={0.5} /></div>
        <Rise delay={0.7}><p className="mt-6 text-xl max-w-[22ch]">Your year in money, worked out from every transaction.</p></Rise>
      </div>
    ),
  }, {
    key: 'spent', surface: 'green', render: () => (
      <div className="h-full flex flex-col justify-center px-8">
        <Rise><p className="text-xl opacity-80">This year you spent</p></Rise>
        <Rise delay={0.15}><p className="num font-display text-[clamp(3.2rem,15vw,7rem)] leading-none tracking-tight mt-2">{formatINR(d.totals.spend)}</p></Rise>
        {d.totals.savings_rate_pct != null && (
          <Rise delay={0.45}>
            <p className="mt-10 text-xl">and kept</p>
            <p className="num font-display text-[clamp(4rem,22vw,9rem)] leading-none">{d.totals.savings_rate_pct}%</p>
            <p className="mt-2 text-lg opacity-80">of everything that came in.</p>
          </Rise>
        )}
      </div>
    ),
  }]
  if (w.top_merchant_by_visits) scenes.push({
    key: 'visits', surface: 'paper', render: () => (
      <div className="h-full flex flex-col justify-between py-24 px-8">
        <Rise><p className="text-xl text-[#3C463F]">The place you kept going back to</p></Rise>
        <Rise delay={0.2}><p className="font-display text-[clamp(3rem,16vw,8rem)] leading-[0.9] tracking-tight break-words">{w.top_merchant_by_visits.name}</p></Rise>
        <Rise delay={0.5}>
          <div className="flex items-baseline gap-3 border-t-2 border-[#101511] pt-4">
            <span className="num font-display text-6xl">{w.top_merchant_by_visits.visits}</span><span className="text-xl">visits</span>
          </div>
        </Rise>
      </div>
    ),
  })
  if (w.top_merchant_by_spend) scenes.push({
    key: 'spend', surface: 'ink', render: () => (
      <div className="h-full flex flex-col justify-center px-8">
        <Rise><p className="text-xl opacity-70">Most of your money went to</p></Rise>
        <Rise delay={0.15}><p className="font-display text-[clamp(2.8rem,13vw,6.5rem)] leading-none mt-3 text-[#5CCB93]">{w.top_merchant_by_spend.name}</p></Rise>
        <div className="mt-8 w-full text-[#3A463E]"><Rule delay={0.4} /></div>
        <Rise delay={0.6}><p className="num font-display text-5xl mt-6">{formatINR(w.top_merchant_by_spend.amount)}</p></Rise>
      </div>
    ),
  })
  if (w.most_expensive_month) {
    const [, m] = w.most_expensive_month.month.split('-').map(Number)
    scenes.push({
      key: 'month', surface: 'green', render: () => (
        <div className="h-full flex flex-col justify-end pb-28 px-8">
          <Rise><p className="text-xl opacity-80">Your most expensive month was</p></Rise>
          <Rise delay={0.2}><p className="font-display text-[clamp(3.4rem,16vw,10rem)] leading-[0.85] tracking-tight">{MONTHS[m - 1]}</p></Rise>
          <Rise delay={0.5}><p className="mt-6 text-2xl"><span className="num font-semibold">{formatINR(w.most_expensive_month.amount)}</span> that month.</p></Rise>
        </div>
      ),
    })
  }
  if (Number(w.subscriptions_total) > 0) scenes.push({
    key: 'subs', surface: 'paper', render: () => (
      <div className="h-full flex flex-col justify-center px-8">
        <Rise><p className="text-xl text-[#3C463F]">Subscriptions, all together</p></Rise>
        <Rise delay={0.15}><p className="num font-display text-[clamp(3.5rem,17vw,8rem)] leading-none mt-2">{formatINR(w.subscriptions_total)}</p></Rise>
        <Rise delay={0.45}><p className="mt-6 text-xl max-w-[26ch]">The recurring payments Vaulta found in your statements this year.</p></Rise>
      </div>
    ),
  })
  // only meaningful with last year's data to compare against
  if (w.biggest_category_change && Number(w.biggest_category_change.last_year) > 0) {
    const c = w.biggest_category_change
    const up = Number(c.change) > 0
    scenes.push({
      key: 'change', surface: 'ink', render: () => (
        <div className="h-full flex flex-col justify-center px-8">
          <Rise><p className="text-xl opacity-70">The biggest change from last year</p></Rise>
          <Rise delay={0.15}><p className="font-display text-[clamp(2.8rem,13vw,6rem)] leading-none mt-3">{c.category}</p></Rise>
          <Rise delay={0.45}>
            <p className="mt-8 text-2xl num"><span className="opacity-60">{formatINR(c.last_year)}</span> <span aria-hidden>→</span><span className="sr-only">to</span> <span className="text-[#5CCB93] font-semibold">{formatINR(c.this_year)}</span></p>
            <p className="mt-2 text-lg opacity-80">{up ? 'up' : 'down'} {formatINR(Math.abs(Number(c.change)))}</p>
          </Rise>
        </div>
      ),
    })
  }
  if (d.top_categories?.length) {
    const max = Math.max(...d.top_categories.map((c) => Number(c.amount)))
    scenes.push({
      key: 'categories', surface: 'paper', render: () => (
        <div className="h-full flex flex-col justify-center px-8">
          <Rise><p className="text-xl text-[#3C463F] mb-8">Where it all went</p></Rise>
          <ul className="space-y-5">
            {d.top_categories.slice(0, 5).map((c, i) => (
              <li key={c.name}>
                <Rise delay={0.15 + i * 0.1}>
                  <div className="flex items-baseline justify-between text-lg"><span className="font-medium">{c.name}</span><span className="num">{formatINR(c.amount)}</span></div>
                  <div className="mt-2 h-3 rounded-full bg-[#DDE3DE]"><div className="h-full rounded-full bg-[#17643F]" style={{ width: `${(Number(c.amount) / max) * 100}%` }} /></div>
                </Rise>
              </li>
            ))}
          </ul>
        </div>
      ),
    })
  }
  scenes.push({ key: 'share', surface: 'ink', share: true })
  return scenes
}

const CARD_COLORS = { bg: '#0B0E0C', ink: '#E9EEEA', muted: '#9BA69E', accent: '#5CCB93', line: '#27302A' }

function ShareScene({ d }) {
  const [names, setNames] = useState(false)
  const [amounts, setAmounts] = useState(true)
  const [busy, setBusy] = useState(false)
  const rows = shareRows(d, { names, amounts })
  const year = d.period.label
  const blob = async () => drawShareCard({ year, rows, colors: CARD_COLORS })

  const download = async () => {
    setBusy(true)
    const b = await blob()
    const url = URL.createObjectURL(b)
    const a = Object.assign(document.createElement('a'), { href: url, download: `vaulta-wrapped-${year}.png` })
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    setBusy(false)
  }
  const share = async () => {
    setBusy(true)
    try {
      const file = new File([await blob()], `vaulta-wrapped-${year}.png`, { type: 'image/png' })
      await navigator.share({ files: [file], title: `My ${year} in money` })
    } catch { /* the user closed the share sheet */ }
    setBusy(false)
  }
  const canShare = typeof navigator !== 'undefined' && navigator.canShare?.({ files: [new File([''], 'x.png', { type: 'image/png' })] })

  return (
    <div className="h-full overflow-y-auto px-6 pt-16 pb-28 flex flex-col items-center gap-6" onClick={(e) => e.stopPropagation()}>
      <p className="text-lg opacity-80">Your card to share</p>
      <figure aria-label="Share card preview" className="w-full max-w-[22rem] aspect-[4/5] rounded-md border border-[#27302A] bg-[#0B0E0C] p-6 flex flex-col">
        <p className="font-display text-lg font-semibold">Vaulta</p>
        <p className="mt-6 text-sm text-[#9BA69E]">Money Wrapped</p>
        <p className="font-display text-6xl leading-none">{year}</p>
        <dl className="mt-auto space-y-2.5">
          {rows.map((r) => (
            <div key={r.label} className="border-t border-[#27302A] pt-2">
              <dt className="text-[11px] text-[#9BA69E]">{r.label}</dt>
              <dd className="font-display text-base leading-tight">{r.value}</dd>
            </div>
          ))}
        </dl>
      </figure>
      <fieldset className="w-full max-w-[22rem] space-y-2 text-sm">
        <legend className="sr-only">What the card shows</legend>
        <label className="flex items-center justify-between gap-3 min-h-[44px]">Show merchant names
          <input type="checkbox" checked={names} onChange={(e) => setNames(e.target.checked)} />
        </label>
        <label className="flex items-center justify-between gap-3 min-h-[44px]">Show amounts
          <input type="checkbox" checked={amounts} onChange={(e) => setAmounts(e.target.checked)} />
        </label>
        <p className="text-[12px] text-[#9BA69E]">The card never includes account details. Merchant names stay off unless you turn them on.</p>
      </fieldset>
      <div className="flex gap-3">
        <button onClick={download} disabled={busy} className="btn h-11 px-5 bg-[#5CCB93] text-[#06140D]"><DownloadSimple size={18} aria-hidden />Save image</button>
        {canShare && <button onClick={share} disabled={busy} className="btn h-11 px-5 border border-[#3A463E] text-[#E9EEEA]"><ShareNetwork size={18} aria-hidden />Share</button>}
      </div>
    </div>
  )
}

export default function Wrapped() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data, error } = useApi(`/api/reports/${id}`, id)
  const reduce = useReducedMotion()
  const [i, setI] = useState(0)
  const [dir, setDir] = useState(1)
  const touch = useRef(null)
  const d = data?.data
  const scenes = useMemo(() => (d ? buildScenes(d) : []), [d])
  const go = useCallback((step) => {
    setDir(step)
    setI((n) => Math.max(0, Math.min(scenes.length - 1, n + step)))
  }, [scenes.length])
  const close = useCallback(() => navigate(`/reports/${id}`), [navigate, id])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); go(1) }
      else if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, close])

  if (error) return <div className="min-h-dvh grid place-items-center bg-canvas text-danger p-6">{error}</div>
  if (!d) return <div className="min-h-dvh bg-[#0B0E0C]" aria-busy="true" />
  if (!d.wrapped) return <div className="min-h-dvh grid place-items-center bg-canvas text-ink-2 p-6">Money Wrapped is made from annual reports.</div>
  const scene = scenes[i]

  return (
    <div role="region" aria-roledescription="story" aria-label={`Money Wrapped ${d.period.label}`}
      className={`fixed inset-0 select-none ${SURFACES[scene.surface]} transition-colors duration-slow`}
      onTouchStart={(e) => { touch.current = e.touches[0].clientX }}
      onTouchEnd={(e) => {
        if (touch.current == null) return
        const dx = e.changedTouches[0].clientX - touch.current
        touch.current = null
        if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1)
      }}>
      {/* progress */}
      <div className="absolute top-3 inset-x-3 z-20 flex gap-1.5" aria-hidden>
        {scenes.map((s, n) => <span key={s.key} className={`h-1 flex-1 rounded-full ${n <= i ? 'bg-current' : 'bg-current opacity-25'}`} />)}
      </div>
      <p className="sr-only" aria-live="polite">Scene {i + 1} of {scenes.length}</p>
      <button onClick={close} aria-label="Close Money Wrapped" className="absolute top-7 right-3 z-30 w-11 h-11 rounded-full flex items-center justify-center opacity-80 hover:opacity-100"><X size={22} /></button>

      <AnimatePresence mode="wait" custom={dir} initial={false}>
        <motion.div key={scene.key} className="absolute inset-0 max-w-xl mx-auto"
          initial={reduce ? false : { opacity: 0, x: dir * 40 }} animate={{ opacity: 1, x: 0 }} exit={reduce ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, x: dir * -40 }}
          transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}>
          {scene.share ? <ShareScene d={d} /> : scene.render()}
        </motion.div>
      </AnimatePresence>

      {/* tap zones and buttons: previous on the left, next on the right */}
      {!scene.share && <button aria-label="Next" onClick={() => go(1)} className="absolute right-0 top-16 bottom-0 w-2/3 z-10" />}
      <button aria-label="Previous" onClick={() => go(-1)} disabled={i === 0} className={`absolute left-0 top-16 bottom-0 z-10 ${scene.share ? 'w-10' : 'w-1/3'}`} />
      <div className="absolute bottom-5 inset-x-0 z-20 flex justify-center gap-2 pointer-events-none">
        <button onClick={() => go(-1)} disabled={i === 0} aria-label="Previous scene" className="pointer-events-auto w-11 h-11 rounded-full border border-current flex items-center justify-center opacity-70 hover:opacity-100 disabled:opacity-20"><CaretLeft size={18} /></button>
        <button onClick={() => go(1)} disabled={i === scenes.length - 1} aria-label="Next scene" className="pointer-events-auto w-11 h-11 rounded-full border border-current flex items-center justify-center opacity-70 hover:opacity-100 disabled:opacity-20"><CaretRight size={18} /></button>
      </div>
    </div>
  )
}
