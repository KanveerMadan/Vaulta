import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../lib/api'
import { MIN_PASSWORD } from '../lib/verification'
import { useAuthStore } from '../store/authStore'
import SignInMethods from './SignInMethods'

function PasswordForm({ hasPassword }) {
  const { user } = useAuthStore()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [status, setStatus] = useState({})
  const save = async (e) => {
    e.preventDefault()
    if (password.length < MIN_PASSWORD) return setStatus({ error: `Use at least ${MIN_PASSWORD} characters.` })
    if (password !== confirm) return setStatus({ error: "The two passwords don't match." })
    setStatus({ busy: true })
    try {
      await api.post('/api/account/password', { password }, { recent: true })
    } catch (err) {
      return setStatus({ error: err?.response?.data?.detail || "Couldn't change the password. Try again." })
    }
    // Every session was signed out, this one too: sign this browser back in with the new password
    const [{ signInWithEmailAndPassword }, { auth }] = await Promise.all([import('firebase/auth'), import('../lib/firebase')])
    await signInWithEmailAndPassword(auth, user.email, password)
    setPassword(''); setConfirm('')
    setStatus({ done: hasPassword ? 'Password changed. Your other devices were signed out.' : 'Password added. You can now log in with it too.' })
  }
  return (
    <form onSubmit={save} className="space-y-2" aria-labelledby="password-title">
      <h3 id="password-title" className="text-sm font-medium text-ink-900">{hasPassword ? 'Change password' : 'Add a password'}</h3>
      <label htmlFor="new-password" className="label">New password</label>
      <input id="new-password" type="password" autoComplete="new-password" className="input" value={password}
        onChange={(e) => setPassword(e.target.value)} aria-describedby="new-password-hint" />
      <p id="new-password-hint" className="text-xs text-muted">At least {MIN_PASSWORD} characters.</p>
      <label htmlFor="confirm-password" className="label">Type it again</label>
      <input id="confirm-password" type="password" autoComplete="new-password" className="input" value={confirm}
        onChange={(e) => setConfirm(e.target.value)} />
      {status.error && <p role="alert" className="text-sm text-danger">{status.error}</p>}
      {status.done && <p role="status" className="text-sm text-safe">{status.done}</p>}
      <button type="submit" disabled={status.busy || !password} className="btn-secondary">
        {status.busy ? 'Saving…' : hasPassword ? 'Change password' : 'Add password'}
      </button>
    </form>
  )
}

/** Settings → Security: sign out of all devices (and, as later steps add them, sign-in methods and password). */
export default function SecuritySettings() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const providers = user?.providerData?.map((p) => p.providerId) || []
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const signOutEverywhere = async () => {
    setBusy(true); setError('')
    try {
      await api.post('/api/account/sign-out-everywhere')
    } catch {
      setError("Couldn't sign out everywhere. Try again.")
      setBusy(false)
      return
    }
    const [{ signOut }, { auth }] = await Promise.all([import('firebase/auth'), import('../lib/firebase')])
    await signOut(auth)
    navigate('/login', { replace: true, state: { notice: 'You were signed out on all your devices, this one included.' } })
  }

  return (
    <section className="card p-5 space-y-3" aria-labelledby="security-title">
      <h2 id="security-title" className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Security</h2>
      {user && <SignInMethods />}
      {user && <PasswordForm hasPassword={providers.includes('password')} />}
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-ink-900">Sign out of all devices</h3>
        <p className="text-sm text-ink-600">
          Ends every session on every phone and computer, this one included. Your Telegram link and data stay as they are.
        </p>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <button onClick={signOutEverywhere} disabled={busy} className="btn-secondary">
          {busy ? 'Signing out…' : 'Sign out of all devices'}
        </button>
      </div>
    </section>
  )
}
