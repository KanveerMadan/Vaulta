import { describe, expect, it, vi } from 'vitest'
import { KEYBOARD_DELAY, keepFocusedFieldVisible } from './keyboard'

function fakeWindow({ coarse }) {
  const listeners = {}
  const doc = { activeElement: null }
  return {
    document: doc,
    matchMedia: (q) => ({ matches: q.includes('coarse') ? coarse : false }),
    addEventListener: (type, fn) => { listeners[type] = fn },
    removeEventListener: (type) => { delete listeners[type] },
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    focus(el) { doc.activeElement = el; listeners.focusin?.({ target: el }) },
    listeners,
  }
}
const field = (selector = 'input') => ({ matches: (s) => s.includes(selector), scrollIntoView: vi.fn() })

describe('keepFocusedFieldVisible', () => {
  it('scrolls a focused field into view after the keyboard opens, on touch screens', () => {
    vi.useFakeTimers()
    const win = fakeWindow({ coarse: true })
    keepFocusedFieldVisible(win)
    const input = field()
    win.focus(input)
    expect(input.scrollIntoView).not.toHaveBeenCalled()
    vi.advanceTimersByTime(KEYBOARD_DELAY)
    expect(input.scrollIntoView).toHaveBeenCalledWith({ block: 'center', behavior: 'smooth' })
    vi.useRealTimers()
  })

  it('does nothing with a mouse, or once focus has moved on', () => {
    vi.useFakeTimers()
    const mouse = fakeWindow({ coarse: false })
    keepFocusedFieldVisible(mouse)
    expect(mouse.listeners.focusin).toBeUndefined()
    const win = fakeWindow({ coarse: true })
    keepFocusedFieldVisible(win)
    const a = field(); const b = { matches: () => false, scrollIntoView: vi.fn() }
    win.focus(a); win.document.activeElement = b
    vi.advanceTimersByTime(KEYBOARD_DELAY)
    expect(a.scrollIntoView).not.toHaveBeenCalled()
    vi.useRealTimers()
  })
})
