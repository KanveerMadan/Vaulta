import { useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'

const FEATURES = [
  {
    icon: '✉',
    title: 'Gmail Intelligence',
    body: 'Parses your Swiggy, Zomato, Amazon, and Flipkart order emails. Every order itemised automatically.',
  },
  {
    icon: '💬',
    title: 'Bank SMS Parsing',
    body: 'Forward transaction alerts from any Indian bank. Every debit and credit captured in real time.',
  },
  {
    icon: '🤖',
    title: 'AI That Reasons',
    body: 'Ask anything in English or Hinglish. "Kitna kharch hua last hafte?" — it answers with your actual data.',
  },
  {
    icon: '🔁',
    title: 'Subscription Graveyard',
    body: 'Auto-detects every recurring charge. Flags the ones you haven\'t used in 30+ days.',
  },
  {
    icon: '📊',
    title: 'Tax Assistant',
    body: 'Tracks 80C investments through the year. Warns you in November. Generates a CA-ready summary.',
  },
  {
    icon: '🎁',
    title: 'Money Wrapped',
    body: 'Year-end shareable spending story. Your top merchant, most expensive day, biggest habit. Every December.',
  },
]

const CHAT_DEMO = [
  { role: 'user', text: 'How much did I spend on Zomato vs Swiggy this month?' },
  { role: 'ai',   text: 'You spent ₹3,240 on Zomato across 14 orders and ₹1,180 on Swiggy across 6 orders. Zomato is your go-to — especially on Tuesday nights.' },
  { role: 'user', text: 'If I cut food by half, when can I afford a MacBook?' },
  { role: 'ai',   text: 'At your current savings rate, cutting food spend by half saves ₹2,200/month. A MacBook Air at ₹1,14,900 would take about 18 months. Want me to model a stricter plan?' },
]

export default function Landing() {
  const navigate = useNavigate()
  const [chatIdx, setChatIdx] = useState(0)
  const [visibleMessages, setVisibleMessages] = useState([])

  useEffect(() => {
    if (chatIdx >= CHAT_DEMO.length) return
    const timer = setTimeout(() => {
      setVisibleMessages(prev => [...prev, CHAT_DEMO[chatIdx]])
      setChatIdx(i => i + 1)
    }, chatIdx === 0 ? 800 : 1600)
    return () => clearTimeout(timer)
  }, [chatIdx])

  return (
    <div className="grain min-h-dvh bg-forest-950 overflow-x-hidden">

      {/* Nav */}
      <nav className="sticky top-0 z-40 border-b border-white/5 bg-forest-950/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-5 h-14 flex items-center justify-between">
          <span className="font-display text-xl font-light text-cream-200 tracking-tight">Vaulta</span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/login')}
              className="text-forest-200 hover:text-cream-100 text-sm transition-colors"
            >
              Log in
            </button>
            <button
              onClick={() => navigate('/login')}
              className="btn-primary !py-2 !px-4 text-xs"
            >
              Get started →
            </button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-5 pt-20 pb-24">
        <div className="max-w-3xl">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 bg-forest-800/60 border border-forest-600/40 rounded-full px-3 py-1.5 mb-8 animate-fade-in">
            <div className="w-1.5 h-1.5 rounded-full bg-safe animate-pulse" />
            <span className="text-forest-100 text-xs font-medium">Built for India · Works with any bank</span>
          </div>

          <h1 className="font-display text-5xl sm:text-6xl lg:text-7xl font-light leading-[1.05] tracking-tight text-cream-50 animate-fade-up">
            Your money,<br />
            <span className="text-gradient-green">finally makes sense.</span>
          </h1>

          <p className="mt-6 text-forest-100 text-lg leading-relaxed max-w-xl animate-fade-up delay-150">
            AI that reads your Gmail, bank SMS, and UPI history to give you an honest picture of where your money goes. Ask in English or Hinglish.
          </p>

          <div className="flex flex-wrap items-center gap-3 mt-8 animate-fade-up delay-225">
            <button
              onClick={() => navigate('/login')}
              className="btn-primary-light !px-6 !py-3 text-sm"
            >
              Start for free →
            </button>
            <span className="text-forest-400 text-xs">
              Free now · ₹99/month when we charge · No data selling
            </span>
          </div>
        </div>

        {/* AI Chat Demo */}
        <div className="mt-16 grid lg:grid-cols-2 gap-8 items-center animate-fade-up delay-300">
          <div className="card shadow-card p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-cream-300 flex items-center justify-between bg-cream-100">
              <div>
                <p className="text-forest-900 text-sm font-semibold">AI Assistant</p>
                <p className="text-forest-500 text-xs">Powered by your real transaction data</p>
              </div>
              <div className="w-2 h-2 rounded-full bg-safe animate-pulse" />
            </div>
            <div className="p-4 space-y-3 min-h-[220px] bg-cream-50">
              {visibleMessages.map((msg, i) => (
                <div key={i} className={`flex animate-fade-up ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-forest-700 text-cream-100 rounded-br-sm'
                      : 'bg-white border border-cream-300 text-forest-900 rounded-bl-sm shadow-card'
                  }`}>
                    {msg.text}
                  </div>
                </div>
              ))}
              {chatIdx < CHAT_DEMO.length && visibleMessages.length > 0 && (
                <div className="flex justify-start">
                  <div className="bg-white border border-cream-300 rounded-xl rounded-bl-sm px-3.5 py-2.5 flex gap-1 shadow-card">
                    {[0,1,2].map(i => (
                      <div key={i} className="w-1.5 h-1.5 rounded-full bg-forest-300 animate-skeleton"
                        style={{ animationDelay: `${i * 0.15}s` }} />
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="px-4 py-3 border-t border-cream-300 bg-cream-100">
              <div className="flex items-center gap-2 bg-white border border-cream-300 rounded-lg px-3 py-2">
                <span className="text-forest-400 text-xs flex-1">Ask about your money...</span>
                <div className="w-6 h-6 rounded bg-forest-700 flex items-center justify-center">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#FBF8F0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                  </svg>
                </div>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div className="space-y-4">
            {[
              { label: 'Spent on food delivery this year', value: '₹74,000', sub: 'That\'s a return flight to Bangkok + 4 nights in a hotel', color: 'text-danger' },
              { label: 'Silent subscription drain', value: '₹2,840/mo', sub: '3 subscriptions you haven\'t opened in 60+ days', color: 'text-gold' },
              { label: 'Left to save this month', value: '₹15,200', sub: 'On track — spend ₹540/day max to hit your goal', color: 'text-safe' },
            ].map((stat, i) => (
              <div key={i} className="card shadow-card p-4 animate-fade-up" style={{ animationDelay: `${300 + i * 80}ms` }}>
                <p className="text-forest-500 text-xs font-medium mb-1">{stat.label}</p>
                <p className={`font-display text-3xl font-light ${stat.color} tracking-tight`}>{stat.value}</p>
                <p className="text-forest-600 text-xs mt-1 leading-relaxed">{stat.sub}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Divider */}
      <div className="border-t border-white/5" />

      {/* Problem section */}
      <section className="max-w-6xl mx-auto px-5 py-20">
        <div className="max-w-2xl">
          <p className="label-dark mb-4">The problem</p>
          <h2 className="font-display text-3xl sm:text-4xl font-light text-cream-100 leading-snug">
            Every Indian finance app has a hidden agenda.
          </h2>
          <p className="mt-4 text-forest-200 leading-relaxed">
            CRED makes money on loans. Fi Money locks you into their neo-bank. Money View uses tracking as bait for lending. Their incentive is to keep you on the platform and upsell financial products.
          </p>
          <p className="mt-3 text-forest-200 leading-relaxed">
            Vaulta's only incentive is to make you understand your money. We make money when you pay us ₹99/month. Not when we sell your data. Not when you take a loan.
          </p>
        </div>

        {/* Comparison */}
        <div className="mt-10 grid sm:grid-cols-2 gap-4">
          <div className="card-glass p-5 rounded-xl border border-danger/20">
            <p className="text-danger text-xs font-semibold uppercase tracking-widest mb-4">Other apps</p>
            <ul className="space-y-2.5">
              {[
                'Require a credit card or neo-bank account',
                'Show pie charts, not actual insights',
                'Push loans and credit products',
                'Make money selling your financial profile',
                "Don't understand Indian banks or UPI",
              ].map(t => (
                <li key={t} className="flex items-start gap-2.5 text-forest-200 text-sm">
                  <span className="text-danger mt-0.5 shrink-0">✗</span> {t}
                </li>
              ))}
            </ul>
          </div>
          <div className="card-glass p-5 rounded-xl border border-forest-400/30">
            <p className="text-forest-200 text-xs font-semibold uppercase tracking-widest mb-4">Vaulta</p>
            <ul className="space-y-2.5">
              {[
                'Works with any Indian bank, UPI, or debit card',
                'AI that reasons about your money, not just reports',
                'Zero loans, zero upselling, zero agenda',
                'Flat subscription — we earn when you pay us',
                'Built for India: Hinglish, UPI, AA framework',
              ].map(t => (
                <li key={t} className="flex items-start gap-2.5 text-forest-100 text-sm">
                  <span className="text-forest-300 mt-0.5 shrink-0">✓</span> {t}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <div className="border-t border-white/5" />

      {/* Features */}
      <section className="max-w-6xl mx-auto px-5 py-20">
        <div className="mb-12">
          <p className="label-dark mb-3">What it does</p>
          <h2 className="font-display text-3xl sm:text-4xl font-light text-cream-100">
            Everything your money needs.
          </h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f, i) => (
            <div key={f.title}
              className="card-glass p-5 rounded-xl hover:border-forest-500/40 transition-all duration-300 animate-fade-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <span className="text-2xl mb-3 block">{f.icon}</span>
              <p className="text-cream-100 font-semibold text-sm mb-1.5">{f.title}</p>
              <p className="text-forest-200 text-sm leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="border-t border-white/5" />

      {/* Trust section */}
      <section className="max-w-6xl mx-auto px-5 py-20">
        <div className="mb-10">
          <p className="label-dark mb-3">Security & trust</p>
          <h2 className="font-display text-3xl font-light text-cream-100">
            Nothing to hide. Everything auditable.
          </h2>
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          {[
            { title: 'RBI-regulated pipeline', body: 'Bank data via Account Aggregator framework. You consent directly with your bank — we never see your login or OTP.' },
            { title: 'Open source data layer', body: 'The code that touches your data is publicly auditable on GitHub. The fact that there\'s nothing to hide is the trust signal.' },
            { title: 'Flat subscription only', body: '₹99/month when we charge. We make money when you pay us, not when we sell your data or push you a loan.' },
          ].map((t, i) => (
            <div key={i} className="card-glass p-5 rounded-xl">
              <div className="w-8 h-8 rounded-lg bg-forest-700/60 border border-forest-600/40 flex items-center justify-center mb-4">
                <div className="w-3 h-3 rounded-full border-2 border-forest-300" />
              </div>
              <p className="text-cream-200 font-semibold text-sm mb-2">{t.title}</p>
              <p className="text-forest-200 text-sm leading-relaxed">{t.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-6xl mx-auto px-5 py-16">
        <div className="card p-10 sm:p-16 text-center shadow-card">
          <p className="label mb-4">Get started today</p>
          <h2 className="font-display text-4xl sm:text-5xl font-light text-forest-900 leading-tight mb-4">
            Know where your<br />money actually goes.
          </h2>
          <p className="text-forest-600 max-w-sm mx-auto mb-8 text-sm leading-relaxed">
            Connect Gmail in 30 seconds. Get your first insight before you finish your chai.
          </p>
          <button
            onClick={() => navigate('/login')}
            className="btn-primary !px-8 !py-3.5 text-base inline-flex items-center gap-2"
          >
            Start for free
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
          <p className="text-forest-500 text-xs mt-4">
            Free during beta · No credit card required · Built by Kanveer Madan, VIPS Delhi
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 py-8">
        <div className="max-w-6xl mx-auto px-5 flex items-center justify-between">
          <span className="font-display text-lg font-light text-forest-400">Vaulta</span>
          <p className="text-forest-600 text-xs">
            Personal Finance AI for India · Built by Kanveer Madan
          </p>
        </div>
      </footer>
    </div>
  )
}