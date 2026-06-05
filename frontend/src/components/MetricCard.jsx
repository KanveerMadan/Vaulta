import clsx from 'clsx'

export default function MetricCard({ label, value, icon, trend, trendUp, positive }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-t3 text-xs">{label}</span>
        <span className="text-t3">{icon}</span>
      </div>
      <div>
        <p className="text-t1 text-xl font-semibold font-mono tracking-tight">
          ₹{value.toLocaleString('en-IN')}
        </p>
        {trend && (
          <p className={clsx('text-xs mt-1', positive ? 'text-positive' : trendUp ? 'text-negative' : 'text-t3')}>
            {trend}
          </p>
        )}
      </div>
    </div>
  )
}