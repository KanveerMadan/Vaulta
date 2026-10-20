import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Check, DoorOpen, EnvelopeSimple, GithubLogo, Key, LinkedinLogo, Plus, Sparkle, Wall } from '@phosphor-icons/react'
import { useAuthStore } from '../../store/authStore'
import { TRUST } from '../../lib/trust'
import { useMedia } from '../../lib/useMedia'
import Wordmark from '../../ui/Wordmark'
import GoogleIcon from '../../ui/GoogleIcon'
import RecaptchaNotice from '../../ui/RecaptchaNotice'
import { formatINR } from '../../lib/money'
import { REMOVED, ROWS } from './story'
import Reveal from './Reveal'
import { Cutout, Phone } from './Shot'
import { CHIPS, COMPARE, FAQ, FEATURES, LINKEDIN_URL, PAIN, REPO_URL, STEPS, TILES } from './content'

// The scroll-scrubbed statement (and the animation library with it) loads only when "Why Vaulta" comes near
const WhyStage = lazy(() => import('./WhyStage'))
const ICONS = { key: Key, wall: Wall, mail: EnvelopeSimple, ai: Sparkle, leave: DoorOpen, code: GithubLogo }
const claimHref = (id) => `/security#claim-${TRUST.findIndex((t) => t.id === id) + 1}`

/** Sign in with Google (big), the demo (a quiet link under it), and Google's reCAPTCHA notice (small). */
function Ctas({ busy, onGoogle, onDemo, error, demoLabel, align = 'start' }) {
  return (
    <div className={`flex flex-col gap-3 ${align === 'center' ? 'items-center text-center' : 'items-start'}`}>
      <button onClick={onGoogle} disabled={!!busy} data-cta="primary"
        className="btn-primary h-14 w-full sm:w-auto px-7 text-base font-semibold gap-3 shadow-2">
        <span className="grid place-items-center w-7 h-7 rounded-full bg-white" aria-hidden="true"><GoogleIcon size={16} /></span>
        {busy === 'google' ? 'Signing in…' : 'Sign in with Google'}
      </button>
      <button onClick={onDemo} disabled={!!busy} data-cta="demo"
        className="text-sm font-medium text-accent-text underline-offset-4 hover:underline focus-visible:underline min-h-11 px-1">
        {busy === 'demo' ? 'Opening the demo…' : demoLabel}
      </button>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <RecaptchaNotice className="!text-[11px]" />
    </div>
  )
}

function Section({ id, eyebrow, title, intro, children, className = '' }) {
  return (
    <section aria-labelledby={id} className={`max-w-6xl mx-auto px-4 sm:px-6 py-20 sm:py-28 ${className}`}>
      <Reveal className="max-w-2xl">
        {eyebrow && <p className="text-micro font-semibold uppercase tracking-[0.14em] text-accent-text">{eyebrow}</p>}
        <h2 id={id} className="mt-3 font-display text-[clamp(2rem,5.5vw,3.25rem)] leading-[1.02] tracking-[-0.03em] text-ink">{title}</h2>
        {intro && <p className="mt-4 text-lg text-ink-2">{intro}</p>}
      </Reveal>
      <div className="mt-12">{children}</div>
    </section>
  )
}

function Hero({ ctas }) {
  return (
    <section aria-labelledby="hero" className="max-w-6xl mx-auto px-4 sm:px-6 pt-8 pb-16 lg:pt-16 lg:pb-24 grid gap-12 [&>*]:min-w-0 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] lg:items-center">
      <div>
        <h1 id="hero" className="font-display text-[clamp(3.1rem,13vw,6.5rem)] leading-[0.92] tracking-[-0.045em] text-ink">
          Kahan gaye <span className="text-accent-text">paise?</span>
        </h1>
        <p data-hero-sub className="mt-5 text-[clamp(1.125rem,4.4vw,1.4rem)] leading-snug text-ink-2 max-w-[34ch]">
          The question every month ends with. You never quite know the answer.{' '}
          <span className="font-semibold text-accent-text">vaulta.in does.</span>
        </p>
        <p data-hero-note className="mt-2 text-sm sm:text-base text-muted">
          Without your bank login, your SMS, or a single typed entry.
        </p>
        <div className="mt-6">{ctas}</div>
        <ul aria-label="At a glance" className="mt-8 flex flex-wrap gap-2">
          {CHIPS.map((c) => (
            <li key={c} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] text-ink-2">
              <Check size={13} weight="bold" className="text-accent-text" aria-hidden="true" />{c}
            </li>
          ))}
        </ul>
      </div>
      <div className="relative">
        <div className="absolute inset-x-6 top-10 bottom-0 rounded-[3rem] bg-accent-tint blur-2xl" aria-hidden="true" />
        <div className="relative">
          <Phone name="home" eager alt="vaulta.in's home screen on a phone: safe to spend today ₹2,239, ₹26,863 left this month for 12 days, on pace for ₹45,012 and ₹24,988 under budget, with recent transactions starting at Swiggy." />
        </div>
      </div>
    </section>
  )
}

function Pain() {
  return (
    <section aria-labelledby="pain" className="border-y border-line bg-surface">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
        <h2 id="pain" className="sr-only">Sound familiar?</h2>
        <ul className="grid gap-4 sm:grid-cols-3">
          {PAIN.map((p, i) => (
            <Reveal as="li" key={p.title} delay={i * 90} className="rounded-lg border border-line bg-canvas p-6">
              <h3 className="font-display text-2xl leading-tight tracking-[-0.02em] text-ink">{p.title}</h3>
              <p className="mt-3 text-ink-2">{p.body}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}

function HowItWorks() {
  return (
    <Section id="how" eyebrow="How it works" title="Set it up once. Then just ask.">
      <ol className="grid gap-12 lg:grid-cols-3 lg:gap-8">
        {STEPS.map((s, i) => (
          <Reveal as="li" key={s.title} delay={i * 90} className="flex flex-col">
            <div className="flex items-baseline gap-3">
              <span className="font-display text-4xl text-accent-text" aria-hidden="true">{i + 1}</span>
              <h3 className="font-display text-2xl leading-tight tracking-[-0.02em] text-ink">{s.title}</h3>
            </div>
            <p className="mt-2 text-ink-2">{s.body}</p>
            <div className="mt-6"><Cutout name={s.shot} alt={s.alt} maxH="max-h-[26rem]" /></div>
          </Reveal>
        ))}
      </ol>
    </Section>
  )
}

/** Reduced motion: what's removed and what's left, side by side, nothing moving. */
function StillStage() {
  return (
    <div className="grid gap-4 rounded-lg border border-line bg-canvas p-5">
      <div>
        <p className="text-micro font-semibold uppercase tracking-wide text-muted">Removed on your phone</p>
        <ul className="mt-2 space-y-1 text-sm">
          {REMOVED.map((x) => <li key={x} className="flex gap-2 text-ink-2"><span className="text-danger font-semibold" aria-hidden="true">×</span><span className="line-through decoration-danger">{x}</span></li>)}
        </ul>
      </div>
      <div>
        <p className="text-micro font-semibold uppercase tracking-wide text-muted">What reaches vaulta.in</p>
        <ul className="mt-2 divide-y divide-line text-sm">
          {ROWS.map((r) => <li key={r.raw} className="flex gap-3 py-1.5"><span className="num text-muted w-12">{r.date}</span><span className="flex-1 text-ink truncate">{r.clean}</span><span className="num font-semibold">{r.flow === 'in' ? '+' : '−'}{formatINR(r.amount)}</span></li>)}
        </ul>
      </div>
    </div>
  )
}

function Why({ reduce }) {
  const ref = useRef(null)
  const [near, setNear] = useState(false)
  useEffect(() => {
    if (reduce || !ref.current || typeof IntersectionObserver === 'undefined') return undefined
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setNear(true); io.disconnect() } }, { rootMargin: '400px 0px' })
    io.observe(ref.current)
    return () => io.disconnect()
  }, [reduce])
  return (
    <section ref={ref} aria-labelledby="why" className="bg-surface border-y border-line">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20 sm:py-28 grid gap-12 [&>*]:min-w-0 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] lg:gap-14">
        <div>
          <Reveal>
            <p className="text-micro font-semibold uppercase tracking-[0.14em] text-accent-text">Why vaulta.in</p>
            <h2 id="why" className="mt-3 font-display text-[clamp(2rem,5.5vw,3.25rem)] leading-[1.02] tracking-[-0.03em] text-ink">
              Many finance apps want everything. We want three columns.
            </h2>
          </Reveal>
          {/* phones: one card per row; wider screens: the table */}
          <ul className="mt-10 grid gap-3 sm:hidden" aria-label="Many finance apps compared with vaulta.in">
            {COMPARE.map(([what, them, us]) => (
              <li key={what} className="rounded-lg border border-line bg-canvas p-4">
                <p className="font-semibold text-ink">{what}</p>
                <dl className="mt-2 grid grid-cols-2 gap-3 text-sm">
                  <div><dt className="text-muted">Many finance apps</dt><dd className="text-ink-2">{them}</dd></div>
                  <div><dt className="text-muted">vaulta.in</dt><dd className="font-semibold text-accent-text">{us}</dd></div>
                </dl>
              </li>
            ))}
          </ul>
          <table className="mt-10 hidden sm:table w-full text-left text-[15px]">
            <caption className="sr-only">Many finance apps compared with vaulta.in</caption>
            <thead>
              <tr className="border-b border-line-strong text-sm text-muted">
                <th scope="col" className="py-3 pr-4 font-medium"><span className="sr-only">What</span></th>
                <th scope="col" className="py-3 pr-4 font-medium">Many finance apps</th>
                <th scope="col" className="py-3 font-semibold text-accent-text">vaulta.in</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {COMPARE.map(([what, them, us]) => (
                <tr key={what}>
                  <th scope="row" className="py-4 pr-4 font-medium text-ink">{what}</th>
                  <td className="py-4 pr-4 text-ink-2">{them}</td>
                  <td className="py-4 font-semibold text-ink"><span className="inline-flex items-start gap-2"><Check size={16} weight="bold" className="mt-0.5 shrink-0 text-accent-text" aria-hidden="true" />{us}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-6 text-sm text-muted">Every vaulta.in line here is checked against the code. <Link to="/security" className="text-accent-text underline underline-offset-2">How each one works</Link>.</p>
        </div>
        <div className="lg:sticky lg:top-0 lg:h-[100dvh] flex flex-col justify-center">
          <p className="mb-3 text-sm font-medium text-ink-2">Your statement, as it leaves your phone:</p>
          {reduce ? <StillStage /> : (
            <div className="h-[30rem] sm:h-[34rem] lg:h-[40rem] rounded-lg bg-canvas border border-line p-4">
              {near && <Suspense fallback={null}><WhyStage section={ref} /></Suspense>}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function Security() {
  return (
    <Section id="security" eyebrow="Security, in plain words" title="Built so there's little to lose.">
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map((t, i) => {
          const Icon = ICONS[t.icon]
          const inner = (
            <>
              <span className="grid place-items-center w-10 h-10 rounded-md bg-accent-tint text-accent-text" aria-hidden="true"><Icon size={20} /></span>
              <h3 className="mt-4 font-display text-xl text-ink">{t.title}</h3>
              <p className="mt-2 text-ink-2">{t.body}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent-text">
                {t.href ? 'Read the code' : 'How it works'} <ArrowRight size={14} aria-hidden="true" />
              </span>
            </>
          )
          const cls = '!block h-full rounded-lg border border-line bg-surface p-6 hover:border-accent-line focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent transition-colors'
          return (
            <Reveal as="li" key={t.title} delay={(i % 3) * 80}>
              {t.href
                ? <a href={t.href} target="_blank" rel="noreferrer" className={cls}>{inner}</a>
                : <Link to={claimHref(t.claim)} className={cls}>{inner}</Link>}
            </Reveal>
          )
        })}
      </ul>
    </Section>
  )
}

function Features() {
  return (
    <Section id="features" eyebrow="What you get" title="Less checking. More knowing.">
      <div className="grid gap-20">
        {FEATURES.map((f, i) => (
          <Reveal key={f.title} className="grid gap-8 lg:grid-cols-2 lg:items-center lg:gap-16">
            <div className={i % 2 ? 'lg:order-2' : ''}>
              <h3 className="font-display text-[clamp(1.75rem,4.5vw,2.5rem)] leading-tight tracking-[-0.025em] text-ink">{f.title}</h3>
              <p className="mt-3 text-lg text-ink-2 max-w-[36ch]">{f.body}</p>
            </div>
            <div className={`max-w-md w-full ${i % 2 ? 'lg:order-1' : 'lg:justify-self-end'}`}>
              <Cutout name={f.shot} alt={f.alt} inset={f.inset} />
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

function Faq() {
  return (
    <Section id="faq" eyebrow="Questions" title="Fair questions.">
      <div className="max-w-3xl divide-y divide-line border-y border-line">
        {FAQ.map((f) => (
          <details key={f.q} className="group" name="faq">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-lg font-medium text-ink [&::-webkit-details-marker]:hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent rounded-sm">
              {f.q}
              <Plus size={18} className="shrink-0 text-muted transition-transform group-open:rotate-45" aria-hidden="true" />
            </summary>
            <div className="pb-6 space-y-3 text-ink-2 max-w-[62ch]">
              {f.a.map((p) => <p key={p}>{p}</p>)}
              {f.links && (
                <div className="flex flex-wrap gap-4">
                  <a href={REPO_URL} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center gap-1.5 font-medium text-accent-text underline underline-offset-2"><GithubLogo size={16} aria-hidden="true" />GitHub</a>
                  <a href={LINKEDIN_URL} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center gap-1.5 font-medium text-accent-text underline underline-offset-2"><LinkedinLogo size={16} aria-hidden="true" />LinkedIn</a>
                </div>
              )}
            </div>
          </details>
        ))}
      </div>
    </Section>
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
  const ctas = (label, align) => <Ctas busy={busy} onGoogle={google} onDemo={demo} error={error} demoLabel={label} align={align} />

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
        <Hero ctas={ctas('or look around the demo first →')} />
        <Pain />
        <HowItWorks />
        <Why reduce={reduce} />
        <Security />
        <Features />
        <Faq />
        <section aria-labelledby="final" className="max-w-6xl mx-auto px-4 sm:px-6 pb-24">
          <Reveal className="rounded-lg bg-accent-strong px-6 py-14 sm:px-12 sm:py-20 text-center">
            <h2 id="final" className="font-display text-[clamp(2rem,6vw,3.5rem)] leading-[1.02] tracking-[-0.03em] text-on-accent">
              Your money's been talking. Start listening.
            </h2>
            <div className="mt-8 [&_.btn-primary]:bg-on-accent [&_.btn-primary]:text-accent-strong [&_[data-cta=demo]]:text-on-accent [&_p]:text-on-accent/90 [&_a]:text-on-accent">
              {ctas('or try the demo →', 'center')}
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row gap-4 sm:items-center justify-between text-sm text-muted">
          <Wordmark to="/welcome" size="text-lg" />
          <nav aria-label="Footer" className="flex flex-wrap gap-x-4 gap-y-2">
            <Link to="/security" className="hover:text-ink">Security</Link>
            <Link to="/privacy" className="hover:text-ink">Privacy</Link>
            <Link to="/terms" className="hover:text-ink">Terms</Link>
            <a href="/.well-known/security.txt" className="hover:text-ink">security.txt</a>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-ink">GitHub</a>
            <Link to="/login" className="hover:text-ink">Log in</Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
