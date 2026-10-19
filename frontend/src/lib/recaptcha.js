// reCAPTCHA v3: a fresh token on the requests bots would abuse, verified by the API with Google (backend
// app/core/recaptcha.py). Firebase App Check isn't used (its reCAPTCHA v3 provider is deprecated). Google's script is
// loaded only when one of those requests is made, never for someone just reading a page; its badge is hidden and the
// disclosure Google asks for is shown where it's used (login, the demo button, /privacy).
//   VITE_RECAPTCHA_SITE_KEY      production: the v3 site key (public)
//   VITE_RECAPTCHA_DEBUG_TOKEN   local and browser-test builds only, sent as-is (the API accepts it outside production)
export const HEADER = 'X-Recaptcha-Token'
const ACTIONS = [[/^\/auth\/demo$/, 'demo'], [/^\/auth\/password-reset-requested$/, 'password_reset'],
  [/^\/api\/import\/batch$/, 'import'], [/^\/api\/chat$/, 'chat']]

/** The action a request needs a token for: its route's, or 'signup' while the signed-in account may not exist yet. */
export function actionFor(path, { signedIn = false, accountKnown = false } = {}) {
  const hit = ACTIONS.find(([re]) => re.test(path))
  if (hit) return hit[1]
  return signedIn && !accountKnown ? 'signup' : null
}

let loading = null
function load(siteKey) {
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = `https://www.google.com/recaptcha/api.js?render=${encodeURIComponent(siteKey)}`
    s.async = true
    s.onload = () => window.grecaptcha.ready(() => resolve(window.grecaptcha))
    s.onerror = () => { loading = null; reject(new Error('reCAPTCHA failed to load')) }
    document.head.appendChild(s)
  })
  return loading
}

/** A token for `action`, or null (no key configured, script blocked): the API then decides (monitor mode lets it through). */
export async function recaptchaToken(action) {
  if (!action) return null
  if (import.meta.env.MODE !== 'production' && import.meta.env.VITE_RECAPTCHA_DEBUG_TOKEN) return import.meta.env.VITE_RECAPTCHA_DEBUG_TOKEN
  const siteKey = import.meta.env.VITE_RECAPTCHA_SITE_KEY
  if (!siteKey) return null
  try {
    const g = await load(siteKey)
    return await g.execute(siteKey, { action })
  } catch {
    return null
  }
}

// Accounts this browser has already seen answered by the API: their requests don't need a 'signup' token
const KNOWN = 'vaulta-accounts-known'
const known = () => { try { return JSON.parse(localStorage.getItem(KNOWN) || '[]') } catch { return [] } }
export const accountKnown = (uid) => known().includes(uid)
export function rememberAccount(uid) {
  if (accountKnown(uid)) return
  try { localStorage.setItem(KNOWN, JSON.stringify([...known(), uid].slice(-5))) } catch { /* storage off: tokens keep being sent, harmlessly */ }
}
