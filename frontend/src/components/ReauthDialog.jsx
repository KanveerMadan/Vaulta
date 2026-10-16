import { useEffect, useState } from 'react'
import Sheet from '../ui/Sheet'
import api from '../lib/api'

/** The "sign in again" prompt (lib/reauth.js): password, or Google for accounts that use it. */
export default function ReauthDialog() {
  const [ask, setAsk] = useState(null)        // {resolve, reject}
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [user, setUser] = useState(null)

  useEffect(() => {
    const onAsk = async (e) => {
      const { auth } = await import('../lib/firebase')
      setUser(auth.currentUser)
      setPassword(''); setError(''); setAsk(e.detail)
    }
    window.addEventListener('vaulta:reauth', onAsk)
    return () => window.removeEventListener('vaulta:reauth', onAsk)
  }, [])

  if (!ask || !user) return null
  const providers = user.providerData.map((p) => p.providerId)
  const done = async () => { await user.getIdToken(true); ask.resolve(); setAsk(null) }
  const failed = (message) => {
    setError(message)
    api.post('/api/account/reauth-failed').catch(() => {})
  }
  const cancel = () => { ask.reject(new Error('reauth cancelled')); setAsk(null) }

  const withPassword = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const { EmailAuthProvider, reauthenticateWithCredential } = await import('firebase/auth')
      await reauthenticateWithCredential(user, EmailAuthProvider.credential(user.email, password))
      await done()
    } catch (err) {
      failed(err.code === 'auth/too-many-requests' ? 'Too many attempts. Try again in a few minutes.' : "That password didn't work.")
    } finally { setBusy(false) }
  }
  const withGoogle = async () => {
    setBusy(true); setError('')
    try {
      const [{ reauthenticateWithPopup, browserPopupRedirectResolver }, { googleProvider }] =
        await Promise.all([import('firebase/auth'), import('../lib/firebase')])
      await reauthenticateWithPopup(user, googleProvider, browserPopupRedirectResolver)
      await done()
    } catch (err) {
      if (err.code !== 'auth/popup-closed-by-user') failed("Google sign-in didn't complete. Try again.")
    } finally { setBusy(false) }
  }

  return (
    <Sheet title="Sign in again" onClose={cancel}>
      <p className="text-sm text-ink-2">For your security, confirm it's you before doing this.</p>
      {providers.includes('password') && (
        <form onSubmit={withPassword} className="mt-4 space-y-3">
          <label htmlFor="reauth-password" className="label">Password for {user.email}</label>
          <input id="reauth-password" type="password" autoComplete="current-password" className="input" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
          <button type="submit" disabled={busy || !password} className="btn-primary w-full h-11">Confirm</button>
        </form>
      )}
      {providers.includes('google.com') && (
        <button onClick={withGoogle} disabled={busy} className="btn-secondary w-full h-11 mt-4">Confirm with Google</button>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
    </Sheet>
  )
}
