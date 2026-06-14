// ─────────────────────────────────────────────
// Skeleton loading components
// Uses the .skeleton CSS primitive from index.css
// ─────────────────────────────────────────────

export function SkeletonMetricCard() {
  return (
    <div className="card p-5 space-y-3">
      <div className="skeleton h-3 w-24 rounded" />
      <div className="skeleton h-8 w-32 rounded" />
      <div className="skeleton h-2 w-full rounded" />
      <div className="skeleton h-3 w-20 rounded" />
    </div>
  );
}

export function SkeletonChart() {
  return (
    <div className="card p-5 space-y-4">
      <div className="skeleton h-3 w-32 rounded" />
      <div className="flex items-end gap-2 h-36">
        {[60, 85, 40, 95, 55, 70, 45].map((h, i) => (
          <div
            key={i}
            className="skeleton flex-1 rounded-t"
            style={{ height: `${h}%` }}
          />
        ))}
      </div>
      <div className="flex gap-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className="skeleton h-2.5 w-2.5 rounded-full" />
            <div className="skeleton h-2 w-14 rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonTransactionFeed() {
  return (
    <div className="card p-5 space-y-4">
      <div className="skeleton h-3 w-28 rounded" />
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex items-center gap-3 py-1">
          <div className="skeleton h-9 w-9 rounded-full shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3 w-28 rounded" />
            <div className="skeleton h-2 w-16 rounded" />
          </div>
          <div className="skeleton h-3 w-16 rounded" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonInsightCard() {
  return (
    <div className="card p-5 space-y-3">
      <div className="skeleton h-3 w-20 rounded" />
      <div className="skeleton h-4 w-full rounded" />
      <div className="skeleton h-4 w-3/4 rounded" />
      <div className="skeleton h-3 w-24 rounded" />
    </div>
  );
}