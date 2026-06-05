import { useEffect } from 'react'
import { useFinanceStore } from '../store/financeStore'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import MetricCard from '../components/MetricCard'
import SpendChart from '../components/SpendChart'
import TransactionFeed from '../components/TransactionFeed'
import InsightCard from '../components/InsightCard'
import { TrendingUp, Wallet, Calendar } from 'lucide-react'
import { Link } from 'react-router-dom'

// Mock data — replace with real API calls in Phase 1
const MOCK_SUMMARY = {
  spentThisMonth: 24800,
  budgetLeft: 15200,
  predictedBalance: 8400,
}

const MOCK_CATEGORIES = [
  { name: 'Food', amount: 9200,  color: '#6C63FF', max: 15000 },
  { name: 'Transport', amount: 3100, color: '#10B981', max: 8000 },
  { name: 'Shopping', amount: 7400, color: '#F59E0B', max: 10000 },
  { name: 'Subscriptions', amount: 2840, color: '#F43F5E', max: 5000 },
  { name: 'Other', amount: 2260, color: '#8888AA', max: 5000 },
]

const MOCK_TRANSACTIONS = [
  { id: 1, merchant: 'Zomato', category: 'Food', amount: -349, time: '2h ago', icon: '🍕' },
  { id: 2, merchant: 'Salary', category: 'Income', amount: 40000, time: '2d ago', icon: '💰' },
  { id: 3, merchant: 'Swiggy', category: 'Food', amount: -180, time: '3d ago', icon: '🛵' },
  { id: 4, merchant: 'Uber', category: 'Transport', amount: -220, time: '3d ago', icon: '🚗' },
  { id: 5, merchant: 'Netflix', category: 'Subscriptions', amount: -649, time: '5d ago', icon: '📺' },
  { id: 6, merchant: 'Amazon', category: 'Shopping', amount: -1299, time: '6d ago', icon: '📦' },
]

export default function Dashboard() {
  const { user } = useAuthStore()
  const { setSummary, setCategorySpend } = useFinanceStore()

  useEffect(() => {
    // Will replace with real API calls in Phase 1
    setSummary(MOCK_SUMMARY)
    setCategorySpend(MOCK_CATEGORIES)
  }, [])

  const firstName = user?.displayName?.split(' ')[0] || 'there'

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Greeting */}
      <div>
        <h1 className="text-xl font-semibold text-t1">Hey, {firstName} 👋</h1>
        <p className="text-t3 text-sm mt-0.5">Here's your money picture for June 2025</p>
      </div>

      {/* No data connected yet banner */}
      <NoDataBanner />

      {/* Metric cards */}
      <div className="grid grid-cols-3 gap-3">
        <MetricCard
          label="Spent this month"
          value={24800}
          icon={<TrendingUp size={14} />}
          trend="+12% vs last month"
          trendUp
        />
        <MetricCard
          label="Left to spend"
          value={15200}
          icon={<Wallet size={14} />}
          trend="of ₹40,000 budget"
          positive
        />
        <MetricCard
          label="Predicted end"
          value={8400}
          icon={<Calendar size={14} />}
          trend="by Jun 30"
        />
      </div>

      {/* Insight + Spend chart */}
      <div className="grid grid-cols-5 gap-3">
        <div className="col-span-3">
          <SpendChart data={MOCK_CATEGORIES} />
        </div>
        <div className="col-span-2">
          <InsightCard />
        </div>
      </div>

      {/* Recent transactions */}
      <TransactionFeed transactions={MOCK_TRANSACTIONS} />
    </div>
  )
}

function NoDataBanner() {
  return (
    <div className="bg-brand-dim border border-brand/20 rounded-xl px-4 py-3 flex items-center justify-between">
      <div>
        <p className="text-brand text-sm font-medium">Connect your accounts to see real data</p>
        <p className="text-t3 text-xs mt-0.5">Currently showing demo data</p>
      </div>
      <Link
        to="/connect"
        className="text-xs bg-brand hover:bg-brand-light text-white px-3 py-1.5 rounded-lg font-medium transition-all active:scale-95 whitespace-nowrap"
      >
        Connect →
      </Link>
    </div>
  )
}