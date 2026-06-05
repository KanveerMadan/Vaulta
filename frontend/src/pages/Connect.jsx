import { useState } from 'react'
import { Mail, MessageSquare, Building2, FileUp, CheckCircle2, ChevronRight } from 'lucide-react'
import clsx from 'clsx'

const SOURCES = [
  {
    id: 'gmail',
    icon: <Mail size={18} />,
    title: 'Gmail',
    description: 'Order confirmations from Swiggy, Zomato, Amazon, Flipkart',
    phase: 'Connect now',
    available: true,
    color: '#6C63FF',
  },
  {
    id: 'sms',
    icon: <MessageSquare size={18} />,
    title: 'Bank SMS',
    description: 'Real-time transaction alerts from any bank via WhatsApp bot',
    phase: 'Connect now',
    available: true,
    color: '#10B981',
  },
  {
    id: 'aa',
    icon: <Building2 size={18} />,
    title: 'Account Aggregator',
    description: 'Full bank history — RBI regulated, read-only, 50+ banks',
    phase: 'Coming in Phase 5',
    available: false,
    color: '#F59E0B',
  },
  {
    id: 'csv',
    icon: <FileUp size={18} />,
    title: 'UPI CSV / Statement',
    description: 'Upload GPay/PhonePe CSV or credit card PDF',
    phase: 'Coming soon',
    available: false,
    color: '#8888AA',
  },
]

export default function Connect() {
  const [connected, setConnected] = useState({})

  const handleConnect = (id) => {
    // Real OAuth flows go here in Phase 1
    setConnected((prev) => ({ ...prev, [id]: true }))
  }

  return (
    <div className="space-y-6 animate-fade-up max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-t1">Connect your accounts</h1>
        <p className="text-t3 text-sm mt-1">
          We earn the right to each data source separately. Start with Gmail — one jaw-dropping insight first.
        </p>
      </div>

      {/* Trust pill */}
      <div className="flex items-center gap-2 bg-positive/10 border border-positive/20 rounded-xl px-4 py-2.5 w-fit">
        <div className="w-1.5 h-1.5 rounded-full bg-positive animate-pulse" />
        <p className="text-positive text-xs font-medium">
          We never see your bank login, password, or UPI PIN — architecturally impossible
        </p>
      </div>

      {/* Sources */}
      <div className="space-y-3">
        {SOURCES.map((source) => (
          <div
            key={source.id}
            className={clsx(
              'bg-card border rounded-2xl p-4 flex items-center gap-4 transition-all',
              source.available ? 'border-border hover:border-t3' : 'border-border opacity-50'
            )}
          >
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
              style={{ backgroundColor: `${source.color}18`, color: source.color }}
            >
              {source.icon}
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-t1 text-sm font-medium">{source.title}</p>
              <p className="text-t3 text-xs mt-0.5 leading-relaxed">{source.description}</p>
            </div>

            {connected[source.id] ? (
              <div className="flex items-center gap-1.5 text-positive text-xs font-medium shrink-0">
                <CheckCircle2 size={14} />
                Connected
              </div>
            ) : source.available ? (
              <button
                onClick={() => handleConnect(source.id)}
                className="flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-light transition-colors shrink-0"
              >
                Connect <ChevronRight size={13} />
              </button>
            ) : (
              <span className="text-xs text-t3 shrink-0">{source.phase}</span>
            )}
          </div>
        ))}
      </div>

      {/* What we see / don't see */}
      <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
        <h3 className="text-t1 text-sm font-medium">What Vaulta can and cannot see</h3>
        <div className="space-y-2">
          {[
            { can: true,  text: 'Order confirmation emails from Swiggy, Zomato, Amazon' },
            { can: true,  text: 'Bank SMS messages you have forwarded' },
            { can: false, text: 'Your Gmail inbox — we cannot read other emails' },
            { can: false, text: 'Your bank login credentials — we never ask' },
            { can: false, text: 'Your UPI PIN — technically impossible for us to see' },
          ].map((item, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <span className={clsx('text-xs mt-0.5', item.can ? 'text-positive' : 'text-negative')}>
                {item.can ? '✓' : '✗'}
              </span>
              <span className="text-t2 text-xs leading-relaxed">{item.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}