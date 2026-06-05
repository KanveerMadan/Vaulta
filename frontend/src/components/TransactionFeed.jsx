import clsx from 'clsx'

export default function TransactionFeed({ transactions }) {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex justify-between items-center">
        <h3 className="text-t1 text-sm font-medium">Recent transactions</h3>
        <span className="text-t3 text-xs">Last 30 days</span>
      </div>
      <div className="divide-y divide-border">
        {transactions.map((tx) => (
          <div key={tx.id} className="px-5 py-3.5 flex items-center gap-3 hover:bg-elevated/50 transition-colors">
            <div className="w-9 h-9 rounded-xl bg-elevated flex items-center justify-center text-base shrink-0">
              {tx.icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-t1 text-sm font-medium truncate">{tx.merchant}</p>
              <p className="text-t3 text-xs">{tx.category} · {tx.time}</p>
            </div>
            <span className={clsx(
              'text-sm font-mono font-medium shrink-0',
              tx.amount > 0 ? 'text-positive' : 'text-t1'
            )}>
              {tx.amount > 0 ? '+' : ''}₹{Math.abs(tx.amount).toLocaleString('en-IN')}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}