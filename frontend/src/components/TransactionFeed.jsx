import clsx from 'clsx'

export default function TransactionFeed({ transactions }) {
  return (
    <div className="card shadow-card overflow-hidden">
      <div className="px-5 py-4 border-b border-cream-300 flex items-center justify-between">
        <p className="text-forest-900 font-semibold text-sm">Recent transactions</p>
        <span className="text-forest-400 text-xs">Last 30 days</span>
      </div>
      <div className="divide-y divide-cream-200">
        {transactions.map((tx, i) => (
          <div key={tx.id}
            className="px-5 py-3.5 flex items-center gap-4 hover:bg-cream-100 transition-colors duration-150 animate-fade-in"
            style={{ animationDelay: `${i * 35}ms` }}
          >
            <div className="w-9 h-9 rounded-lg bg-cream-200 border border-cream-300 flex items-center justify-center text-sm shrink-0">
              {tx.icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-forest-900 text-sm font-medium truncate">{tx.merchant}</p>
              <p className="text-forest-400 text-xs mt-0.5">{tx.category} · {tx.time}</p>
            </div>
            <span className={clsx(
              'text-sm font-mono font-medium shrink-0 tabular-nums',
              tx.amount > 0 ? 'text-safe' : 'text-forest-800'
            )}>
              {tx.amount > 0 ? '+' : '−'}₹{Math.abs(tx.amount).toLocaleString('en-IN')}
            </span>
          </div>
        ))}
      </div>
      <div className="px-5 py-3 border-t border-cream-200 bg-cream-100/50">
        <button className="text-forest-500 hover:text-forest-800 text-xs font-medium transition-colors">
          View all transactions →
        </button>
      </div>
    </div>
  )
}