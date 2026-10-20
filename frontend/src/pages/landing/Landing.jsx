import { lazy, Suspense, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Check } from '@phosphor-icons/react'
import { useAuthStore } from '../../store/authStore'
import { LANDING_CLAIMS } from '../../lib/trust'
import Wordmark from '../../ui/Wordmark'
import StaticStory from './StaticStory'
import { useMedia } from '../../lib/useMedia'

// The hero paints from the main bundle; the animation library arrives with these two afterwards.
const StageDriver = lazy(() => import('./StageDriver'))
const Scenes = lazy(() => import('./Scenes'))
import { CAPTIONS } from './story'
import RecaptchaNotice from '../../ui/RecaptchaNotice'

function Ctas({ busy, onDemo, onGoogle, error }) {
  return (
    <div>
      <div className="flex flex-col sm:flex-row gap-3">
        <button onClick={onDemo} disabled={!!busy} className="btn-primary h-12 px-6 text-[15px]">
          {busy === 'demo' ? 'Opening the demo…' : 'Try the demo'}
        </button>
        <button onClick={onGoogle} disabled={!!busy} className="btn-secondary h-12 px-6 text-[15px]">
          {busy === 'google' ? 'Signing in…' : 'Sign in with Google'}
        </button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      <RecaptchaNotice className="mt-3" />
    </div>
  )
}

/** Hero and the statement story share one scroll: the statement on the right is the hero's visual. */
function Story({ ctas }) {
  const ref = useRef(null)
  const captions = useRef(null)
  const [step, setStep] = useState(0)

  return (
    <section ref={ref} className="relative grid grid-cols-[minmax(0,1fr)] lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-10 max-w-6xl mx-auto px-4 sm:px-6" aria-label="How vaulta.in handles your statement">
      <div className="lg:col-start-1 lg:row-start-1 min-h-[calc(100dvh-4rem)] lg:min-h-[100dvh] flex flex-col justify-center py-10 lg:py-0">
        <h1 className="font-display text-[clamp(2.25rem,3.9vw,3.5rem)] leading-[1.04] tracking-[-0.03em] text-ink">
          vaulta.in tracks every rupee you spend, automatically. Set it up once, then just ask.
        </h1>
        <p className="mt-5 text-lg text-ink-2 max-w-[34ch]">Your statements are read on your phone. Only clean transaction rows ever reach us.</p>
        <div className="mt-8">{ctas}</div>
      </div>

      <div className="lg:col-start-2 lg:row-start-1 lg:row-span-2 sticky top-0 h-[62dvh] lg:h-[100dvh] z-10 bg-canvas lg:bg-transparent py-3 lg:py-10 overflow-hidden">
        <Suspense fallback={null}><StageDriver captions={captions} onStep={setStep} /></Suspense>
      </div>

      <ol ref={captions} className="lg:col-start-1 lg:row-start-2 relative pb-[30dvh]">
        {CAPTIONS.map((c, i) => (
          <li key={c.title} className="min-h-[70dvh] lg:min-h-[78dvh] flex items-end pb-[4dvh] lg:pb-0 lg:items-center">
            {/* phones: the caption rests in the band under the pinned statement */}
            <div className={`transition-colors duration-slow ${step === i ? '' : '[&_*]:!text-muted'}`}>
              <h2 className="font-display text-2xl lg:text-[2rem] leading-tight text-ink">{c.title}</h2>
              <p className="mt-2 text-ink-2 max-w-[38ch]">{c.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function ReducedHero({ ctas }) {
  return (
    <section className="max-w-6xl mx-auto px-4 sm:px-6 pt-10 pb-16 lg:pt-20">
      <h1 className="font-display text-[clamp(2.4rem,5.2vw,4.1rem)] leading-[1.02] tracking-[-0.03em] text-ink max-w-[20ch]">
        vaulta.in tracks every rupee you spend, automatically. Set it up once, then just ask.
      </h1>
      <p className="mt-5 text-lg text-ink-2 max-w-[44ch]">Your statements are read on your phone. Only clean transaction rows ever reach us.</p>
      <div className="mt-8">{ctas}</div>
    </section>
  )
}

export default function Landing() {
  const navigate = useNavigate()
  const { setUser, endDemo } = useAuthStore()
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const reduce = useMedia('(prefers-reduced-motion: reduce)')

  const demo = async () => {
    setBusy('demo'); setError(null)
    try { const { startDemo } = await import('../../lib/api'); await startDemo(); navigate('/') } catch { setError("The demo isn't available right now. Try again in a minute.") }
    setBusy(null)
  }
  const google = async () => {
    setBusy('google'); setError(null)
    try {
      const { signInWithGoogle } = await import('../../lib/firebase')
      const r = await signInWithGoogle()
      endDemo(); setUser(r.user); navigate('/')
    } catch (e) {
      if (e?.code !== 'auth/popup-closed-by-user') setError('Google sign-in failed. Please try again.')
    }
    setBusy(null)
  }
  const ctas = <Ctas busy={busy} onDemo={demo} onGoogle={google} error={error} />

  return (
    <div className="min-h-dvh bg-canvas text-ink">
      <header className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Wordmark to="/welcome" />
        <nav aria-label="Site" className="flex items-center gap-1 text-sm">
          <Link to="/security" className="px-3 py-2 rounded-sm text-ink-2 hover:text-ink hover:bg-sunken">Security</Link>
          <Link to="/login" className="px-3 py-2 rounded-sm text-ink-2 hover:text-ink hover:bg-sunken">Log in</Link>
        </nav>
      </header>

      <main>
        {reduce ? <><ReducedHero ctas={ctas} /><StaticStory /></> : <Story ctas={ctas} />}

        <Suspense fallback={<div className="min-h-[200dvh]" />}><Scenes /></Suspense>

        <section aria-labelledby="trust" className="border-t border-line bg-surface">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20 grid lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] gap-10">
            <div>
              <h2 id="trust" className="font-display text-display-s text-ink">What happens to your data</h2>
              <p className="mt-3 text-ink-2 max-w-[36ch]">Things that are true of the code today. Each one links to how it works and how it's checked.</p>
              <Link to="/security" className="inline-flex items-center gap-1.5 mt-5 text-sm font-medium text-accent-text hover:underline">How each of these works →</Link>
            </div>
            <ul className="divide-y divide-line border-y border-line">
              {LANDING_CLAIMS.map((t) => (
                <li key={t.id}>
                  <Link to={`/security#claim-${t.n}`} className="group flex items-center gap-4 py-4 hover:bg-sunken/60 px-2 -mx-2 rounded-sm">
                    <span className="w-7 h-7 shrink-0 rounded-full bg-accent-tint text-accent-text flex items-center justify-center"><Check size={14} weight="bold" aria-hidden /></span>
                    <span className="flex-1 text-[15px] text-ink">{t.claim}</span>
                    <ArrowRight size={16} className="text-muted group-hover:text-ink transition-colors" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
          <div className="rounded-lg border border-line bg-surface p-8 sm:p-12 grid gap-6 lg:grid-cols-[1fr_auto] items-center">
            <div>
              <h2 className="font-display text-display-s text-ink">See it with four months of sample data.</h2>
              <p className="mt-2 text-ink-2">No sign-in, nothing to install. Every number in the demo is computed the same way yours would be.</p>
            </div>
            {ctas}
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row gap-4 sm:items-center justify-between text-sm text-muted">
          <Wordmark to="/welcome" size="text-lg" />
          <nav aria-label="Footer" className="flex gap-4">
            <Link to="/security" className="hover:text-ink">Security</Link>
            <Link to="/privacy" className="hover:text-ink">Privacy</Link>
            <Link to="/terms" className="hover:text-ink">Terms</Link>
            <Link to="/login" className="hover:text-ink">Log in</Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
