import { useLayoutEffect, useRef } from 'react'
import { formatINR, spokenINR } from '../lib/money'

const SIGNS = { out: '−', in: '+', transfer: '↔' }
const TWEEN_MS = 420
const reduceMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/**
 * Every amount in Vaulta.
 *  flow       'out' (money spent), 'in' (received), 'transfer', or omitted for a plain figure.
 *             Direction is shown by a sign and said in words to screen readers, never by colour alone.
 *  hidden     shows ₹•••• (Wrapped share card, privacy)
 *  animate    when the value changes, count to the new value; the first render and every
 *             settled frame show the exact value, so screenshots never catch a wrong number
 */
export default function Money({ value, flow, hidden = false, animate = true, decimals = 'auto', className = '', tone = true, as: Tag = 'span' }) {
  const ref = useRef(null)
  const shown = useRef(Number(value) || 0)
  const raf = useRef(0)
  const exact = Math.abs(Number(value) || 0) * (flow ? 1 : Math.sign(Number(value) || 0) || 1)
  const sign = flow ? SIGNS[flow] ?? '' : ''

  // The visible figure is written only here (before paint), never by React's render, so the
  // tween and React never fight over the same text node.
  useLayoutEffect(() => {
    const el = ref.current
    const from = shown.current
    const to = exact
    cancelAnimationFrame(raf.current)
    if (!el || hidden || !animate || from === to || reduceMotion() || !el.textContent) {
      shown.current = to
      if (el) el.textContent = hidden ? '₹••••' : sign + formatINR(to, { decimals })
      return undefined
    }
    const start = performance.now()
    const step = (now) => {
      const t = Math.min(1, (now - start) / TWEEN_MS)
      const eased = 1 - Math.pow(1 - t, 3)
      const current = t === 1 ? to : from + (to - from) * eased
      el.textContent = sign + formatINR(t === 1 ? to : Math.round(current), { decimals: t === 1 ? decimals : 0 })
      if (t < 1) raf.current = requestAnimationFrame(step)
      else shown.current = to
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [exact, sign, hidden, animate, decimals])

  const toneClass = !tone ? '' : flow === 'in' ? 'text-accent-text' : flow === 'transfer' ? 'text-muted' : ''
  const label = hidden ? 'amount hidden' : spokenINR(exact, flow)
  return (
    <Tag className={`num ${toneClass} ${className}`} data-value={hidden ? undefined : exact}>
      <span ref={ref} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </Tag>
  )
}
