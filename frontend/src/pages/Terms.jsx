import { Link } from 'react-router-dom'
import { PRIVACY_CONTACT } from '../lib/trust'
import Wordmark from '../ui/Wordmark'

// Plain-language terms of service. Everything described is what Vaulta does today (free, no payments configured).
// It needs the owner's (and ideally a lawyer's) review before launch: the banner says so until then.

const SECTIONS = [
  ['What vaulta.in is', [
    'vaulta.in is a personal spending tracker run by Kanveer Madan in India. It reads your bank, card and UPI statements on your device, files your transactions into categories, and answers questions about your own spending.',
    'vaulta.in is free. If paid plans are ever offered, the price and terms are shown before you pay, and nothing you already have is taken away for not paying.',
  ]],
  ['Not financial advice', [
    'vaulta.in shows and summarises your own transactions. It doesn\'t give financial, tax, investment or legal advice, and it isn\'t a bank, a payment service or an account aggregator: it never moves money and can\'t see your accounts.',
    'Categories, forecasts, budgets and AI chat answers can be wrong. Check anything that matters against your bank\'s own records before acting on it.',
  ]],
  ['Your account', [
    'You need to be 18 or over. One account per person; keep your sign-in to yourself. You\'re responsible for what happens in your account.',
    'Only import statements and forward alerts for accounts that are yours, or that you have permission to use.',
  ]],
  ['Your data', [
    'Your data stays yours. vaulta.in uses it only to run the service for you, as the privacy policy describes, and never sells it.',
    'You can export everything, delete one import, reset your data or delete your account at any time in Settings.',
  ]],
  ['Fair use', [
    'Don\'t try to get at other people\'s data, overload or attack the service, get around its limits or bot checks, scrape it, or use it for anything unlawful. vaulta.in can limit, suspend or close an account that does, and will tell you why where it safely can.',
  ]],
  ['Availability', [
    'vaulta.in runs on free hosting. It can be slow to wake after a quiet spell, and it can be unavailable at times or change as it improves. There\'s no guarantee of uptime. Keep your bank statements: vaulta.in isn\'t a place to store records you\'re required to keep.',
    'If vaulta.in shuts down, we\'ll email you in advance whenever possible (we aim for at least 30 days) so you can export your data.',
  ]],
  ['Liability', [
    'vaulta.in is provided as it is. As far as the law allows, vaulta.in isn\'t liable for indirect losses, or for decisions made on its numbers, categories or answers. Nothing here limits rights you have under Indian consumer law that can\'t be limited.',
  ]],
  ['Changes and law', [
    'If these terms change, the new version is published here before it applies; for a change that matters, you\'ll be told by email. These terms are governed by the laws of India.',
  ]],
]

export default function Terms() {
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="max-w-3xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Wordmark to="/welcome" />
        <Link to="/welcome" className="text-sm text-ink-2 hover:text-ink">← Back to vaulta.in</Link>
      </header>
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-10 text-ink-2 leading-relaxed">
        <p role="note" className="rounded-md border border-line bg-sunken px-4 py-3 text-sm text-ink">
          Draft for review: these terms describe how things work today, and are awaiting their owner's review before launch.
        </p>
        <h1 className="mt-8 font-display text-display-m text-ink">Terms of service</h1>
        <p className="mt-4 max-w-[60ch]">
          The short version: vaulta.in (the "Service") is free, your data is yours, it isn't financial advice, and you can leave with everything at
          any time. How your data is handled is in the <Link to="/privacy" className="text-accent-text underline underline-offset-2">privacy policy</Link>.
        </p>
        {SECTIONS.map(([title, paras]) => (
          <section key={title}>
            <h2 className="mt-12 font-display text-2xl text-ink">{title}</h2>
            {paras.map((p) => <p key={p} className="mt-4">{p}</p>)}
          </section>
        ))}
        <h2 className="mt-12 font-display text-2xl text-ink">Contact</h2>
        <p className="mt-4">
          Questions, complaints and grievances:{' '}
          {PRIVACY_CONTACT
            ? <a href={`mailto:${PRIVACY_CONTACT}`} className="font-medium text-accent-text underline underline-offset-2">{PRIVACY_CONTACT}</a>
            : <span className="text-ink">set by the deployment</span>}.
        </p>
      </main>
    </div>
  )
}
