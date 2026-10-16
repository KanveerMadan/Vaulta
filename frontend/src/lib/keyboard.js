// On-screen keyboards. iOS Safari doesn't resize the page when the keyboard opens, so a field low on the screen
// (quick add, the chat box, the login form on a short phone) can end up under it. On touch screens, once the
// keyboard has had time to open, the focused field is scrolled to the middle of what's still visible.
// Applies to any touch browser; Android Chrome also shrinks the visual viewport, so the scroll lands in what's visible.
export const KEYBOARD_DELAY = 300

export function keepFocusedFieldVisible(win = window) {
  if (!win.matchMedia?.('(pointer: coarse)').matches) return () => {}
  const reduce = win.matchMedia('(prefers-reduced-motion: reduce)').matches
  const onFocus = (e) => {
    const el = e.target
    if (!el?.matches?.('input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea, select, [contenteditable="true"]')) return
    win.setTimeout(() => {
      if (win.document.activeElement === el) el.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' })
    }, KEYBOARD_DELAY)
  }
  win.addEventListener('focusin', onFocus)
  return () => win.removeEventListener('focusin', onFocus)
}
