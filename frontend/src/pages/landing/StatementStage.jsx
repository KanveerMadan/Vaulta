import { useLayoutEffect, useRef, useState } from 'react'
import { motion, useTransform } from 'motion/react'
import { formatINR } from '../../lib/money'
import { GROUPS, HOLDER, ROWS } from './story'

/*
 * The statement being taken apart, driven by `progress` (0..1, a motion value from the page scroll).
 * Phases:
 *   0.0-0.2  the statement as the bank sent it
 *   0.2-0.4  personal details are struck through and removed
 *   0.4-0.6  the statement frame falls away; clean rows cross to Vaulta
 *   0.6-0.8  rows sort into categories
 *   0.8-1.0  recurring payments are marked; the month's forecast draws
 * (one step per caption on the page)
 * Laid out on a fixed logical canvas and scaled to fit, so the choreography is the same at any size.
 * Only transform and opacity animate.
 */
const B = [0.2, 0.4, 0.6, 0.8, 1]
const LAYOUTS = {
  wide: { w: 560, h: 620, pad: 24, header: 104, row: 50, groupHead: 26, gap: 8 },
  compact: { w: 340, h: 470, pad: 12, header: 100, row: 40, groupHead: 20, gap: 4 },
}

function geometry(L) {
  const statement = ROWS.map((_, i) => L.pad + L.header + i * L.row)
  const clean = ROWS.map((_, i) => L.pad + 48 + i * L.row)
  const groupY = []
  const grouped = []
  let y = L.pad + 48
  GROUPS.forEach((_, g) => {
    groupY[g] = y
    y += L.groupHead
    ROWS.forEach((r, i) => { if (r.group === g) { grouped[i] = y; y += L.row } })
    y += L.gap
  })
  return { statement, clean, grouped, groupY, forecastY: y + 4 }
}

const masked = (raw) => raw
  .replace(/\d{4}X{6}\d{4}/g, '••••')
  .replace(/-(\d{12,})/g, '-••••')
  .replace(/([a-z])[a-z.]*@(ok[a-z]+)/g, '$1***@$2')

function Row({ row, i, L, G, progress }) {
  const y = useTransform(progress, [0, B[1], B[2], B[2] + 0.02, B[3], 1],
    [G.statement[i], G.statement[i], G.clean[i], G.clean[i], G.grouped[i], G.grouped[i]])
  const x = useTransform(progress, [B[1], (B[1] + B[2]) / 2, B[2]], [0, 10, 0])
  // one text at a time: raw → masked → clean, never two overlapping
  const rawOpacity = useTransform(progress, [B[0] + 0.06, B[0] + 0.09], [1, 0])
  const maskedOpacity = useTransform(progress, [B[0] + 0.09, B[0] + 0.12, B[1] + 0.04, B[1] + 0.07], [0, 1, 1, 0])
  const cleanOpacity = useTransform(progress, [B[1] + 0.07, B[1] + 0.1], [0, 1])
  const balanceOpacity = useTransform(progress, [B[0] + 0.1, B[0] + 0.16], [1, 0])
  const recurringOpacity = useTransform(progress, [B[3] + 0.02 + i * 0.01, B[3] + 0.08 + i * 0.01], [0, 1])
  const rowBg = useTransform(progress, [B[1], B[2]], [0, 1])
  const compactLayout = L === LAYOUTS.compact
  // once the balance column has gone, the amount moves over to the row's edge
  const amountX = useTransform(progress, [B[1], B[1] + 0.08], [0, compactLayout ? 0 : 96])
  const compact = L === LAYOUTS.compact
  const amount = `${row.flow === 'in' ? '+' : '−'}${formatINR(row.amount)}`

  return (
    <motion.div className="absolute left-0 right-0 flex items-center" style={{ y, x, height: L.row, paddingLeft: L.pad, paddingRight: L.pad }}>
      <motion.div className="absolute inset-y-1 rounded-sm bg-surface border border-line" style={{ left: L.pad - 8, right: L.pad - 8, opacity: rowBg }} />
      <span className="relative w-14 shrink-0 text-[12px] text-muted num">{row.date}</span>
      <span className="relative flex-1 min-w-0 h-full">
        <motion.span className="absolute inset-0 flex items-center font-mono text-[11.5px] text-ink-2 truncate" style={{ opacity: rawOpacity }}>{row.raw}</motion.span>
        <motion.span className="absolute inset-0 flex items-center font-mono text-[11.5px] text-ink-2 truncate" style={{ opacity: maskedOpacity }}>{masked(row.raw)}</motion.span>
        <motion.span className="absolute inset-0 flex items-center gap-2 text-[13.5px] font-medium text-ink truncate" style={{ opacity: cleanOpacity }}>
          {row.clean}
          {row.recurring && (
            <motion.span className="shrink-0 text-[11px] font-semibold text-accent-text bg-accent-tint rounded-[4px] px-1.5 py-0.5" style={{ opacity: recurringOpacity }}>
              {row.recurring}
            </motion.span>
          )}
        </motion.span>
      </span>
      <motion.span className={`relative shrink-0 text-right num text-[13px] font-semibold ${row.flow === 'in' ? 'text-accent-text' : 'text-ink'} ${compact ? 'w-20' : 'w-24'}`} style={{ x: amountX }}>{amount}</motion.span>
      {!compact && (
        <motion.span className="relative w-24 shrink-0 text-right num text-[12px] text-muted" style={{ opacity: balanceOpacity }}>{row.balance}</motion.span>
      )}
    </motion.div>
  )
}

function Strike({ progress, at, children, className = '' }) {
  const line = useTransform(progress, [B[0] + at, B[0] + at + 0.06], [0, 1])
  const fade = useTransform(progress, [B[0] + at + 0.07, B[0] + at + 0.12], [1, 0])
  return (
    <motion.span className={`relative inline-block ${className}`} style={{ opacity: fade }}>
      {children}
      <motion.span aria-hidden className="absolute left-0 right-0 top-1/2 h-[2px] bg-danger origin-left" style={{ scaleX: line }} />
    </motion.span>
  )
}

function GroupHead({ label, y, progress, delay, pad }) {
  // appears as the rows settle under it, never while rows are still passing through
  const opacity = useTransform(progress, [B[3] - 0.04 + delay, B[3] + delay], [0, 1])
  return (
    <motion.div className="absolute flex items-end text-[11px] font-semibold tracking-wide uppercase text-muted" style={{ y, opacity, height: 22, left: pad, right: pad }}>
      {label}
    </motion.div>
  )
}

export default function StatementStage({ progress }) {
  const box = useRef(null)
  const [fit, setFit] = useState({ layout: LAYOUTS.wide, scale: 1 })
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return undefined
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect
      const layout = width < 500 ? LAYOUTS.compact : LAYOUTS.wide
      setFit({ layout, scale: Math.min(width / layout.w, height / layout.h, 1.15) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const L = fit.layout
  const G = geometry(L)

  const frame = useTransform(progress, [B[1] + 0.02, B[1] + 0.1], [1, 0])
  const headerFade = useTransform(progress, [B[1], B[1] + 0.06], [1, 0])
  const onPhone = useTransform(progress, [B[1] + 0.02, B[1] + 0.08], [1, 0])
  const inVaulta = useTransform(progress, [B[1] + 0.06, B[1] + 0.12], [0, 1])
  const scan = useTransform(progress, [B[1] + 0.02, B[2]], [G.statement[0], G.clean[ROWS.length - 1] + L.row])
  const scanOpacity = useTransform(progress, [B[1] + 0.02, B[1] + 0.05, B[2] - 0.03, B[2]], [0, 1, 1, 0])
  const forecast = useTransform(progress, [B[3] + 0.06, 0.97], [0, 1])
  const forecastIn = useTransform(progress, [B[3] + 0.03, B[3] + 0.08], [0, 1])

  return (
    <div ref={box} className="relative w-full h-full flex items-center justify-center" aria-hidden="true">
      <div className="relative" style={{ width: L.w, height: L.h, transform: `scale(${fit.scale})`, transformOrigin: 'center' }}>
        {/* the statement as it arrives */}
        <motion.div className="absolute inset-x-0 top-0 rounded-md border border-line-strong bg-surface shadow-2"
          style={{ opacity: frame, height: G.statement[ROWS.length - 1] + L.row + L.pad }} />
        <motion.div className="absolute" style={{ left: L.pad, right: L.pad, top: L.pad, opacity: headerFade }}>
          <div className="flex items-baseline justify-between">
            <p className="font-display text-[17px] font-semibold text-ink">{HOLDER.bank}</p>
            <p className="text-[11px] text-muted">Statement of account · {HOLDER.period}</p>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[12px] text-ink-2">
            <span>Account holder <Strike progress={progress} at={0} className="font-semibold text-ink">{HOLDER.name}</Strike></span>
            <span>Account no. <Strike progress={progress} at={0.03} className="num font-semibold text-ink">{HOLDER.account}</Strike></span>
            <span>IFSC <Strike progress={progress} at={0.05} className="num text-ink">{HOLDER.ifsc}</Strike></span>
            <span className="text-right">Balance <Strike progress={progress} at={0.07} className="num text-ink">₹86,701.50</Strike></span>
          </div>
        </motion.div>

        {/* where we are */}
        <div className="absolute flex gap-2" style={{ left: L.pad, top: L.pad + 4 }}>
          <motion.span className="absolute whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide text-muted" style={{ opacity: inVaulta, y: -2 }}>
            In vaulta.in · {ROWS.length} rows, nothing else
          </motion.span>
        </div>
        <motion.span className="absolute right-4 -top-7 text-[11px] font-semibold uppercase tracking-wide text-muted" style={{ opacity: onPhone }}>
          On your phone
        </motion.span>

        {GROUPS.map((g, gi) => <GroupHead key={g} label={g} y={G.groupY[gi]} progress={progress} delay={gi * 0.006} pad={L.pad} />)}
        {ROWS.map((row, i) => <Row key={i} row={row} i={i} L={L} G={G} progress={progress} />)}

        {/* the line every row has to cross */}
        <motion.div className="absolute left-0 right-0 h-px bg-accent" style={{ y: scan, opacity: scanOpacity }} />

        {/* the month's forecast */}
        <motion.div className="absolute" style={{ left: L.pad, right: L.pad, top: G.forecastY, opacity: forecastIn }}>
          <div className="flex items-baseline justify-between text-[12px]">
            <span className="font-semibold text-ink">On pace for ₹34,200 this month</span>
            <span className="text-muted">budget ₹40,000</span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-sunken overflow-hidden">
            <motion.div className="h-full w-[85.5%] rounded-full bg-accent origin-left" style={{ scaleX: forecast }} />
          </div>
        </motion.div>
      </div>
    </div>
  )
}
