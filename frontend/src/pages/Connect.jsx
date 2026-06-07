import { useState } from 'react'
import clsx from 'clsx'

const SOURCES = [
  {
    id: 'gmail',
    icon: '✉',
    title: 'Gmail',
    description: 'Parse order confirmations from Swiggy, Zomato, Amazon, Flipkart automatically.',
    badge: 'Recommended first',
    badgeColor: 'text-safe bg-safe/10 border-safe/20',
    available: true,
  },
  {
    id: 'sms',
    icon: '💬',
    title: 'Bank SMS',
    description: 'Forward transaction alerts from any Indian bank via our WhatsApp bot.',
    badge: 'Easy setup',
    badgeColor: 'text-cream-300 bg-forest-800 border-forest-600',
    available: true,
  },
  {
    id: 'aa',
    icon: '🏦',
    title: 'Account Aggregator',
    description: 'Full bank history via RBI-regulated framework. Read-only. 50+ banks supported.',
    badge: 'Phase 5',
    badgeColor: 'text-forest-400 bg-forest-800 border-forest-700',
    available: false,
  },
  {
    id: 'csv',
    icon: '📄',
    title: 'UPI CSV / Statement PDF',
    description: 'Upload exports from GPay, PhonePe, or credit card statements.',
    badge: 'Coming soon',
    badgeColor: 'text-forest-400 bg-forest-800 border-forest-700',
    available: false,
  },
]

const PRIVACY_ROWS = [
  { can: true,  text: 'Order confirmation emails from Swiggy, Zomato, Amazon, Flipkart' },
  { can: true,  text: 'Bank SMS messages you have explicitly forwarded to us' },
  { can: true,  text: 'Transaction history via RBI Account Aggregator (read-only)' },
  { can: false, text: 'Your Gmail inbox — we cannot read anything except order emails' },
  { can: false, text: 'Your bank login credentials — we never ask for these' },
  { can: false, text: 'Your UPI PIN or OTP — architecturally impossible for us to see' },
]

export default function Connect() {
  const [connected, setConnected] = useState({})

  return (
    <div className="max-w-2xl space-y-8 animate-fade-up">
      <div>
        <h1 className="font-display text-2xl font-light text-cream-100 tracking-tight">Connect your accounts</h1>
        <p className="text-forest-300 text-sm mt-2 leading-relaxed">
          We earn the right to each data source separately. Start with Gmail — get one real insight first, then decide if you want to go deeper.
        </p>
      </div>

      {/* Trust signal */}
      <div className="flex items-start gap-3 bg-safe/5 border border-safe/20 rounded-xl px-4 py-3.5">
        <div className="w-5 h-5 rounded-full bg-safe/20 flex items-center justify-center shrink-0 mt-0.5">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#27AE60" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <p className="text-forest-100 text-sm leading-relaxed">
          We never see your bank login, password, or UPI PIN. The Account Aggregator framework is RBI-regulated — you consent directly with your bank, not us.
        </p>
      </div>

      {/* Data sources */}
      <div className="space-y-3">
        <p className="label">Data sources</p>
        {SOURCES.map((src) => (
          <div key={src.id} className={clsx('card p-4 flex items-center gap-4', !src.available && 'opacity-50')}>
            <div className="w-10 h-10 rounded-lg bg-forest-800 border border-forest-700 flex items-center justify-center text-lg shrink-0">
              {src.icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <p className="text-cream-200 text-sm font-medium">{src.title}</p>
                <span className={`text-xs border px-1.5 py-px rounded ${src.badgeColor}`}>{src.badge}</span>
              </div>
              <p className="text-forest-300 text-xs leading-relaxed">{src.description}</p>
            </div>
            {connected[src.id] ? (
              <div className="flex items-center gap-1.5 text-safe text-xs font-medium shrink-0">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                Connected
              </div>
            ) : src.available ? (
              <button
                onClick={() => setConnected(p => ({ ...p, [src.id]: true }))}
                className="btn-primary shrink-0 !py-1.5 !px-3 text-xs"
              >
                Connect
              </button>
            ) : (
              <span className="text-forest-600 text-xs shrink-0">Soon</span>
            )}
          </div>
        ))}
      </div>

      {/* Privacy table */}
      <div className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-forest-700">
          <p className="text-cream-200 text-sm font-medium">What Vaulta can and cannot see</p>
          <p className="text-forest-400 text-xs mt-0.5">Plain English. Not a privacy policy.</p>
        </div>
        <div className="divide-y divide-forest-800">
          {PRIVACY_ROWS.map((row, i) => (
            <div key={i} className="px-5 py-3 flex items-start gap-3">
              <span className={`text-xs font-bold shrink-0 mt-0.5 ${row.can ? 'text-safe' : 'text-danger'}`}>
                {row.can ? '✓' : '✗'}
              </span>
              <span className="text-forest-100 text-sm leading-relaxed">{row.text}</span>
            </div>
          ))}
        </div>
        <div className="px-5 py-4 border-t border-forest-700 bg-forest-950/50">
          <p className="text-forest-400 text-xs leading-relaxed">
            The code that touches your data is publicly auditable on GitHub. 99% of users will never read it.
            The fact that there's nothing to hide is the trust signal.
          </p>
        </div>
      </div>
    </div>
  )
}