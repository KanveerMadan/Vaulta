export default function MetricCard({ label, value, sub, subColor = 'text-forest-400', progress }) {
  return (
    <div className="card p-5 space-y-3">
      <p className="label">{label}</p>
      <p className="font-display text-3xl font-light text-cream-100 tracking-tight">
        ₹{value.toLocaleString('en-IN')}
      </p>
      {progress !== undefined && (
        <div className="h-1 bg-forest-700 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(progress, 100)}%`,
              backgroundColor: progress > 80 ? '#C0392B' : '#4A9955',
            }}
          />
        </div>
      )}
      {sub && <p className={`text-xs ${subColor}`}>{sub}</p>}
    </div>
  )
}