/** Placeholder shaped like the content that is loading. */
export function SkeletonLines({ lines = 3, className = '' }) {
  return (
    <div className={`space-y-3 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton h-4" style={{ width: `${92 - i * 14}%` }} />)}
    </div>
  )
}

export function SkeletonRows({ rows = 5 }) {
  return (
    <div className="divide-y divide-line" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 py-3">
          <div className="skeleton w-9 h-9 rounded-sm" />
          <div className="flex-1 space-y-2"><div className="skeleton h-3.5 w-2/5" /><div className="skeleton h-3 w-1/4" /></div>
          <div className="skeleton h-4 w-16" />
        </div>
      ))}
    </div>
  )
}
