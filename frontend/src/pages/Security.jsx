import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { SECURITY_CONTACT, TRUST } from '../lib/trust'
import Wordmark from '../ui/Wordmark'

export default function Security() {
  const { hash } = useLocation()
  // The page loads lazily, after the browser has looked for the #anchor: scroll to it once it exists
  useEffect(() => {
    if (hash) document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView()
  }, [hash])
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="max-w-3xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Wordmark to="/welcome" />
        <Link to="/welcome" className="text-sm text-ink-2 hover:text-ink">← Back to Vaulta</Link>
      </header>
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
        <h1 className="font-display text-display-m text-ink">Security and privacy</h1>
        <p className="mt-4 text-lg text-ink-2 max-w-[52ch]">
          What Vaulta does with your financial data, and how. Each statement here is true of the code today, and each one
          says how it is checked.
        </p>

        <ol className="mt-12 border-t border-line" aria-label="Claims">
          {TRUST.map((t, i) => (
            <li key={t.id} id={`claim-${i + 1}`} className="scroll-mt-6 border-b border-line py-6 grid sm:grid-cols-[3rem_1fr] gap-x-4 gap-y-2">
              <span className="num font-display text-2xl text-faint" aria-hidden>{i + 1}</span>
              <div>
                <h2 className="font-display text-2xl text-ink">{t.claim}</h2>
                <a href={`#how-${t.id}`} className="inline-block mt-2 text-sm font-medium text-accent-text hover:underline">How it works</a>
              </div>
            </li>
          ))}
        </ol>

        <h2 className="font-display text-display-s text-ink mt-16">How it works</h2>
        <div className="mt-6 space-y-10">
          {TRUST.map((t) => (
            <section key={t.id} id={`how-${t.id}`} aria-labelledby={`how-${t.id}-title`} className="scroll-mt-6">
              <h3 id={`how-${t.id}-title`} className="font-semibold text-lg text-ink">{t.claim}</h3>
              <p className="mt-2 text-ink-2 leading-relaxed max-w-[62ch]">{t.how}</p>
              <p className="mt-2 text-sm text-muted max-w-[62ch]"><span className="font-semibold">How it's checked: </span>{t.checked}</p>
              {t.id === 'report' && (
                <p className="mt-3 text-ink">
                  Security contact:{' '}
                  {SECURITY_CONTACT
                    ? <a href={`mailto:${SECURITY_CONTACT}`} className="font-medium text-accent-text hover:underline">{SECURITY_CONTACT}</a>
                    : <a href="/.well-known/security.txt" className="font-medium text-accent-text hover:underline">security.txt</a>}
                </p>
              )}
            </section>
          ))}
        </div>

        <p className="mt-16 text-ink-2">
          What Vaulta collects, why, how long it's kept and your rights: <Link to="/privacy" className="font-medium text-accent-text hover:underline">privacy policy</Link>.
        </p>
      </main>
    </div>
  )
}
