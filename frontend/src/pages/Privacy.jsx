import { Link } from 'react-router-dom'
import { PRIVACY_CONTACT } from '../lib/trust'
import Wordmark from '../ui/Wordmark'

// Plain-language privacy policy written to the Digital Personal Data Protection Act, 2023. Every retention period
// and every flow described here is what the code does today. It still needs the owner's (and ideally a lawyer's)
// review before launch: the banner says so until that review is done.

const COLLECTED = [
  ['Your account', 'Your email address and name from Google or your sign-in, and a sign-in id from Firebase.', 'To sign you in and send you the emails you choose.'],
  ['Your transactions', 'The rows you confirm from a statement, alert emails you forward, entries you add yourself or through Telegram: date, description with personal details masked, amount, the account label you chose (for example "HDFC Bank"), and your categories and notes.', 'To show your spending, budgets, reports and alerts. This is the service.'],
  ['What you set up', 'Budgets, goals, rules, the people you pay (names as they appear in your transactions), settings and your answers during setup.', 'To run those features.'],
  ['Chat', 'Your questions to the assistant and its answers.', 'To answer you and keep the conversation going. Deleted after 30 days.'],
  ['Account activity', 'When you signed in, exported, deleted something, linked or unlinked Telegram or changed a setting. Not your IP address.', 'So you can spot activity that isn\'t yours (Settings → Activity).'],
  ['Telegram, if you link it', 'Your Telegram chat id.', 'To reply in that chat. Unlinking removes it.'],
  ['Payments, if you subscribe', 'Your Razorpay subscription id and its status. Card and UPI details stay with Razorpay.', 'To know whether your subscription is active.'],
]

const NOT_COLLECTED = [
  'Statement files: they are read on your device and never uploaded.',
  'Account and card numbers, balances, statement passwords and your login password.',
  'The text of forwarded alert emails, beyond the transaction found in them.',
  'Bill photos: they are read on your phone.',
  'Your location, contacts or advertising identifiers. Vaulta has no ads and no analytics trackers.',
]

const PROCESSORS = [
  ['Google Firebase', 'sign-in'],
  ['Neon', 'the database (your data, encrypted as /security describes)'],
  ['Render', 'the servers that run Vaulta'],
  ['Vercel', 'serving the web app'],
  ['Groq', 'AI chat and report summaries: your question and the figures needed to answer it, never statement text, UPI IDs or notes'],
  ['Resend', 'sending report and alert emails'],
  ['Cloudflare', 'receiving forwarded alert emails, which are passed on without being stored'],
  ['Telegram', 'the bot, only if you link it'],
  ['Razorpay', 'payments, only if you subscribe'],
]

const RETENTION = [
  'Chat history: 30 days, then deleted automatically.',
  'Forwarded alert emails: not kept at all once read; only the transaction found and which bank sent it.',
  'Everything else: until you delete it, or delete your account. Delete everything removes it all from Vaulta\'s database at once, then deletes your sign-in and emails you a confirmation. If the sign-in can\'t be deleted at that moment, Vaulta keeps only its id and your email address until it is, within the hour.',
  'After deletion, copies can remain in the database provider\'s short-term recovery backups until they expire, and are never restored into the service except to recover from a failure.',
]

export default function Privacy() {
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="max-w-3xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Wordmark to="/welcome" />
        <Link to="/welcome" className="text-sm text-ink-2 hover:text-ink">← Back to Vaulta</Link>
      </header>
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-10 text-ink-2 leading-relaxed">
        <p role="note" className="rounded-md border border-line bg-sunken px-4 py-3 text-sm text-ink">
          Draft for review: this policy describes what Vaulta's code does today, and is awaiting review by Vaulta's owner before launch.
        </p>
        <h1 className="mt-8 font-display text-display-m text-ink">Privacy policy</h1>
        <p className="mt-4 max-w-[60ch]">
          Vaulta helps you track your own spending. This page explains, in plain language, what personal data it handles,
          why, how long it keeps it and the rights you have under India's Digital Personal Data Protection Act, 2023. How the
          data is protected is on the <Link to="/security" className="text-accent-text underline underline-offset-2">security page</Link>.
        </p>

        <h2 className="mt-12 font-display text-2xl text-ink">What Vaulta collects and why</h2>
        <dl className="mt-4 divide-y divide-line border-y border-line">
          {COLLECTED.map(([what, detail, why]) => (
            <div key={what} className="py-4 grid sm:grid-cols-[11rem_1fr] gap-x-4 gap-y-1">
              <dt className="font-semibold text-ink">{what}</dt>
              <dd>{detail} <span className="text-ink">Why: </span>{why}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4">Vaulta processes this data because you ask it to when you sign up and use it (your consent). You can withdraw consent at any time by deleting your account.</p>

        <h2 className="mt-12 font-display text-2xl text-ink">What Vaulta never collects</h2>
        <ul className="mt-4 list-disc pl-5 space-y-1">{NOT_COLLECTED.map((t) => <li key={t}>{t}</li>)}</ul>

        <h2 className="mt-12 font-display text-2xl text-ink">Who else handles it</h2>
        <p className="mt-4">Vaulta doesn't sell or share your data for advertising. These services process it on Vaulta's behalf, only for the purpose shown, and some of them do so outside India:</p>
        <ul className="mt-3 list-disc pl-5 space-y-1">{PROCESSORS.map(([who, what]) => <li key={who}><span className="text-ink">{who}</span>: {what}</li>)}</ul>

        <h2 className="mt-12 font-display text-2xl text-ink">How long it's kept</h2>
        <ul className="mt-4 list-disc pl-5 space-y-1">{RETENTION.map((t) => <li key={t}>{t}</li>)}</ul>

        <h2 className="mt-12 font-display text-2xl text-ink">Your rights</h2>
        <ul className="mt-4 list-disc pl-5 space-y-1">
          <li><span className="text-ink">See your data:</span> Settings → Your data downloads all of it, as JSON and CSV.</li>
          <li><span className="text-ink">Correct it:</span> edit any transaction, category, note, person, budget or goal in the app, or ask us.</li>
          <li><span className="text-ink">Erase it:</span> Settings → Delete everything, at any time: your data, then your sign-in, with an email to confirm.</li>
          <li><span className="text-ink">Withdraw consent:</span> delete your account; turn off AI chat, reports or Telegram individually in Settings.</li>
          <li><span className="text-ink">Nominate someone</span> to exercise these rights if you can't: write to the contact below.</li>
          <li><span className="text-ink">Complain:</span> write to the grievance contact below. If you're not satisfied with the answer, you can complain to the Data Protection Board of India.</li>
        </ul>

        <h2 className="mt-12 font-display text-2xl text-ink">Children</h2>
        <p className="mt-4">Vaulta is for adults. Don't use it if you are under 18.</p>

        <h2 className="mt-12 font-display text-2xl text-ink">Grievances and questions</h2>
        <p className="mt-4">
          Contact for privacy questions, requests and grievances:{' '}
          {PRIVACY_CONTACT
            ? <a href={`mailto:${PRIVACY_CONTACT}`} className="font-medium text-accent-text underline underline-offset-2">{PRIVACY_CONTACT}</a>
            : <span className="text-ink">set by the deployment</span>}.
        </p>
        <p className="mt-4">If this policy changes, the new version is published here before it applies.</p>
      </main>
    </div>
  )
}
