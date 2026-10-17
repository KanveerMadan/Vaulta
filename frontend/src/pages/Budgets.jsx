import { useState } from "react";
import api from "../lib/api";
import { CATEGORIES, subcategoryName, useCategoryTree } from "../lib/categories";
import CategorySelect from "../components/CategorySelect";
import { rupees, useApi } from "../lib/format";
import BudgetBars from "../components/BudgetBars";

// Budgets are for spending categories; transfers and people are tracked elsewhere
const BUDGET_CATEGORIES = CATEGORIES.filter((c) => !["Transfers", "Received from People", "Income"].includes(c));
const SUB_GROUPS = BUDGET_CATEGORIES.filter((c) => !["Sent to People", "Misc cash", "Other"].includes(c));

/** Add a budget for one subcategory ("Food delivery" inside Food & Dining). */
function AddSubcategoryBudget({ taken, onAdd }) {
  const [sub, setSub] = useState("");
  const [value, setValue] = useState("");
  const [error, setError] = useState(null);
  const tree = useCategoryTree();
  const group = tree.groups.find((g) => g.subcategories.some((s) => s.id === sub))?.name;
  const add = async (e) => {
    e.preventDefault();
    try { await onAdd(group, sub, value.trim()); setSub(""); setValue(""); setError(null); }
    catch { setError("Enter a positive amount."); }
  };
  return (
    <form onSubmit={add} className="flex items-center gap-2 pt-3 flex-wrap">
      <CategorySelect value={sub} onChange={setSub} empty="Pick a subcategory" groups={SUB_GROUPS} system={false}
        groupOption={null} aria-label="Subcategory" className="input h-9 min-h-0 py-0 text-sm flex-1 min-w-[12rem]" />
      <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" placeholder="Monthly limit"
        pattern="\d{1,10}(\.\d{1,2})?" aria-label="Subcategory monthly limit" className="w-32 border border-sage-200 rounded-lg px-2 py-1 text-sm" />
      <button type="submit" disabled={!group || !value.trim() || taken.has(sub)}
        className="text-xs px-2 py-1 rounded bg-forest-50 text-forest-700 disabled:opacity-40">Add</button>
      {taken.has(sub) && <span className="text-xs text-ink-400 w-full">That subcategory already has a budget.</span>}
      {error && <span className="text-xs text-danger w-full">{error}</span>}
    </form>
  );
}
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
  const status = useApi("/api/budgets/status", refreshKey);
  const tree = useCategoryTree();
  const reload = () => setRefreshKey((k) => k + 1);

  if (budgets.error || summary.error) return <div className="card p-5 text-sm text-danger">Couldn't load budgets.</div>;
  if (!budgets.data || !summary.data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;

  const groupBudgets = budgets.data.items.filter((b) => !b.subcategory);
  const subBudgets = budgets.data.items.filter((b) => b.subcategory);
  const byCategory = Object.fromEntries(groupBudgets.map((b) => [b.category ?? OVERALL, b]));
  const subSpent = Object.fromEntries((status.data?.categories || []).filter((l) => l.subcategory).map((l) => [l.subcategory, Number(l.spent)]));
  const subLabel = (b) => `${b.category} › ${subcategoryName(b.subcategory, tree) || "Removed subcategory"}`;
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
    category: b.subcategory ? subLabel(b) : b.category ?? "Overall",
    spent: b.subcategory ? (subSpent[b.subcategory] ?? 0) : b.category ? (spent[b.category] ?? 0) : totalSpent,
    limit: Number(b.monthly_limit),
  }));
  const addSub = async (category, subcategory, limit) => {
    await api.post("/api/budgets", { category, subcategory, monthly_limit: limit });
    reload();
  };

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
      <section className="card p-5">
        <h2 className="text-sm font-semibold text-ink">Subcategory budgets</h2>
        <p className="text-xs text-ink-400 mt-1">A limit for one part of a category, like Food delivery inside Food &amp; Dining. It counts inside its category's budget, not on top of it.</p>
        {subBudgets.map((b) => (
          <LimitInput key={`${b.id}-${b.monthly_limit}`} label={subLabel(b)} budget={b} spent={subSpent[b.subcategory] ?? 0}
            onSave={async (v) => { await api.patch(`/api/budgets/${b.id}`, { monthly_limit: v }); reload(); }}
            onRemove={async () => { await api.delete(`/api/budgets/${b.id}`); reload(); }} />
        ))}
        <AddSubcategoryBudget taken={new Set(subBudgets.map((b) => b.subcategory))} onAdd={addSub} />
      </section>
    </div>
  );
}
