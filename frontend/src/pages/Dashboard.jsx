import { useEffect } from 'react'
import { useFinanceStore } from '../store/financeStore'
import { useAuthStore } from '../store/authStore'
import { Link } from 'react-router-dom'
import MetricCard from '../components/MetricCard'
import SpendChart from '../components/SpendChart'
import TransactionFeed from '../components/TransactionFeed'
import InsightCard from '../components/InsightCard'

const MOCK_SUMMARY = { spent: 24800, budgetLeft: 15200, predicted: 8400, budget: 40000 }

const MOCK_CATEGORIES = [
  { name: 'Food & Delivery', amount: 9200,  pct: 37, color: '#4A9955' },
  { name: 'Shopping',        amount: 7400,  pct: 30, color: '#A8D9B0' },
  { name: 'Transport',       amount: 3100,  pct: 13, color: '#6DB87A' },
  { name: 'Subscriptions',   amount: 2840,  pct: 11, color: '#C9A84C' },
  { name: 'Other',           amount: 2260,  pct: 9,  color: '#27602F' },
]

const MOCK_TXN = [
  { id:1, merchant:'Zomato',   category:'Food',          amount:-349,   time:'2h ago',   icon:'🍕' },
  { id:2, merchant:'Salary',   category:'Income',        amount:40000,  time:'2d ago',   icon:'💰' },
  { id:3, merchant:'Swiggy',   category:'Food',          amount:-180,   time:'3d ago',   icon:'🛵' },
  { id:4, merchant:'Uber',     category:'Transport',     amount:-220,   time:'4d ago',   icon:'🚗' },
  { id:5, merchant:'Netflix',  category:'Subscription',  amount:-649,   time:'5d ago',   icon:'📺' },
  { id:6, merchant:'Amazon',   category:'Shopping',      amount:-1299,  time:'6d ago',   icon:'📦' },
  { id:7, merchant:'IRCTC',    category:'Travel',        amount:-2100,  time:'1w ago',   icon:'🚆' },
]

export default function Dashboard() {
  const { user } = useAuthStore()
  const { setSummary, setCategorySpend, summaryLoading } = useFinanceStore()

  useEffect(() => {
    setSummary(MOCK_SUMMARY)
    setCategorySpend(MOCK_CATEGORIES)
  }, [])

  const firstName = user?.displayName?.split(' ')[0] || user?.email?.split('@')[0] || 'there'
  const budgetPct = Math.round((MOCK_SUMMARY.spent / MOCK_SUMMARY.budget) * 100)

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-2xl font-light text-cream-100 tracking-tight">
            Good evening, {firstName}
          </h1>
          <p className="text-forest-300 text-sm mt-1">June 2025 · 14 days remaining</p>
        </div>
        <Link to="/connect" className="btn-ghost hidden sm:inline-flex items-center gap-2 text-xs">
          Connect accounts
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
          </svg>
        </Link>
      </div>

      {/* Connect banner */}
      <div className="card p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-gold animate-pulse" />
          <div>
            <p className="text-cream-200 text-sm font-medium">Showing demo data</p>
            <p className="text-forest-400 text-xs mt-0.5">Connect Gmail or bank SMS to see your real spending</p>
          </div>
        </div>
        <Link to="/connect" className="btn-primary shrink-0 !py-2 !px-4 text-xs">Connect now</Link>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <MetricCard
          label="Spent this month"
          value={24800}
          sub={`${budgetPct}% of ₹40,000 budget`}
          subColor={budgetPct > 80 ? 'text-danger' : 'text-forest-300'}
          progress={budgetPct}
        />
        <MetricCard
          label="Remaining budget"
          value={15200}
          sub="₹540/day left to spend"
          subColor="text-safe"
        />
        <MetricCard
          label="Predicted month-end"
          value={8400}
          sub="Based on current velocity"
          subColor="text-forest-400"
        />
      </div>

      {/* Chart + Insight */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3">
          <SpendChart data={MOCK_CATEGORIES} />
        </div>
        <div className="lg:col-span-2">
          <InsightCard />
        </div>
      </div>

      {/* Transactions */}
      <TransactionFeed transactions={MOCK_TXN} />
    </div>
  )
}