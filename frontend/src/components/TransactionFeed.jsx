export default function TransactionFeed({ transactions }) {
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid #E8F0EA' }}>
        <p className="font-semibold text-sm" style={{ color: '#1A2E1E' }}>Recent transactions</p>
        <span className="text-xs" style={{ color: '#8FAF98' }}>Last 30 days</span>
      </div>

      <div>
        {transactions.map((tx, i) => (
          <div key={tx.id}
            className="px-5 py-3.5 flex items-center gap-4 transition-colors duration-150 animate-fade-in"
            style={{
              borderBottom: i < transactions.length - 1 ? '1px solid #F2F7F3' : 'none',
              animationDelay: `${i * 35}ms`,
            }}
            onMouseEnter={e => e.currentTarget.style.background = '#F2F7F3'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <div className="w-9 h-9 rounded-lg flex items-center justify-center text-sm shrink-0"
              style={{ background: '#F2F7F3', border: '1px solid #E8F0EA' }}>
              {tx.icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate" style={{ color: '#1A2E1E' }}>{tx.merchant}</p>
              <p className="text-xs mt-0.5" style={{ color: '#8FAF98' }}>{tx.category} · {tx.time}</p>
            </div>
            <span className="text-sm font-mono font-medium shrink-0 tabular-nums"
              style={{ color: tx.amount > 0 ? '#2D6A4F' : '#1A2E1E' }}>
              {tx.amount > 0 ? '+' : '−'}₹{Math.abs(tx.amount).toLocaleString('en-IN')}
            </span>
          </div>
        ))}
      </div>

      <div className="px-5 py-3" style={{ borderTop: '1px solid #E8F0EA', background: '#F9FBF9' }}>
        <button className="text-xs font-medium transition-colors"
          style={{ color: '#8FAF98' }}
          onMouseEnter={e => e.currentTarget.style.color = '#2D6A4F'}
          onMouseLeave={e => e.currentTarget.style.color = '#8FAF98'}>
          View all transactions →
        </button>
      </div>
    </div>
  )
}