import Sheet from "../ui/Sheet";
import { useState } from "react";
import { CATEGORIES } from "../lib/categories";
import { addManualTransaction } from "../lib/transactions";

const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local

/** Full manual entry form. `initial` pre-fills it (e.g. from the quick-add bar). */
export default function ManualEntryModal({ initial = {}, onClose, onSaved }) {
  const [form, setForm] = useState(() => {
    const f = { date: today(), amount: "", merchant: "", direction: "debit", payment_method: "cash", notes: "", ...initial };
    return { ...f, category: f.category || "" };
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const txn = await addManualTransaction({
        date: form.date,
        amount: String(form.amount).trim(),
        merchant: form.merchant.trim(),
        category: form.category || null,
        direction: form.direction,
        payment_method: form.payment_method,
        notes: form.notes.trim() || null,
      });
      onSaved?.(txn);
      onClose?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((d) => d.msg).join(" ") : detail || "Couldn't save. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const input = "input";
  return (
    <Sheet title="Add transaction" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">

        <div className="flex gap-1 bg-sage-100 rounded-lg p-1">
          {[["debit", "Spent"], ["credit", "Received"]].map(([value, label]) => (
            <button type="button" key={value} onClick={() => setForm((f) => ({ ...f, direction: value }))}
              className={`flex-1 py-1.5 rounded-md text-sm font-medium ${form.direction === value ? "bg-surface text-ink-900 shadow-sm" : "text-ink-500"}`}>
              {label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm text-ink-700 space-y-1">
            <span>Amount (₹)</span>
            <input className={input} inputMode="decimal" required pattern="\d{1,10}(\.\d{1,2})?" value={form.amount} onChange={set("amount")} autoFocus />
          </label>
          <label className="text-sm text-ink-700 space-y-1">
            <span>Date</span>
            <input className={input} type="date" required max={today()} value={form.date} onChange={set("date")} />
          </label>
        </div>
        <label className="text-sm text-ink-700 space-y-1 block">
          <span>{form.direction === "debit" ? "Paid to" : "Received from"}</span>
          <input className={input} required maxLength={100} value={form.merchant} onChange={set("merchant")} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm text-ink-700 space-y-1">
            <span>Category</span>
            <select className={input} value={form.category} onChange={set("category")}>
              <option value="">Auto-detect</option>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="text-sm text-ink-700 space-y-1">
            <span>Paid by</span>
            <select className={input} value={form.payment_method} onChange={set("payment_method")}>
              <option value="cash">Cash</option>
              <option value="online">Online / UPI / card</option>
            </select>
          </label>
        </div>
        <label className="text-sm text-ink-700 space-y-1 block">
          <span>Note (optional)</span>
          <input className={input} maxLength={500} value={form.notes} onChange={set("notes")} />
        </label>

        {error && <p className="text-sm text-danger">{error}</p>}
        <button type="submit" disabled={saving} className="btn-primary w-full h-11">
          {saving ? "Saving…" : "Add transaction"}
        </button>
      </form>
    </Sheet>
  );
}
