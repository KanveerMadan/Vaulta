import { Link } from 'react-router-dom'
import { TRUST } from '../lib/trust'
import Wordmark from '../ui/Wordmark'

export default function Security() {
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="max-w-3xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Wordmark to="/welcome" />
        <Link to="/welcome" className="text-sm text-ink-2 hover:text-ink">← Back to Vaulta</Link>
      </header>
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
        <h1 className="font-display text-display-m text-ink">Security and privacy</h1>
        <p className="mt-4 text-lg text-ink-2 max-w-[52ch]">What Vaulta does with your financial data, and how. Each statement here is true of the code today.</p>
        <ol className="mt-12 border-t border-line">
          {TRUST.map((t, i) => (
            <li key={t.claim} id={`claim-${i + 1}`} className="scroll-mt-6 border-b border-line py-8 grid sm:grid-cols-[3rem_1fr] gap-x-4 gap-y-2">
              <span className="num font-display text-2xl text-faint" aria-hidden>{i + 1}</span>
              <div>
                <h2 className="font-display text-2xl text-ink">{t.claim}</h2>
                <p className="mt-3 text-ink-2 leading-relaxed max-w-[62ch]"><span className="font-semibold text-ink">How it works: </span>{t.how}</p>
              </div>
            </li>
          ))}
        </ol>
      </main>
    </div>
  )
}
