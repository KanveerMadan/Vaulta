import { Link } from 'react-router-dom'
import { TRUST } from '../lib/trust'

export default function Security() {
  return (
    <div className="min-h-dvh bg-sage-50">
      <div className="max-w-2xl mx-auto px-4 py-10 space-y-6">
        <Link to="/welcome" className="text-sm text-forest-600 hover:underline inline-block py-2">← Vaulta</Link>
        <h1 className="font-display text-3xl text-ink-900">Security and privacy</h1>
        <p className="text-sm text-ink-600">What Vaulta does with your financial data, and how.</p>
        {TRUST.map((t) => (
          <section key={t.claim} className="card p-5 space-y-2">
            <h2 className="text-base font-semibold text-ink-900">{t.claim}</h2>
            <p className="text-sm text-ink-600 leading-relaxed"><span className="font-medium text-ink-700">How it works: </span>{t.how}</p>
          </section>
        ))}
      </div>
    </div>
  )
}
