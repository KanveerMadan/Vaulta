import { useState } from "react";
import api from "../lib/api";
import { CATEGORIES } from "../lib/categories";
import { rupees, shortDay, useApi } from "../lib/format";

const SPEND_CATEGORIES = CATEGORIES.filter((c) => !["Transfers", "Sent to People", "Received from People"].includes(c));

export default function Cash() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data: w, error } = useApi("/api/cash", refreshKey);
  const [count, setCount] = useState("");
  const [category, setCategory] = useState("Food & Dining");
  const [message, setMessage] = useState(null);
  const reload = () => setRefreshKey((k) => k + 1);

  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!w) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;

  const reconcile = async (body) => {
    const { data } = await api.post("/api/cash/reconcile", body);
    setMessage(data.message);
    reload();
  };
  const declare = async (e) => {
    e.preventDefault();
    const { data } = await api.post("/api/cash/declare", { amount: count.trim() });
    setCount("");
    setMessage(Number(data.gap) > 0
      ? { gap: data.gap, text: `You have ${rupees(data.declared)}; ${rupees(data.gap)} less than expected.` }
      : `Saved: ${rupees(data.declared)} in cash.`);
    reload();
  };
  const unaccounted = Number(w.unaccounted);

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900">Cash</h1>
        <p className="text-sm text-ink-500 mt-1">
          ATM withdrawals move money into your cash wallet (not spending). Cash you log as spent is spending.
          Whatever came out but isn't logged shows as unaccounted.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[["Cash in hand (expected)", w.balance], ["Withdrawn", w.withdrawn], ["Received", w.received], ["Spent", w.spent]].map(([k, v]) => (
          <div key={k} className="card p-4"><p className="text-xs text-ink-400">{k}</p><p className="font-mono text-lg font-semibold">{rupees(v)}</p></div>
        ))}
      </div>
      <p className="text-xs text-ink-500">
        {w.since ? `Since you last counted your cash on ${shortDay(w.since)} (${rupees(w.declared)}).` : "Since you started."}
      </p>

      {unaccounted > 0 && (
        <section className="card p-5 space-y-3">
          <p className="text-sm font-medium text-ink-900">{rupees(unaccounted)} unaccounted</p>
          <div className="flex flex-wrap gap-2 items-center">
            <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category"
              className="border border-sage-200 rounded-lg px-2 py-1.5 text-sm bg-surface">
              {SPEND_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <button onClick={() => reconcile({ action: "category", category })} className="btn-primary-light text-sm py-1.5 px-3">Allocate</button>
            <button onClick={() => reconcile({ action: "have" })} className="btn-ghost text-sm py-1.5 px-3">I still have it</button>
            <button onClick={() => reconcile({ action: "misc" })} className="btn-ghost text-sm py-1.5 px-3">Untracked misc</button>
          </div>
        </section>
      )}

      <section className="card p-5 space-y-2">
        <form onSubmit={declare} className="flex gap-2 items-center flex-wrap">
          <label className="text-sm text-ink-700" htmlFor="cash-count">Count your cash:</label>
          <input id="cash-count" value={count} onChange={(e) => setCount(e.target.value)} inputMode="decimal" required
            pattern="\d{1,10}(\.\d{1,2})?" placeholder="₹ in hand now" className="w-36 border border-sage-200 rounded-lg px-2 py-1.5 text-sm" />
          <button type="submit" className="btn-primary text-sm py-1.5 px-3">Save</button>
        </form>
        {message && typeof message === "object" ? (
          <div className="text-sm text-ink-700 flex items-center gap-2 flex-wrap">
            {message.text}
            <button onClick={() => reconcile({ action: "misc", amount: message.gap })} className="text-forest-600 font-medium">
              Record {rupees(message.gap)} as untracked spending
            </button>
          </div>
        ) : message && <p className="text-sm text-ink-700">{message}</p>}
      </section>

      <div className="grid sm:grid-cols-2 gap-4">
        {[["Withdrawals", w.withdrawals], ["Cash spent", w.spends]].map(([title, items]) => (
          <section key={title} className="card p-5">
            <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest mb-2">{title}</h2>
            {items.length ? (
              <ul className="text-sm space-y-1">
                {items.map((t, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span className="truncate">{shortDay(t.date)} · {t.merchant}{t.category ? ` · ${t.category}` : ""}</span>
                    <span className="font-mono">{rupees(t.amount)}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-ink-400">None yet.</p>}
          </section>
        ))}
      </div>
    </div>
  );
}
