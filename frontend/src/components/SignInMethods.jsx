import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../lib/api'
import { useAuthStore } from '../store/authStore'

const NAMES = { password: 'Email and password', 'google.com': 'Google' }

/** Settings → Security → Sign-in methods: one account, any of these ways in. */
export default function SignInMethods() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const [methods, setMethods] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => api.get('/api/account/sign-in-methods').then(({ data }) => setMethods(data.methods)).catch(() => setMethods([])), [])
  useEffect(() => { load() }, [load])

  const linkGoogle = async () => {
    setError(''); setBusy(true)
    try {
      const [{ linkWithPopup, browserPopupRedirectResolver }, { googleProvider }, { ensureRecentLogin }] =
        await Promise.all([import('firebase/auth'), import('../lib/firebase'), import('../lib/reauth')])
      await ensureRecentLogin(user)
      await linkWithPopup(user, googleProvider, browserPopupRedirectResolver)
      await api.post('/api/account/sign-in-methods/linked', { method: 'google.com' }, { recent: true })
      await load()
    } catch (e) {
      if (e.code === 'auth/credential-already-in-use') setError('That Google account already belongs to another vaulta.in account.')
      else if (e.code !== 'auth/popup-closed-by-user' && e.message !== 'reauth cancelled') setError("Couldn't link Google. Try again.")
    } finally { setBusy(false) }
  }

  const unlink = async (method) => {
    if (!window.confirm(`Stop signing in with ${NAMES[method]}? Every device will be signed out.`)) return
    setError(''); setBusy(true)
    try {
      await api.delete(`/api/account/sign-in-methods/${encodeURIComponent(method)}`, { recent: true })
    } catch (e) {
      setError(e?.response?.data?.detail || "Couldn't remove it. Try again."); setBusy(false)
      return
    }
    const [{ signOut }, { auth }] = await Promise.all([import('firebase/auth'), import('../lib/firebase')])
    await signOut(auth)
    navigate('/login', { replace: true, state: { notice: `${NAMES[method]} was removed and every device was signed out. Sign in again.` } })
  }

  if (!methods) return null
  return (
    <div className="space-y-2" aria-labelledby="methods-title">
      <h3 id="methods-title" className="text-sm font-medium text-ink-900">Sign-in methods</h3>
      <ul className="divide-y divide-sage-50 text-sm" aria-label="Sign-in methods">
        {methods.map((m) => (
          <li key={m} className="py-1.5 flex items-center justify-between gap-4">
            <span className="text-ink-700">{NAMES[m] || m}</span>
            {methods.length > 1 && (
              <button onClick={() => unlink(m)} disabled={busy} className="btn-quiet text-danger" aria-label={`Remove ${NAMES[m] || m}`}>Remove</button>
            )}
          </li>
        ))}
      </ul>
      {methods.length === 1 && <p className="text-xs text-muted">Add another method before you can remove this one.</p>}
      {!methods.includes('google.com') && <button onClick={linkGoogle} disabled={busy} className="btn-secondary">Link Google</button>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  )
}
