// Draws the Money Wrapped share card on a canvas (1080×1350) and returns a PNG blob.
// Only what the user chose to include: merchant names off by default, amounts optional.
import { formatINR } from '../../lib/money'

const W = 1080, H = 1350

function wrapText(ctx, text, maxWidth) {
  const words = text.split(' ')
  const lines = []
  let line = ''
  for (const w of words) {
    const test = line ? `${line} ${w}` : w
    if (ctx.measureText(test).width > maxWidth && line) { lines.push(line); line = w } else line = test
  }
  if (line) lines.push(line)
  return lines
}

/** rows: [{ label, value }] already filtered for privacy by the caller */
export async function drawShareCard({ year, rows, colors }) {
  await Promise.all([
    document.fonts.load('600 120px "Bricolage Grotesque Variable"'),
    document.fonts.load('500 40px "Geist Variable"'),
  ]).catch(() => {})
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = colors.bg
  ctx.fillRect(0, 0, W, H)

  // wordmark with the ledger rule under the V
  ctx.fillStyle = colors.ink
  ctx.font = '600 52px "Bricolage Grotesque Variable", sans-serif'
  ctx.fillText('Vaulta', 90, 140)
  ctx.fillStyle = colors.accent
  ctx.fillRect(90, 152, 32, 5)

  ctx.fillStyle = colors.muted
  ctx.font = '500 40px "Geist Variable", sans-serif'
  ctx.fillText('Money Wrapped', 90, 300)
  ctx.fillStyle = colors.ink
  ctx.font = '600 240px "Bricolage Grotesque Variable", sans-serif'
  ctx.fillText(String(year), 78, 520)

  let y = 660
  for (const r of rows) {
    ctx.fillStyle = colors.line
    ctx.fillRect(90, y - 56, W - 180, 2)
    ctx.fillStyle = colors.muted
    ctx.font = '500 34px "Geist Variable", sans-serif'
    ctx.fillText(r.label, 90, y)
    ctx.fillStyle = colors.ink
    ctx.font = '600 50px "Bricolage Grotesque Variable", sans-serif'
    const lines = wrapText(ctx, r.value, W - 180)
    lines.slice(0, 1).forEach((l) => ctx.fillText(l, 90, y + 66))
    y += 150
  }
  ctx.fillStyle = colors.muted
  ctx.font = '500 30px "Geist Variable", sans-serif'
  ctx.fillText('Made with Vaulta', 90, H - 90)
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
}

/** The rows on the card, honouring the privacy toggles. */
export function shareRows(d, { names, amounts }) {
  const w = d.wrapped || {}
  const money = (v) => (amounts ? formatINR(v) : '₹ hidden')
  const rows = [
    ['Spent', money(d.totals.spend)],
    d.totals.savings_rate_pct != null && ['Kept of what came in', `${d.totals.savings_rate_pct}%`],
    d.top_categories?.[0] && ['Top category', d.top_categories[0].name],
    w.top_merchant_by_visits && ['Most visited', names ? `${w.top_merchant_by_visits.name}, ${w.top_merchant_by_visits.visits} times` : `One place, ${w.top_merchant_by_visits.visits} times`],
    ['Transactions', `${w.transaction_count ?? d.totals.transactions}`],
  ]
  return rows.filter(Boolean).map(([label, value]) => ({ label, value }))
}
