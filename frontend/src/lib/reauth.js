// "Sign in again" for sensitive actions. The API answers 403 {code: reauth_required} when the last real sign-in is
// over 5 minutes old (backend app/core/auth.py get_recent_user); lib/api.js calls requestReauth(), the
// ReauthDialog mounted in App asks for the password or a Google sign-in, and the request is retried once.
let pending = null

/** Resolves when the user has signed in again; rejects if they cancel. One prompt at a time. */
export function requestReauth() {
  if (!pending) {
    pending = new Promise((resolve, reject) => {
      window.dispatchEvent(new CustomEvent('vaulta:reauth', { detail: { resolve, reject } }))
    }).finally(() => { pending = null })
  }
  return pending
}

// The server's window (RECENT_LOGIN_SECONDS); the browser tests' build uses a shorter one
const RECENT_SECONDS = Number(import.meta.env.VITE_RECENT_LOGIN_SECONDS) || 300
const MARGIN = 15   // ask a little early rather than send a request the server will refuse

/** Before a sensitive request: if the last real sign-in is too old, ask to sign in again first. */
export async function ensureRecentLogin(user) {
  const { authTime } = await user.getIdTokenResult()
  if ((Date.now() - new Date(authTime).getTime()) / 1000 > RECENT_SECONDS - MARGIN) await requestReauth()
}
