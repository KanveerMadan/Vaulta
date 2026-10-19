import { useState } from 'react'
import { signInWithEmailAndPassword, createUserWithEmailAndPassword, sendEmailVerification, sendPasswordResetEmail, GoogleAuthProvider, linkWithCredential } from 'firebase/auth'
import { auth, signInWithGoogle } from '../lib/firebase'
import { useAuthStore } from '../store/authStore'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Wordmark from '../ui/Wordmark'
import { MIN_PASSWORD, noteVerificationSent } from '../lib/verification'
import api from '../lib/api'
import RecaptchaNotice from '../ui/RecaptchaNotice'

const RESET_SENT = "If there's an account for that email, we've sent it a link to reset the password. It can take a minute; check spam too."

// Wrong password and unknown email read the same, so the form never reveals which addresses have accounts
const ERROR_MAP = {
  'auth/invalid-credential':    'Incorrect email or password.',
  'auth/user-not-found':        'Incorrect email or password.',
  'auth/wrong-password':        'Incorrect email or password.',
  'auth/weak-password':         `Use at least ${MIN_PASSWORD} characters.`,
  'auth/password-does-not-meet-requirements': `Use at least ${MIN_PASSWORD} characters.`,
  'auth/invalid-email':         'Please enter a valid email address.',
  'auth/too-many-requests':     'Too many attempts. Try again in a few minutes.',
  'auth/popup-closed-by-user':  null,
}

export default function Login() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')
  // Google sign-in for an address that already has a password account (Firebase: account-exists-with-different-
  // credential): sign in with the password once, then Google is linked to that same account
  const [linking, setLinking] = useState(null)        // {email, credential}
  const { setUser, endDemo, signedOutNotice, setSignedOutNotice } = useAuthStore()
  const navigate = useNavigate()
  const { state } = useLocation()

  // App's /login route sends a signed-in user on to state.next (the page they were heading for) or home
  const onSuccess = (user) => { endDemo(); setSignedOutNotice(null); setUser(user) }

  const handleGoogle = async () => {
    setError(''); setLoading(true)
    try {
      const r = await signInWithGoogle()
      onSuccess(r.user)
    } catch (e) {
      if (e.code === 'auth/account-exists-with-different-credential') {
        setLinking({ email: e.customData?.email || '', credential: GoogleAuthProvider.credentialFromError(e) })
        setEmail(e.customData?.email || ''); setMode('login'); setError('')
        return
      }
      const msg = ERROR_MAP[e.code]
      if (msg !== null) setError(msg || 'Google sign-in failed. Please try again.')
    } finally { setLoading(false) }
  }

  const handleReset = async (e) => {
    e.preventDefault(); setError(''); setNotice(''); setLoading(true)
    try {
      await sendPasswordResetEmail(auth, email)
    } catch (err) {
      if (err.code === 'auth/invalid-email') { setError(ERROR_MAP['auth/invalid-email']); setLoading(false); return }
      if (err.code === 'auth/too-many-requests') { setError(ERROR_MAP['auth/too-many-requests']); setLoading(false); return }
      // any other answer (including "no such user") gets the same message as success
    }
    api.post('/auth/password-reset-requested', { email }).catch(() => {})   // for the account's activity log
    setNotice(RESET_SENT)
    setLoading(false)
  }

  const handleEmail = async (e) => {
    e.preventDefault(); setError(''); setLoading(true)
    if (mode === 'signup' && password.length < MIN_PASSWORD) {
      setError(`Use at least ${MIN_PASSWORD} characters.`); setLoading(false); return
    }
    try {
      if (mode === 'login') {
        const { user } = await signInWithEmailAndPassword(auth, email, password)
        if (linking?.credential) {
          await linkWithCredential(user, linking.credential)
          await api.post('/api/account/sign-in-methods/linked', { method: 'google.com' }).catch(() => {})
          setLinking(null)
        }
        onSuccess(user)
        return
      }
      const r = await createUserWithEmailAndPassword(auth, email, password)
      await sendEmailVerification(r.user)
      noteVerificationSent()
      endDemo(); setUser(r.user)
      navigate('/verify-email')
    } catch (e) {
      if (mode === 'signup' && e.code === 'auth/email-already-in-use') {
        // The same screen as a new sign-up, so this form never reveals which addresses have accounts
        noteVerificationSent()
        navigate('/verify-email', { state: { email } })
        return
      }
      setError(ERROR_MAP[e.code] || 'Something went wrong. Please try again.')
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-dvh grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] bg-canvas">
      <section className="hidden lg:flex flex-col justify-between p-12 border-r border-line bg-surface">
        <Wordmark to="/welcome" size="text-2xl" />
        <div className="space-y-6 max-w-md">
          <p className="font-display text-display-s text-ink">Every rupee, accounted for. Nothing you didn't choose to share.</p>
          <ul className="space-y-3 text-sm text-ink-2">
            <li className="rule pt-3">Statements are read on your device and never uploaded.</li>
            <li className="rule pt-3">Account numbers, balances and passwords are never stored.</li>
            <li className="rule pt-3">Delete everything, anytime.</li>
          </ul>
        </div>
        <Link to="/security" className="text-sm text-accent-text hover:underline">How each of these works</Link>
      </section>

      <section className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm animate-rise">
          <div className="lg:hidden mb-10"><Wordmark to="/welcome" size="text-2xl" /></div>
          <h1 className="font-display text-display-s text-ink">{{ login: 'Welcome back', signup: 'Create your account', reset: 'Reset your password' }[mode]}</h1>
          <p className="text-sm mt-2 text-muted">
            {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <button onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(''); setNotice('') }}
              className="font-medium text-accent-text underline underline-offset-2">
              {mode === 'login' ? 'Sign up' : 'Log in'}
            </button>
          </p>

          {linking && (
            <p role="status" className="mt-6 text-sm text-ink bg-sunken rounded-sm px-3 py-2">
              You already have a Vaulta account for {linking.email || 'this email'} with a password. Log in with it once and
              Google will be added to the same account.
            </p>
          )}
          {(state?.notice || signedOutNotice) && (
            <p role="status" className="mt-6 text-sm text-ink bg-sunken rounded-sm px-3 py-2">{state?.notice || signedOutNotice}</p>
          )}
          <div className="mt-8 space-y-5">
            <button onClick={handleGoogle} disabled={loading} className="btn-secondary w-full h-11">
              <GoogleIcon /> Continue with Google
            </button>
            <div className="flex items-center gap-3 text-micro text-muted" aria-hidden>
              <span className="flex-1 h-px bg-line" />or<span className="flex-1 h-px bg-line" />
            </div>
            {mode === 'reset' ? (
              <form onSubmit={handleReset} className="space-y-4">
                <div className="space-y-1.5">
                  <label htmlFor="reset-email" className="label">Email</label>
                  <input id="reset-email" type="email" value={email} onChange={e => setEmail(e.target.value)} spellCheck={false}
                    placeholder="you@example.com" required className="input" autoComplete="email" name="email" />
                </div>
                {error && <p role="alert" className="text-sm text-danger bg-danger-tint rounded-sm px-3 py-2">{error}</p>}
                {notice && <p role="status" className="text-sm text-ink bg-sunken rounded-sm px-3 py-2">{notice}</p>}
                <button type="submit" disabled={loading || !email} className="btn-primary w-full h-11">{loading ? 'Please wait…' : 'Send reset link'}</button>
                <button type="button" onClick={() => { setMode('login'); setError(''); setNotice('') }} className="btn-quiet w-full h-11">Back to log in</button>
              </form>
            ) : (
            <form onSubmit={handleEmail} className="space-y-4">
                <div className="space-y-1.5">
                  <label htmlFor="login-email" className="label">Email</label>
                  <input id="login-email" type="email" value={email} onChange={e => setEmail(e.target.value)} spellCheck={false}
                    placeholder="you@example.com" required className="input" autoComplete="email" name="email" />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="login-password" className="label">Password</label>
                  <input id="login-password" type="password" value={password} onChange={e => setPassword(e.target.value)}
                    placeholder="••••••••" required className="input" name="password"
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'} aria-describedby={mode === 'signup' ? 'password-hint' : undefined} />
                  {mode === 'signup' && <p id="password-hint" className="text-xs text-muted">At least {MIN_PASSWORD} characters. A short phrase is easiest to remember.</p>}
                  {mode === 'login' && (
                    <button type="button" onClick={() => { setMode('reset'); setError('') }} className="text-sm text-accent-text underline underline-offset-2">
                      Forgot password?
                    </button>
                  )}
                </div>
                {error && <p role="alert" className="text-sm text-danger bg-danger-tint rounded-sm px-3 py-2">{error}</p>}
                <button type="submit" disabled={loading || !email || !password} className="btn-primary w-full h-11">
                  {loading ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
                </button>
              </form>
            )}
          </div>
          <p className="text-xs mt-8 text-muted">
            By continuing you agree to our <Link to="/terms" className="underline">terms of service</Link>. <Link to="/security" className="underline">What happens to your data</Link>
          </p>
          <RecaptchaNotice className="mt-2" />
        </div>
      </section>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
    </svg>
  )
}