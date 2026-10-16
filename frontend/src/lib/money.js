// Indian-grouped rupee formatting (₹1,20,000) used for every amount in the app.

const whole = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const paise = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** ₹1,20,000 · ₹1,234.50 (paise only when there are any) · −₹500 when signed and negative. */
export function formatINR(value, { decimals = 'auto' } = {}) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '₹0'
  const abs = Math.abs(n)
  const rounded = Math.round(abs * 100) / 100
  const usePaise = decimals === 2 || (decimals === 'auto' && rounded % 1 !== 0)   // decimals: 'auto' | 0 | 2
  const body = usePaise ? paise.format(rounded) : whole.format(Math.round(rounded))
  return `${n < 0 ? '−' : ''}₹${body}`
}

/** Short form for chart axes and dense labels: ₹950, ₹12k, ₹1.2L, ₹3.4Cr. */
export function formatINRCompact(value) {
  const n = Math.abs(Number(value) || 0)
  const sign = Number(value) < 0 ? '−' : ''
  const trim = (x) => (Math.round(x * 10) / 10).toString().replace(/\.0$/, '')
  if (n >= 1e7) return `${sign}₹${trim(n / 1e7)}Cr`
  if (n >= 1e5) return `${sign}₹${trim(n / 1e5)}L`
  if (n >= 1e3) return `${sign}₹${trim(n / 1e3)}k`
  return `${sign}₹${Math.round(n)}`
}

/** Words a screen reader says for a figure: "₹1,200 received". */
export function spokenINR(value, flow) {
  const base = formatINR(Math.abs(Number(value) || 0)).replace('−', 'minus ')
  if (flow === 'in') return `${base} received`
  if (flow === 'out') return `${base} spent`
  if (flow === 'transfer') return `${base} moved between your accounts`
  return Number(value) < 0 ? `minus ${base}` : base
}
