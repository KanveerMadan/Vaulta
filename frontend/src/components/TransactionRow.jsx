import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ArrowsSplit, Tag, Trash } from "@phosphor-icons/react";
import api from "../lib/api";
import SplitModal from "./SplitModal";
import Money from "../ui/Money";
import { formatINR } from "../lib/money";
import { KINDS, categoryValue, isSubcategory, kindsFor, subcategoryName, useCategoryTree } from "../lib/categories";
import CategorySelect from "./CategorySelect";
import TagEditor from "./TagEditor";
import { updateTransaction, deleteTransaction } from "../lib/transactions";
import { toast } from "../lib/toast";

const COUNTED = new Set(["spend", "income", "refund"]);
const day = (iso) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/**
 * One transaction. Category and kind edits show at once and roll back if the server says no.
 * `selected` (transactions page) highlights the row; the ref exposes editCategory() for the `e` shortcut.
 */
const TransactionRow = forwardRef(function TransactionRow({ txn, onChanged, onRuleLearned, onTag, selected = false, compact = false }, ref) {
  const atm = txn.cash_flow === "withdrawal";
  const name = txn.merchant_clean || (atm ? "ATM withdrawal" : txn.merchant_raw);
  const [local, setLocal] = useState({ category: txn.category, subcategory: txn.subcategory, kind: txn.kind, tags: txn.tags || [] });
  const [editing, setEditing] = useState(null); // "category" | "kind" | "tags" | null
  const tree = useCategoryTree();
  const [splitting, setSplitting] = useState(false);
  const categoryButton = useRef(null);
  useImperativeHandle(ref, () => ({ editCategory: () => setEditing("category") }), []);
  useEffect(() => {
    setLocal({ category: txn.category, subcategory: txn.subcategory, kind: txn.kind, tags: txn.tags || [] });
  }, [txn.category, txn.subcategory, txn.kind, txn.tags]);

  const flow = local.kind === "transfer" || atm ? "transfer" : txn.direction === "credit" ? "in" : "out";
  const counted = COUNTED.has(local.kind);

  // "category" takes a group name or a subcategory id (CategorySelect); the server derives the group
  const change = async (field, value) => {
    const before = { ...local };
    setEditing(null);
    let body;
    if (field === "category") {
      if (value === categoryValue(local.category, local.subcategory)) return;
      body = isSubcategory(value) ? { subcategory: value } : { category: value || null, subcategory: null };
      setLocal((l) => ({ ...l, ...(isSubcategory(value) ? { subcategory: value } : { category: value || null, subcategory: null }) }));
    } else {
      if (JSON.stringify(value) === JSON.stringify(local[field])) return;
      body = { [field]: value };
      setLocal((l) => ({ ...l, [field]: value }));                  // optimistic
    }
    try {
      const res = await updateTransaction(txn.id, body);
      setLocal((l) => ({ ...l, category: res.category, subcategory: res.subcategory, tags: res.tags }));
      if (res.rule_applied) onRuleLearned?.(res.rule_applied);
      onChanged?.();
    } catch (err) {
      setLocal(before);                                              // roll back
      toast({ tone: "danger", message: err?.response?.data?.detail && typeof err.response.data.detail === "string"
        ? err.response.data.detail : `Couldn't change ${name}. Nothing was saved.` });
    }
  };
  const unsplit = async () => { await api.delete(`/api/transactions/${txn.id}/split`); onChanged?.(); };
  const remove = async () => {
    if (!window.confirm(`Delete ${name}, ${formatINR(txn.amount)}?`)) return;
    try { await deleteTransaction(txn.id); onChanged?.(); } catch { toast({ tone: "danger", message: "Couldn't delete that." }); }
  };

  const escape = (e) => { if (e.key === "Escape") { e.stopPropagation(); setEditing(null); categoryButton.current?.focus(); } };
  const select = (field, options) => (
    <select autoFocus defaultValue={local.kind} onChange={(e) => change(field, e.target.value)} onBlur={() => setEditing(null)}
      onKeyDown={escape} className="input h-8 min-h-0 py-0 text-micro w-auto" aria-label="Kind">
      {options}
    </select>
  );
  const sub = subcategoryName(local.subcategory, tree);

  return (
    <div className={`group py-3 ${compact ? "" : "px-2 -mx-2"} rounded-sm transition-colors duration-fast ${selected ? "bg-accent-tint/70" : ""}`}
      data-selected={selected || undefined}>
      <div className="flex items-center gap-3">
        <span aria-hidden className="w-9 h-9 rounded-sm bg-sunken text-ink-2 flex items-center justify-center font-display font-semibold shrink-0">
          {(name || "?")[0].toUpperCase()}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[15px] font-medium text-ink truncate">{name}</p>
          <div className="text-micro text-muted flex items-center gap-1.5 flex-wrap">
            {editing === "category" ? (
              <CategorySelect autoFocus value={categoryValue(local.category, local.subcategory)} empty="Uncategorized"
                onChange={(v) => change("category", v)} onBlur={() => setEditing(null)} onKeyDown={escape}
                className="input h-8 min-h-0 py-0 text-micro w-auto max-w-[14rem]" aria-label="Category" />
            ) : (
              <button ref={categoryButton} onClick={() => setEditing("category")} title={sub ? `${local.category} › ${sub}. Change category` : "Change category"}
                className="hover:text-accent-text hover:underline">
                {sub || local.category || "Uncategorized"}
              </button>
            )}
            <span aria-hidden>·</span>
            {editing === "kind" ? select("kind", kindsFor(txn.direction).map(([v, k]) => <option key={v} value={v}>{k.label}</option>)) : (
              <button onClick={() => setEditing("kind")} title="Change what this transaction is"
                className={`hover:text-accent-text hover:underline ${counted ? "" : "text-warn"}`}>
                {atm ? "Cash withdrawal" : KINDS[local.kind]?.label ?? local.kind}
              </button>
            )}
            <span aria-hidden>·</span>
            <span>{day(txn.transaction_date)}</span>
            {txn.source === "manual" && <span>· added by you</span>}
            {local.tags.map((t) => (
              <button key={t} onClick={() => onTag?.(t)} disabled={!onTag} title={onTag ? `Show everything tagged ${t}` : undefined}
                className="rounded-full bg-sunken px-2 text-ink-2 enabled:hover:text-accent-text">#{t}</button>
            ))}
          </div>
          {editing === "tags" && (
            <TagEditor tags={local.tags} onSave={(tags) => change("tags", tags)} onCancel={() => setEditing(null)} />
          )}
        </div>
        <Money value={txn.amount} flow={flow} className={`text-[15px] font-semibold shrink-0 ${counted ? "" : "text-muted"}`} />
        <div className="flex items-center shrink-0 pointer-fine:opacity-0 pointer-fine:group-hover:opacity-100 pointer-fine:group-focus-within:opacity-100 transition-opacity duration-fast">
          <button onClick={() => setEditing(editing === "tags" ? null : "tags")} className="btn-quiet h-8 px-2 text-micro text-muted"
            aria-label={`Tags for ${name}`} aria-expanded={editing === "tags"} title="Tags">
            <Tag size={15} aria-hidden />
          </button>
          {(local.kind === "spend" || local.kind === "income") && !txn.is_split && (
            <button onClick={() => setSplitting(true)} className="btn-quiet h-8 px-2 text-micro text-muted" aria-label={`Split ${name}`} title="Split">
              <ArrowsSplit size={15} aria-hidden />
            </button>
          )}
          {txn.source === "manual" && (
            <button onClick={remove} className="btn-quiet h-8 px-2 text-muted hover:text-danger" aria-label="Delete transaction"><Trash size={15} /></button>
          )}
        </div>
      </div>
      {txn.is_split && (
        <div className="ml-12 mt-2 space-y-0.5 text-micro text-ink-2">
          {txn.splits.map((part) => (
            <div key={part.id} className="flex justify-between">
              <span>↳ {part.category || "Uncategorized"}</span>
              <Money value={part.amount} />
            </div>
          ))}
          <button onClick={unsplit} className="text-muted hover:text-danger">Unsplit</button>
        </div>
      )}
      {splitting && <SplitModal txn={txn} onClose={() => setSplitting(false)} onSaved={onChanged} />}
    </div>
  );
});

export default TransactionRow;
