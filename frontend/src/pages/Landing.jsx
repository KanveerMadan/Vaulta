import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signInWithPopup } from 'firebase/auth'
import { auth, googleProvider } from '../lib/firebase'
import { startDemo } from '../lib/api'
import { useAuthStore } from '../store/authStore'
import { TRUST } from '../lib/trust'

const PROOF = [
  { title: 'Automatic tracking', body: 'Import your statement history once, forward bank alert emails, and log cash in a tap or on Telegram. Transfers, refunds and repayments are sorted out for you.' },
  { title: 'Reports that come to you', body: 'A weekly and monthly summary arrives by email, plus alerts when a budget runs low, a charge looks duplicated or a bill is due tomorrow.' },
  { title: 'Ask anything', body: '“How much went on food this month?” “Can I afford a ₹40,000 trip by March?” Answers come from your own numbers.' },
]

export default function Landing() {
  const navigate = useNavigate()
  const { setUser, endDemo } = useAuthStore()
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)

  const demo = async () => {
    setBusy('demo'); setError(null)
    try { await startDemo(); navigate('/') } catch { setError("The demo isn't available right now. Try again in a minute.") }
    setBusy(null)
  }
  const google = async () => {
    setBusy('google'); setError(null)
    try {
      const r = await signInWithPopup(auth, googleProvider)
      endDemo(); setUser(r.user); navigate('/')
    } catch (e) {
      if (e?.code !== 'auth/popup-closed-by-user') setError('Google sign-in failed. Please try again.')
    }
    setBusy(null)
  }

  return (
    <div className="min-h-dvh bg-forest-950 text-cream-100 overflow-x-hidden">
      <nav className="border-b border-white/5">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-3">
          <span className="font-display text-xl font-light text-cream-200">Vaulta</span>
          <Link to="/login" className="text-forest-200 hover:text-cream-100 text-sm px-3 py-3">Log in</Link>
        </div>
      </nav>

      <main>
        <section className="max-w-3xl mx-auto px-4 pt-16 pb-12 text-center">
          <h1 className="font-display text-3xl sm:text-5xl font-light leading-tight text-cream-50">
            Vaulta tracks every rupee you spend, automatically. Set it up once, then just ask.
          </h1>
          <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
            <button onClick={demo} disabled={!!busy} className="btn-primary justify-center">
              {busy === 'demo' ? 'Opening the demo…' : 'Try the demo'}
            </button>
            <button onClick={google} disabled={!!busy} className="btn-dark justify-center">
              {busy === 'google' ? 'Signing in…' : 'Sign in with Google'}
            </button>
          </div>
          {error && <p role="alert" className="mt-4 text-sm text-red-300">{error}</p>}
          <p className="mt-3 text-xs text-forest-200">The demo uses sample data. No sign-in needed.</p>
        </section>

        <section className="max-w-5xl mx-auto px-4 pb-16 grid grid-cols-1 md:grid-cols-3 gap-4">
          {PROOF.map((p) => (
            <div key={p.title} className="card-glass p-5">
              <h2 className="text-lg font-medium text-cream-50">{p.title}</h2>
              <p className="mt-2 text-sm text-forest-100 leading-relaxed">{p.body}</p>
            </div>
          ))}
        </section>

        <section className="max-w-3xl mx-auto px-4 pb-20" aria-labelledby="trust">
          <h2 id="trust" className="font-display text-2xl font-light text-cream-50">What happens to your data</h2>
          <ul className="mt-5 space-y-3">
            {TRUST.map((t) => (
              <li key={t.claim} className="flex gap-3 text-sm text-forest-100">
                <span aria-hidden className="text-forest-200">✓</span><span>{t.claim}</span>
              </li>
            ))}
          </ul>
          <Link to="/security" className="inline-block mt-5 text-sm font-medium text-cream-100 underline underline-offset-4 py-2">
            How each of these works →
          </Link>
        </section>
      </main>
    </div>
  )
}
