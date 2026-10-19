import { rupees } from "../lib/format";

/** Spent vs limit per category. `rows`: [{category, spent, limit}] (numbers). */
export default function BudgetBars({ rows }) {
  return (
    <div className="space-y-3">
      {rows.map(({ category, spent, limit }) => {
        const pct = limit > 0 ? (spent / limit) * 100 : 0;
        const over = spent > limit;
        return (
          <div key={category} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-ink-700 font-medium">{category}</span>
              <span className={over ? "text-danger font-medium" : "text-ink-500"}>
                {rupees(spent)} / {rupees(limit)}{over ? ` · over by ${rupees(spent - limit)}` : ""}
              </span>
            </div>
            <div className="h-1.5 bg-sage-100 rounded-full overflow-hidden" role="progressbar"
              aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={`${category} budget`}>
              <div className={`h-full rounded-full ${over ? "bg-danger" : pct > 80 ? "bg-gold" : "bg-forest-500"}`}
                style={{ width: `${Math.min(pct, 100)}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
