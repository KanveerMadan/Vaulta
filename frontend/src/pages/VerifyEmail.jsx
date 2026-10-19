import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import Wordmark from '../ui/Wordmark'
import { RESEND_AFTER, noteVerificationSent, secondsToWait } from '../lib/verification'

/**
 * "Check your inbox". Shown after an email/password sign-up, and whenever an unverified account tries something
 * that needs a verified address (the API answers 403 email_unverified). The same screen is shown when a sign-up
 * hits an address that already has an account (state.existing), so the page never reveals which addresses exist.
 */
export default function VerifyEmail() {
  const { user, refreshVerified } = useAuthStore()
  const { state } = useLocation()
  const navigate = useNavigate()
  const email = user?.email || state?.email || ''
  const [wait, setWait] = useState(secondsToWait)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (wait <= 0) return undefined
    const t = setTimeout(() => setWait((w) => w - 1), 1000)
    return () => clearTimeout(t)
  }, [wait])

  const resend = async () => {
    setMessage('')
    if (user) {
      try {
        const [{ sendEmailVerification }] = await Promise.all([import('firebase/auth')])
        await sendEmailVerification(user)
      } catch (e) {
        if (e.code === 'auth/too-many-requests') { setMessage('Too many emails sent. Wait a few minutes and try again.'); return }
      }
    }
    noteVerificationSent()
    setWait(RESEND_AFTER)
    setMessage('Sent. It can take a minute to arrive; check your spam folder too.')
  }

  const verified = async () => {
    setMessage('')
    if (!user) { navigate('/login', { state: { email } }); return }
    await user.reload()
    await user.getIdToken(true)                       // a new token carries email_verified for the API
    if (user.emailVerified) {
      refreshVerified()
      navigate(state?.next || '/', { replace: true })
    } else {
      setMessage("We can't see the confirmation yet. Open the link in the email, then try again.")
    }
  }

  return (
    <div className="min-h-dvh bg-canvas flex items-center justify-center p-6">
      <main className="w-full max-w-sm">
        <Wordmark to="/welcome" size="text-2xl" />
        <h1 className="mt-10 font-display text-display-s text-ink">Check your inbox</h1>
        <p className="mt-3 text-ink-2">
          If <span className="font-medium text-ink break-all">{email || 'this address'}</span> is new to Vaulta, we've sent it
          a link to confirm it's yours. Open it, then come back here. If you already have an account with it, log in instead.
        </p>
        <p className="mt-3 text-sm text-muted">Until it's confirmed you can finish setting up, but not import or connect anything.</p>
        <div className="mt-8 space-y-3">
          <button onClick={verified} className="btn-primary w-full h-11">I've confirmed my email</button>
          <button onClick={resend} disabled={wait > 0} className="btn-secondary w-full h-11">
            {wait > 0 ? `Resend in ${wait}s` : 'Resend the email'}
          </button>
          {message && <p role="status" className="text-sm text-ink-2">{message}</p>}
        </div>
        <p className="mt-8 text-sm text-muted">
          {user ? <Link to="/onboarding" className="text-accent-text hover:underline">Continue setting up</Link> : null}
          {user ? ' · ' : null}
          <Link to="/login" className="text-accent-text hover:underline">Log in with another account</Link>
        </p>
      </main>
    </div>
  )
}
