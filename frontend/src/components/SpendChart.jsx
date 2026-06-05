export default function SpendChart({ data }) {
  const max = Math.max(...data.map((d) => d.amount))

  return (
    <div className="bg-card border border-border rounded-2xl p-5 h-full">
      <h3 className="text-t1 text-sm font-medium mb-4">Spending by category</h3>
      <div className="space-y-3">
        {data.map((item) => (
          <div key={item.name}>
            <div className="flex justify-between items-center mb-1.5">
              <span className="text-t2 text-xs">{item.name}</span>
              <span className="text-t1 text-xs font-mono">₹{item.amount.toLocaleString('en-IN')}</span>
            </div>
            <div className="h-1.5 bg-elevated rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{
                  width: `${(item.amount / max) * 100}%`,
                  backgroundColor: item.color,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}