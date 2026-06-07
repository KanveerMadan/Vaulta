export default function SpendChart({ data }) {
  const max = Math.max(...data.map(d => d.amount))
  const total = data.reduce((s, d) => s + d.amount, 0)

  return (
    <div className="card shadow-card p-5 h-full">
      <div className="flex items-center justify-between mb-5">
        <p className="text-forest-900 font-semibold text-sm">Spending breakdown</p>
        <p className="text-forest-500 text-xs font-mono">₹{total.toLocaleString('en-IN')}</p>
      </div>

      {/* Mini donut */}
      <div className="flex items-center gap-5 mb-5">
        <svg width="80" height="80" viewBox="0 0 80 80" className="shrink-0">
          {(() => {
            let offset = 0
            const r = 30, c = 2 * Math.PI * r
            return data.map((item) => {
              const dash = (item.pct / 100) * c
              const el = (
                <circle key={item.name} cx="40" cy="40" r={r}
                  fill="none" stroke={item.color} strokeWidth="12"
                  strokeDasharray={`${dash} ${c}`}
                  strokeDashoffset={-offset}
                  style={{ transform: 'rotate(-90deg)', transformOrigin: '40px 40px', transition: 'stroke-dasharray 1s ease' }}
                />
              )
              offset += dash
              return el
            })
          })()}
          <text x="40" y="38" textAnchor="middle" className="font-display" fontSize="10" fill="#27602F" fontWeight="300">spent</text>
          <text x="40" y="50" textAnchor="middle" fontSize="9" fill="#4A9955" fontFamily="JetBrains Mono">this month</text>
        </svg>

        <div className="flex-1 space-y-1.5">
          {data.map(item => (
            <div key={item.name} className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: item.color }} />
              <span className="text-forest-700 text-xs flex-1 truncate">{item.name}</span>
              <span className="text-forest-500 text-xs">{item.pct}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bars */}
      <div className="space-y-3 border-t border-cream-300 pt-4">
        {data.map((item) => (
          <div key={item.name}>
            <div className="flex justify-between items-center mb-1">
              <span className="text-forest-800 text-xs">{item.name}</span>
              <span className="text-forest-900 text-xs font-mono font-medium">
                ₹{item.amount.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="h-1.5 bg-cream-300 rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all duration-1000 ease-out"
                style={{ width: `${(item.amount / max) * 100}%`, backgroundColor: item.color }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}