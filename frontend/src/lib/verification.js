// When the last verification email went out, so "Resend" waits RESEND_AFTER seconds across redirects and reloads
export const RESEND_AFTER = 60   // seconds between resends (Firebase also rate limits: auth/too-many-requests)
const SENT_KEY = 'vaulta-verify-sent'

/** Remember when a verification email went out (survives redirects and reloads in this tab). */
export function noteVerificationSent() {
  try { sessionStorage.setItem(SENT_KEY, String(Date.now())) } catch { /* private mode: no cooldown memory */ }
}

export function secondsToWait() {
  let sent = 0
  try { sent = Number(sessionStorage.getItem(SENT_KEY)) || 0 } catch { /* private mode */ }
  return Math.max(0, Math.ceil(RESEND_AFTER - (Date.now() - sent) / 1000))
}

