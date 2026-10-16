import { useState } from "react";
import api from "../lib/api";
import { CATEGORIES } from "../lib/categories";
import { rupees, useApi } from "../lib/format";
import BudgetBars from "../components/BudgetBars";

// Budgets are for spending categories; transfers and people are tracked elsewhere
const BUDGET_CATEGORIES = CATEGORIES.filter((c) => !["Transfers", "Received from People"].includes(c));
const OVERALL = "__overall__";

function LimitInput({ label, budget, spent, onSave, onRemove }) {
  const [value, setValue] = useState(budget ? String(Number(budget.monthly_limit)) : "");
  const [error, setError] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    try { await onSave(value.trim()); setError(null); } catch { setError("Enter a positive amount."); }
  };
  return (
    <form onSubmit={save} className="flex items-center gap-2 py-2 border-b border-sage-50 last:border-0 flex-wrap">
      <span className="text-sm text-ink-800 flex-1 min-w-[10rem]">{label}</span>
      <span className="text-xs text-ink-400 w-28 text-right">spent {rupees(spent)}</span>
      <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" placeholder="No limit"
        pattern="\d{1,10}(\.\d{1,2})?" aria-label={`${label} monthly limit`}
        className="w-28 border border-sage-200 rounded-lg px-2 py-1 text-sm" />
      <button type="submit" disabled={!value.trim() || (budget && String(Number(budget.monthly_limit)) === value.trim())}
        className="text-xs px-2 py-1 rounded bg-forest-50 text-forest-700 disabled:opacity-40">{budget ? "Update" : "Set"}</button>
      {budget && <button type="button" onClick={onRemove} className="text-xs text-ink-400 hover:text-danger">Remove</button>}
      {error && <span className="text-xs text-danger w-full">{error}</span>}
    </form>
  );
}

export default function Budgets() {
  const [refreshKey, setRefreshKey] = useState(0);
  const budgets = useApi("/api/budgets", refreshKey);
  const summary = useApi("/api/transactions/summary?period=month", refreshKey);
  const reload = () => setRefreshKey((k) => k + 1);

  if (budgets.error || summary.error) return <div className="card p-5 text-sm text-danger">Couldn't load budgets.</div>;
  if (!budgets.data || !summary.data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;

  const byCategory = Object.fromEntries(budgets.data.items.map((b) => [b.category ?? OVERALL, b]));
  const spent = Object.fromEntries(summary.data.categories.map((c) => [c.category, Number(c.total)]));
  const totalSpent = Number(summary.data.total_spend);

  const save = async (category, limit) => {
    const existing = byCategory[category ?? OVERALL];
    if (existing) await api.patch(`/api/budgets/${existing.id}`, { monthly_limit: limit });
    else await api.post("/api/budgets", { category, monthly_limit: limit });
    reload();
  };
  const remove = async (category) => {
    await api.delete(`/api/budgets/${byCategory[category ?? OVERALL].id}`);
    reload();
  };

  const bars = budgets.data.items.map((b) => ({
    category: b.category ?? "Overall",
    spent: b.category ? (spent[b.category] ?? 0) : totalSpent,
    limit: Number(b.monthly_limit),
  }));

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div>
        <h1 className="font-display text-display-s text-ink">Budgets</h1>
        <p className="text-sm text-ink-500 mt-1">
          Monthly limits. Spending here is real spending only: transfers, failed payments and money lent don't count,
          and refunds are subtracted.
        </p>
      </div>
      {bars.length > 0 && <section className="card p-5"><BudgetBars rows={bars} /></section>}
      <section className="card p-5">
        <LimitInput label="Overall monthly cap" budget={byCategory[OVERALL]} spent={totalSpent}
          onSave={(v) => save(null, v)} onRemove={() => remove(null)} />
        {BUDGET_CATEGORIES.map((c) => (
          <LimitInput key={`${c}-${byCategory[c]?.monthly_limit ?? ""}`} label={c} budget={byCategory[c]} spent={spent[c] ?? 0}
            onSave={(v) => save(c, v)} onRemove={() => remove(c)} />
        ))}
      </section>
    </div>
  );
}
