export default function SpendChart({ data }) {
  const max = Math.max(...data.map(d => d.amount))
  const total = data.reduce((s, d) => s + d.amount, 0)

  return (
    <div className="card p-5 h-full">
      <div className="flex items-center justify-between mb-5">
        <p className="font-semibold text-sm" style={{ color: '#1A2E1E' }}>Spending breakdown</p>
        <p className="text-xs font-mono" style={{ color: '#7A9E80' }}>
          ₹{total.toLocaleString('en-IN')} this month
        </p>
      </div>

      <div className="flex items-center gap-6 mb-5">
        {/* Donut */}
        <svg width="84" height="84" viewBox="0 0 84 84" className="shrink-0">
          <circle cx="42" cy="42" r="34" fill="none" stroke="#E8F0EA" strokeWidth="10" />
          {(() => {
            let offset = 0
            const r = 34, c = 2 * Math.PI * r
            return data.map(item => {
              const dash = (item.pct / 100) * c
              const el = (
                <circle key={item.name} cx="42" cy="42" r={r}
                  fill="none" stroke={item.color} strokeWidth="10"
                  strokeDasharray={`${dash - 1} ${c - dash + 1}`}
                  strokeDashoffset={-offset}
                  strokeLinecap="round"
                  style={{ transform: 'rotate(-90deg)', transformOrigin: '42px 42px', transition: 'all 1s ease' }}
                />
              )
              offset += dash
              return el
            })
          })()}
          <text x="42" y="39" textAnchor="middle" style={{ fontSize: '9px', fill: '#7A9E80', fontFamily: 'Instrument Sans' }}>total</text>
          <text x="42" y="51" textAnchor="middle" style={{ fontSize: '10px', fill: '#1A2E1E', fontFamily: 'JetBrains Mono', fontWeight: 500 }}>
            ₹{(total / 1000).toFixed(0)}k
          </text>
        </svg>

        {/* Legend */}
        <div className="flex-1 space-y-2">
          {data.map(item => (
            <div key={item.name} className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: item.color }} />
              <span className="text-xs flex-1 truncate" style={{ color: '#4A6B50' }}>{item.name}</span>
              <span className="text-xs font-medium" style={{ color: '#7A9E80' }}>{item.pct}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bars */}
      <div className="space-y-3 pt-4" style={{ borderTop: '1px solid #E8F0EA' }}>
        {data.map(item => (
          <div key={item.name}>
            <div className="flex justify-between items-center mb-1.5">
              <span className="text-xs" style={{ color: '#4A6B50' }}>{item.name}</span>
              <span className="text-xs font-mono font-medium" style={{ color: '#1A2E1E' }}>
                ₹{item.amount.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="rounded-full overflow-hidden" style={{ height: '4px', background: '#E8F0EA' }}>
              <div className="h-full rounded-full transition-all duration-1000 ease-out"
                style={{ width: `${(item.amount / max) * 100}%`, background: item.color }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}