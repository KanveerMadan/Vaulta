// Light / dark / system. The choice lives in localStorage (a per-device convenience);
// index.html applies it before first paint.
const KEY = 'vaulta-theme'

export function getThemeChoice() {
  try { return localStorage.getItem(KEY) || 'system' } catch { return 'system' }
}

export function setThemeChoice(choice) {
  const root = document.documentElement
  if (choice === 'light' || choice === 'dark') root.dataset.theme = choice
  else delete root.dataset.theme
  try {
    if (choice === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, choice)
  } catch { /* private mode: applies for this page only */ }
}

/** The theme actually showing right now. */
export function resolvedTheme() {
  const set = document.documentElement.dataset.theme
  if (set) return set
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
