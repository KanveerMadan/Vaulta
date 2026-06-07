export default function SpendChart({ data }) {
  const max = Math.max(...data.map(d => d.amount))
  const total = data.reduce((s, d) => s + d.amount, 0)

  return (
    <div className="card p-5 h-full">
      <div className="flex items-center justify-between mb-5">
        <p className="font-medium text-cream-200 text-sm">Spending breakdown</p>
        <p className="text-forest-400 text-xs">₹{total.toLocaleString('en-IN')} total</p>
      </div>
      <div className="space-y-4">
        {data.map((item) => (
          <div key={item.name}>
            <div className="flex justify-between items-center mb-1.5">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: item.color }} />
                <span className="text-forest-100 text-sm">{item.name}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-forest-400 text-xs">{item.pct}%</span>
                <span className="text-cream-200 text-sm font-mono font-medium">
                  ₹{item.amount.toLocaleString('en-IN')}
                </span>
              </div>
            </div>
            <div className="h-1.5 bg-forest-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{ width: `${(item.amount / max) * 100}%`, backgroundColor: item.color }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}