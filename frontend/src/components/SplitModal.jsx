import Sheet from "../ui/Sheet";
import { useState } from "react";
import api from "../lib/api";
import { CATEGORIES } from "../lib/categories";
import { rupees } from "../lib/format";

const toPaise = (v) => Math.round(Number(v || 0) * 100);

/** Split a transaction into parts whose amounts add up to it exactly. */
export default function SplitModal({ txn, onClose, onSaved }) {
  const half = (toPaise(txn.amount) / 2 / 100).toFixed(2);
  const [parts, setParts] = useState([
    { amount: half, category: txn.category || "" },
    { amount: (Number(txn.amount) - Number(half)).toFixed(2), category: "" },
  ]);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const remaining = (toPaise(txn.amount) - parts.reduce((s, p) => s + toPaise(p.amount), 0)) / 100;
  const set = (i, k, v) => setParts((ps) => ps.map((p, j) => (j === i ? { ...p, [k]: v } : p)));

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post(`/api/transactions/${txn.id}/split`, {
        parts: parts.map((p) => ({ amount: String(p.amount).trim(), category: p.category || null })),
      });
      onSaved?.();
      onClose();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((d) => d.msg).join(" ") : detail || "Couldn't split.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet title={`Split ${txn.merchant_clean || txn.merchant_raw}`} onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        <p className="text-sm text-muted">{rupees(txn.amount)} into parts with their own categories.</p>
        {parts.map((p, i) => (
          <div key={i} className="flex gap-2 items-center">
            <input value={p.amount} onChange={(e) => set(i, "amount", e.target.value)} inputMode="decimal" required
              pattern="\d{1,10}(\.\d{1,2})?" aria-label={`Part ${i + 1} amount`}
              className="input w-28" />
            <select value={p.category} onChange={(e) => set(i, "category", e.target.value)} aria-label={`Part ${i + 1} category`}
              className="input flex-1">
              <option value="">Uncategorized</option>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            {parts.length > 2 && (
              <button type="button" onClick={() => setParts((ps) => ps.filter((_, j) => j !== i))} aria-label="Remove part"
                className="text-ink-400 hover:text-danger px-1">✕</button>
            )}
          </div>
        ))}
        <div className="flex items-center justify-between text-sm">
          <button type="button" onClick={() => setParts((ps) => [...ps, { amount: Math.max(remaining, 0).toFixed(2), category: "" }])}
            className="text-forest-600 font-medium">+ Add part</button>
          <span className={remaining === 0 ? "text-safe" : "text-danger"}>
            {remaining === 0 ? "Adds up" : `${remaining > 0 ? "Left" : "Over"}: ${rupees(Math.abs(remaining))}`}
          </span>
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <div className="flex gap-3">
          <button type="button" onClick={onClose} className="btn-ghost flex-1 text-sm py-2">Cancel</button>
          <button type="submit" disabled={saving || remaining !== 0} className="btn-primary flex-1 text-sm py-2 disabled:opacity-50">
            {saving ? "Saving…" : "Split"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
