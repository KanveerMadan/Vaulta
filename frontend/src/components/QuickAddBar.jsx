import { useState } from "react";
import { parseQuickAdd } from "../lib/quickAdd";
import { addManualTransaction } from "../lib/transactions";
import ManualEntryModal from "./ManualEntryModal";

const fmtDay = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  const today = new Date();
  const diff = Math.round((new Date(today.toDateString()) - d) / 86400000);
  return diff === 0 ? "today" : diff === 1 ? "yesterday" : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};

/** "150 auto cash" → parsed chip → one tap to add, or open the full form to edit. */
export default function QuickAddBar({ onAdded }) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const parsed = text.trim() ? parseQuickAdd(text) : null;

  const add = async () => {
    if (!parsed) return;
    setSaving(true);
    setError(null);
    try {
      await addManualTransaction(parsed);
      setText("");
      onAdded?.();
    } catch {
      setError("Couldn't add that. Try the full form.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card p-3 space-y-2">
      <form onSubmit={(e) => { e.preventDefault(); add(); }} className="flex gap-2">
        <input
          value={text}
          onChange={(e) => { setText(e.target.value); setError(null); }}
          placeholder='Quick add: "150 auto cash" or "2400 groceries dmart yesterday"'
          className="flex-1 border border-sage-200 rounded-lg px-3 py-2 text-sm"
          aria-label="Quick add a transaction"
        />
        <button type="button" onClick={() => setEditing(parsed || {})} className="btn-ghost text-sm px-3">
          {parsed ? "Edit" : "+ Add"}
        </button>
      </form>
      {parsed && (
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className={`font-mono font-semibold ${parsed.direction === "credit" ? "text-safe" : "text-ink-900"}`}>
            {parsed.direction === "credit" ? "+" : "−"}₹{Number(parsed.amount).toLocaleString("en-IN")}
          </span>
          <span className="text-ink-800">{parsed.merchant}</span>
          <span className="px-2 py-0.5 rounded-full bg-sage-100 text-ink-600">{parsed.category || "Auto-detect"}</span>
          <span className="text-ink-500">{fmtDay(parsed.date)} · {parsed.payment_method}</span>
          <button onClick={add} disabled={saving} className="ml-auto btn-primary text-xs py-1 px-3 disabled:opacity-50">
            {saving ? "Adding…" : "Add"}
          </button>
        </div>
      )}
      {text.trim() && !parsed && <p className="text-xs text-ink-400">Start with an amount, e.g. "150 auto".</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
      {editing && (
        <ManualEntryModal
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setText(""); onAdded?.(); }}
        />
      )}
    </div>
  );
}
