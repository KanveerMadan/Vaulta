import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../lib/api'

/** Settings → Security: sign out of all devices (and, as later steps add them, sign-in methods and password). */
export default function SecuritySettings() {
  const navigate = useNavigate()
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
