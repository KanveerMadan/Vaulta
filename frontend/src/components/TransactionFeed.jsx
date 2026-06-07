import clsx from 'clsx'

export default function TransactionFeed({ transactions }) {
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-forest-700 flex items-center justify-between">
        <p className="font-medium text-cream-200 text-sm">Recent transactions</p>
        <span className="text-forest-500 text-xs">Last 30 days</span>
      </div>
      <div className="divide-y divide-forest-800">
        {transactions.map((tx, i) => (
          <div
            key={tx.id}
            className="px-5 py-3.5 flex items-center gap-4 hover:bg-forest-800/40 transition-colors"
            style={{ animationDelay: `${i * 0.04}s` }}
          >
            <div className="w-9 h-9 rounded-lg bg-forest-800 border border-forest-700 flex items-center justify-center text-sm shrink-0">
              {tx.icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-cream-200 text-sm font-medium truncate">{tx.merchant}</p>
              <p className="text-forest-400 text-xs mt-0.5">{tx.category} · {tx.time}</p>
            </div>
            <span className={clsx(
              'text-sm font-mono font-medium shrink-0 tabular-nums',
              tx.amount > 0 ? 'text-safe' : 'text-cream-300'
            )}>
              {tx.amount > 0 ? '+' : '−'}₹{Math.abs(tx.amount).toLocaleString('en-IN')}
            </span>
          </div>
        ))}
      </div>
      <div className="px-5 py-3 border-t border-forest-800">
        <button className="text-forest-300 hover:text-cream-200 text-xs transition-colors">
          View all transactions →
        </button>
      </div>
    </div>
  )
}