import { useState } from "react";
import api from "../lib/api";
import { CATEGORIES } from "../lib/categories";
import { GOAL_STATUS, rupees, useApi } from "../lib/format";

const STATUS_STYLE = { done: "text-safe", on_track: "text-safe", behind: "text-danger", not_started: "text-ink-400" };
const longDay = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const errorText = (err) => {
  const d = err?.response?.data?.detail;
  return typeof d === "string" ? d : "Check the details and try again.";
};

function NewGoal({ onSaved }) {
  const [form, setForm] = useState({ name: "", target_amount: "", target_date: "", category: "" });
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/api/goals", { ...form, category: form.category || null });
      setForm({ name: "", target_amount: "", target_date: "", category: "" });
      onSaved();
    } catch (err) {
      setError(errorText(err));
    }
  };
  return (
    <form onSubmit={save} className="card p-5 space-y-3" aria-label="New goal">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">New goal</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="text-sm text-ink-600 space-y-1">Name
          <input className="input" required maxLength={80} value={form.name} onChange={set("name")} placeholder="Laptop" />
        </label>
        <label className="text-sm text-ink-600 space-y-1">Target amount (₹)
          <input className="input" required inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={form.target_amount} onChange={set("target_amount")} placeholder="60000" />
        </label>
        <label className="text-sm text-ink-600 space-y-1">By
          <input className="input" required type="date" value={form.target_date} onChange={set("target_date")} />
        </label>
        <label className="text-sm text-ink-600 space-y-1">Spending to cut (optional)
          <select className="input" value={form.category} onChange={set("category")}>
            <option value="">None</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <button className="btn-primary">Create goal</button>
    </form>
  );
}

function GoalCard({ goal, onChanged }) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState(null);
  const pct = Math.min(Number(goal.progress_pct || 0), 100);

  const run = async (fn) => {
    setError(null);
    try { await fn(); onChanged(); } catch (err) { setError(errorText(err)); }
  };
  const contribute = (e) => {
    e.preventDefault();
    run(async () => { await api.post(`/api/goals/${goal.id}/entries`, { amount }); setAmount(""); });
  };

  return (
    <section className="card p-5 space-y-3" aria-label={goal.name}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-ink-900">{goal.name}</h2>
          <p className="text-sm text-ink-500">{rupees(goal.target_amount)} by {longDay(goal.target_date)}</p>
        </div>
        <span className={`text-sm font-medium ${STATUS_STYLE[goal.status]}`}>{GOAL_STATUS[goal.status]}</span>
      </div>
      <div className="h-2 bg-sage-100 rounded-full overflow-hidden" role="progressbar" aria-label={`${goal.name} progress`}
        aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full bg-forest-400 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div><dt className="text-xs text-ink-400">Saved</dt><dd className="font-mono">{rupees(goal.saved)}</dd></div>
        <div><dt className="text-xs text-ink-400">Still needed</dt><dd className="font-mono">{rupees(goal.remaining)}</dd></div>
        <div><dt className="text-xs text-ink-400">Needed a month</dt><dd className="font-mono">{rupees(goal.required_monthly)}</dd></div>
        <div><dt className="text-xs text-ink-400">At your pace</dt><dd>{goal.projected_date ? longDay(goal.projected_date) : "—"}</dd></div>
      </dl>
      {goal.estimate && (
        <p className="text-xs text-ink-500 bg-sage-50 rounded-lg px-3 py-2">
          <span className="font-semibold">Estimate:</span> if you keep saving about {rupees(goal.estimate.monthly_savings)} a month
          (your average over the last 3 months) and put it all here, you'd reach it around {longDay(goal.estimate.projected_date)}.
          This isn't counted as saved.
        </p>
      )}
      {goal.category_spend && (
        <p className="text-xs text-ink-500">Cutting {goal.category_spend.category}: {rupees(goal.category_spend.this_month)} spent this month.</p>
      )}
      {goal.status !== "done" && (
        <form onSubmit={contribute} className="flex gap-2">
          <input className="input flex-1" required inputMode="decimal" pattern="-?\d+(\.\d{1,2})?" value={amount}
            onChange={(e) => setAmount(e.target.value)} placeholder="₹ put towards it" aria-label={`Amount to put towards ${goal.name}`} />
          <button className="btn-primary shrink-0">Add</button>
        </form>
      )}
      {goal.entries.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-ink-500 py-2">{goal.entries.length} contribution{goal.entries.length === 1 ? "" : "s"}</summary>
          <ul className="divide-y divide-sage-50">
            {goal.entries.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-3 py-1">
                <span className="text-ink-600">{longDay(e.date)}</span>
                <span className="flex items-center gap-2">
                  <span className="font-mono">{rupees(e.amount)}</span>
                  <button onClick={() => run(() => api.delete(`/api/goals/${goal.id}/entries/${e.id}`))}
                    className="text-ink-300 hover:text-danger px-2" aria-label={`Remove ${rupees(e.amount)} on ${longDay(e.date)}`}>✕</button>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <button onClick={() => window.confirm(`Delete the goal “${goal.name}”?`) && run(() => api.delete(`/api/goals/${goal.id}`))}
        className="text-xs text-ink-400 hover:text-danger">Delete goal</button>
    </section>
  );
}

export default function Goals() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/goals", refreshKey);
  const refresh = () => setRefreshKey((k) => k + 1);
  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <h1 className="font-display text-2xl text-ink-900">Goals</h1>
      <p className="text-sm text-ink-500">Record money as you set it aside. Contributions are separate from your transactions, so they never change your spending.</p>
      {error && <p className="text-sm text-danger">{error}</p>}
      {data && data.items.length === 0 && (
        <p className="card p-5 text-sm text-ink-500">No goals yet. Add one below — a laptop, a trip, an emergency fund.</p>
      )}
      {data?.items.map((g) => <GoalCard key={g.id} goal={g} onChanged={refresh} />)}
      <NewGoal onSaved={refresh} />
    </div>
  );
}
