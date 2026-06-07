import { useEffect, useState } from 'react'
import { useFinanceStore } from '../store/financeStore'
import { useAuthStore } from '../store/authStore'
import { Link } from 'react-router-dom'
import SpendChart from '../components/SpendChart'
import TransactionFeed from '../components/TransactionFeed'
import InsightCard from '../components/InsightCard'

const MOCK_SUMMARY = { spent: 24800, budgetLeft: 15200, predicted: 8400, budget: 40000 }

const MOCK_CATEGORIES = [
  { name: 'Food & Delivery', amount: 9200,  pct: 37, color: '#2D6A4F' },
  { name: 'Shopping',        amount: 7400,  pct: 30, color: '#4A9955' },
  { name: 'Transport',       amount: 3100,  pct: 13, color: '#6DB87A' },
  { name: 'Subscriptions',   amount: 2840,  pct: 11, color: '#B5852A' },
  { name: 'Other',           amount: 2260,  pct: 9,  color: '#B8CFC0' },
]

const MOCK_TXN = [
  { id:1, merchant:'Zomato',   category:'Food',         amount:-349,   time:'2h ago',  icon:'🍕' },
  { id:2, merchant:'Salary',   category:'Income',       amount:40000,  time:'2d ago',  icon:'💰' },
  { id:3, merchant:'Swiggy',   category:'Food',         amount:-180,   time:'3d ago',  icon:'🛵' },
  { id:4, merchant:'Uber',     category:'Transport',    amount:-220,   time:'4d ago',  icon:'🚗' },
  { id:5, merchant:'Netflix',  category:'Subscription', amount:-649,   time:'5d ago',  icon:'📺' },
  { id:6, merchant:'Amazon',   category:'Shopping',     amount:-1299,  time:'6d ago',  icon:'📦' },
  { id:7, merchant:'IRCTC',    category:'Travel',       amount:-2100,  time:'1w ago',  icon:'🚆' },
]

function useCountUp(target, duration = 1200) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    let start = 0
    const step = target / (duration / 16)
    const timer = setInterval(() => {
      start += step
      if (start >= target) { setValue(target); clearInterval(timer) }
      else setValue(Math.floor(start))
    }, 16)
    return () => clearInterval(timer)
  }, [target])
  return value
}

function MetricCard({ label, value, sub, subColor, progress, delay = 0 }) {
  const count = useCountUp(value)
  const pctColor = progress > 80 ? '#C0392B' : '#2D6A4F'

  return (
    <div className="card p-5 animate-fade-up" style={{ animationDelay: `${delay}ms` }}>
      <p className="label mb-3">{label}</p>
      <p className="font-display tracking-tight tabular-nums"
        style={{ fontSize: '1.875rem', fontWeight: 300, color: '#1A2E1E', lineHeight: 1 }}>
        ₹{count.toLocaleString('en-IN')}
      </p>
      {progress !== undefined && (
        <div className="mt-3 rounded-full overflow-hidden" style={{ height: '3px', background: '#E8F0EA' }}>
          <div className="h-full rounded-full transition-all duration-1000 ease-out"
            style={{ width: `${Math.min(progress, 100)}%`, background: pctColor }} />
        </div>
      )}
      {sub && (
        <p className="text-xs mt-2" style={{ color: subColor || '#7A9E80' }}>{sub}</p>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuthStore()
  const { setSummary, setCategorySpend } = useFinanceStore()

  useEffect(() => {
    setSummary(MOCK_SUMMARY)
    setCategorySpend(MOCK_CATEGORIES)
  }, [])

  const firstName = user?.displayName?.split(' ')[0] || user?.email?.split('@')[0] || 'there'
  const budgetPct = Math.round((MOCK_SUMMARY.spent / MOCK_SUMMARY.budget) * 100)
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between animate-fade-up">
        <div>
          <h1 className="font-display font-light tracking-tight"
            style={{ fontSize: '1.625rem', color: '#1A2E1E' }}>
            {greeting}, {firstName}
          </h1>
          <p className="text-sm mt-0.5" style={{ color: '#7A9E80' }}>
            {new Date().toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })} ·{' '}
            {new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate() - new Date().getDate()} days remaining
          </p>
        </div>
        <Link to="/connect"
          className="btn-ghost hidden sm:flex items-center gap-2 text-xs">
          Connect accounts
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
          </svg>
        </Link>
      </div>

      {/* Demo banner */}
      <div className="card-subtle rounded-xl px-4 py-3 flex items-center justify-between gap-4 animate-fade-up delay-75"
        style={{ background: '#FFFBEB', border: '1px solid #FDE68A' }}>
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full animate-pulse shrink-0" style={{ background: '#B5852A' }} />
          <div>
            <p className="text-sm font-medium" style={{ color: '#92400E' }}>Showing demo data</p>
            <p className="text-xs" style={{ color: '#B45309' }}>Connect Gmail or bank SMS to see your real spending</p>
          </div>
        </div>
        <Link to="/connect" className="btn-primary !py-1.5 !px-3 !text-xs shrink-0 whitespace-nowrap">
          Connect now
        </Link>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <MetricCard label="Spent this month" value={24800}
          sub={`${budgetPct}% of ₹40,000 budget`}
          subColor={budgetPct > 80 ? '#C0392B' : '#7A9E80'}
          progress={budgetPct} delay={100} />
        <MetricCard label="Remaining budget" value={15200}
          sub="₹543/day left to spend" subColor="#2D6A4F" delay={175} />
        <MetricCard label="Predicted month-end" value={8400}
          sub="Based on current velocity" delay={250} />
      </div>

      {/* Chart + Insight */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 animate-fade-up delay-300">
          <SpendChart data={MOCK_CATEGORIES} />
        </div>
        <div className="lg:col-span-2 animate-fade-up delay-375">
          <InsightCard />
        </div>
      </div>

      {/* Transactions */}
      <div className="animate-fade-up" style={{ animationDelay: '400ms' }}>
        <TransactionFeed transactions={MOCK_TXN} />
      </div>
    </div>
  )
}