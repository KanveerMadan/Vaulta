import { useState } from "react";
import api from "../lib/api";
import SplitModal from "./SplitModal";
import { rupees } from "../lib/format";
import { CATEGORIES, KINDS, kindsFor } from "../lib/categories";
import { updateTransaction, deleteTransaction } from "../lib/transactions";

export function RuleToast({ rule, onUndo, onClose }) {
  const what = rule.field === "kind" ? (KINDS[rule.value]?.label ?? rule.value) : rule.value;
  return (
    <div role="status" className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-ink-900 text-white text-sm rounded-xl shadow-lg px-4 py-3 flex items-center gap-3 max-w-[calc(100vw-2rem)]">
      <span>
        {rule.applied_count > 0
          ? `Applied ${what} to ${rule.applied_count} other ${rule.merchant} transaction${rule.applied_count === 1 ? "" : "s"}.`
          : `${rule.merchant} will be ${what} from now on.`}
      </span>
      <button onClick={onUndo} className="font-semibold underline">Undo</button>
      <button onClick={onClose} aria-label="Dismiss" className="text-white/60">✕</button>
    </div>
  );
}

export default function TransactionRow({ txn, onChanged, onRuleLearned }) {
  const atm = txn.cash_flow === "withdrawal";
  const name = txn.merchant_clean || (atm ? "ATM withdrawal" : txn.merchant_raw);
  const isCredit = txn.direction === "credit";
  const counted = txn.kind === "spend" || txn.kind === "income" || txn.kind === "refund";
  const [editing, setEditing] = useState(false);
  const [editingKind, setEditingKind] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setEditing(false);
      setEditingKind(false);
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.detail || "Couldn't save that change.");
    } finally {
      setBusy(false);
    }
  };

  const update = async (changes) => {
    const res = await updateTransaction(txn.id, changes);
    if (res.rule_applied) onRuleLearned?.(res.rule_applied);
  };
  const setCategory = (category) => act(() => update({ category: category || null }));
  const setKind = (kind) => act(() => update({ kind }));
  const unsplit = () => act(() => api.delete(`/api/transactions/${txn.id}/split`));
  const remove = () => {
    if (window.confirm(`Delete ${txn.merchant_clean || txn.merchant_raw}, ₹${txn.amount}?`)) act(() => deleteTransaction(txn.id));
  };

  return (
    <div className="py-2.5 border-b border-sage-50 last:border-0">
    <div className="flex items-center gap-3">
      <div className="w-9 h-9 rounded-full bg-sage-100 flex items-center justify-center text-ink-500 text-sm shrink-0">
        {(name || "?")[0].toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-ink-900 truncate">
          {name}
        </p>
        <div className="text-xs text-ink-400 flex items-center gap-1">
          {editing ? (
            <select
              autoFocus
              disabled={busy}
              defaultValue={txn.category || ""}
              onChange={(e) => setCategory(e.target.value)}
              onBlur={() => !busy && setEditing(false)}
              className="border border-sage-200 rounded px-1 py-0.5 text-xs bg-white text-ink-700"
              aria-label="Category"
            >
              <option value="">Uncategorized</option>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          ) : (
            <button onClick={() => setEditing(true)} className="hover:text-forest-600 hover:underline" title="Change category">
              {txn.category || "Uncategorized"}
            </button>
          )}
          <span>·</span>
          {editingKind ? (
            <select
              autoFocus
              disabled={busy}
              defaultValue={txn.kind}
              onChange={(e) => setKind(e.target.value)}
              onBlur={() => !busy && setEditingKind(false)}
              className="border border-sage-200 rounded px-1 py-0.5 text-xs bg-white text-ink-700"
              aria-label="Kind"
            >
              {kindsFor(txn.direction).map(([value, k]) => <option key={value} value={value}>{k.label}</option>)}
            </select>
          ) : (
            <button onClick={() => setEditingKind(true)} title="Change what this transaction is"
              className={`hover:text-forest-600 hover:underline ${counted ? "" : "text-gold"}`}>
              {atm ? "Cash withdrawal" : KINDS[txn.kind]?.label ?? txn.kind}
            </button>
          )}
          <span>·</span>
          <span>
            {new Date(txn.transaction_date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
          </span>
          {txn.source === "manual" && <span className="text-ink-300">· added by you</span>}
        </div>
        {error && <p className="text-xs text-danger mt-0.5">{error}</p>}
      </div>
      <p className={`font-mono text-sm font-medium shrink-0 ${
        !counted ? "text-ink-400" : isCredit ? "text-safe" : "text-ink-800"
      }`}>
        {txn.kind === "transfer" ? "↔" : isCredit ? "+" : "-"}
        ₹{Math.abs(txn.amount).toLocaleString("en-IN")}
      </p>
      {(txn.kind === "spend" || txn.kind === "income") && !txn.is_split && (
        <button onClick={() => setSplitting(true)} disabled={busy} className="text-xs text-ink-300 hover:text-forest-600 shrink-0">Split</button>
      )}
      {txn.source === "manual" && (
        <button onClick={remove} disabled={busy} className="p-1 text-ink-300 hover:text-danger shrink-0" aria-label="Delete transaction">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
    {txn.is_split && (
      <div className="ml-12 mt-1.5 space-y-0.5 text-xs text-ink-500">
        {txn.splits.map((part) => (
          <div key={part.id} className="flex justify-between">
            <span>↳ {part.category || "Uncategorized"}</span>
            <span className="font-mono">{rupees(part.amount)}</span>
          </div>
        ))}
        <button onClick={unsplit} disabled={busy} className="text-ink-400 hover:text-danger">Unsplit</button>
      </div>
    )}
    {splitting && <SplitModal txn={txn} onClose={() => setSplitting(false)} onSaved={onChanged} />}
    </div>
  );
}
