import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// WCAG 2.2 AA for every text colour on every surface it's used on, in both themes.
const css = readFileSync(fileURLToPath(new URL('./tokens.css', import.meta.url)), 'utf8')

function block(selector) {
  const start = css.indexOf(selector)
  const body = css.slice(css.indexOf('{', start) + 1, css.indexOf('}', start))
  return Object.fromEntries([...body.matchAll(/--([a-z0-9-]+):\s*(\d+)\s+(\d+)\s+(\d+)/g)].map((m) => [m[1], [m[2], m[3], m[4]].map(Number)]))
}
const lum = ([r, g, b]) => [r, g, b].map((c) => c / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  .reduce((acc, c, i) => acc + c * [0.2126, 0.7152, 0.0722][i], 0)
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }

const light = block(':root {')
const dark = { ...light, ...block(':root[data-theme="dark"] {') }
const TEXT = ['ink', 'ink-2', 'muted', 'accent-text', 'warn', 'danger']
const SURFACES = ['canvas', 'surface', 'sunken', 'accent-tint']

describe.each([['light', light], ['dark', dark]])('%s theme', (_, t) => {
  it.each(TEXT.flatMap((fg) => SURFACES.map((bg) => [fg, bg])))('%s on %s meets 4.5:1', (fg, bg) => {
    expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5)
  })
  it('text on the accent and on inverse meets 4.5:1', () => {
    expect(ratio(t['on-accent'], t.accent)).toBeGreaterThanOrEqual(4.5)
    expect(ratio(t['on-inverse'], t.inverse)).toBeGreaterThanOrEqual(4.5)
  })
  it('warn and danger text on their own tints meets 4.5:1', () => {
    expect(ratio(t.warn, t['warn-tint'])).toBeGreaterThanOrEqual(4.5)
    expect(ratio(t.danger, t['danger-tint'])).toBeGreaterThanOrEqual(4.5)
  })
  it('decorative lines and faint marks are at least 3:1 where they carry meaning', () => {
    expect(ratio(t.faint, t.surface)).toBeGreaterThanOrEqual(3)
    expect(ratio(t.accent, t.surface)).toBeGreaterThanOrEqual(3)   // meter fills, focus ring
  })
})

it('the system-dark block matches the explicit dark theme', () => {
  const media = css.slice(css.indexOf(':root:not([data-theme="light"])'))
  for (const [k, v] of Object.entries(block(':root[data-theme="dark"] {'))) {
    expect(media.includes(`--${k}: ${v.join(' ')};`), k).toBe(true)
  }
})
