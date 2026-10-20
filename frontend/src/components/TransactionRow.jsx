import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ArrowsSplit, DotsThree, Info, Tag, Trash } from "@phosphor-icons/react";
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
  const [editing, setEditing] = useState(null); // "category" | "kind" | "tags" | "why" | null
  const [why, setWhy] = useState(null);
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
  const explain = async () => {
    if (editing === "why") { setEditing(null); return; }
    setEditing("why");
    setWhy(null);
    try { setWhy((await api.get(`/api/transactions/${txn.id}/explanation`)).data); }
    catch { setWhy({ text: "Couldn't load the explanation. Try again in a moment." }); }
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
  const actions = txn.is_sample ? [] : [
    { key: "why", Icon: Info, title: "Why is it filed here?", label: `Why ${name} is filed here`, expanded: editing === "why", onClick: explain },
    { key: "tags", Icon: Tag, title: "Tags", label: `Tags for ${name}`, expanded: editing === "tags",
      onClick: () => setEditing(editing === "tags" ? null : "tags") },
    ...((local.kind === "spend" || local.kind === "income") && !txn.is_split
      ? [{ key: "split", Icon: ArrowsSplit, title: "Split", label: `Split ${name}`, onClick: () => setSplitting(true) }] : []),
    ...(txn.source === "manual" ? [{ key: "delete", Icon: Trash, title: "Delete", label: "Delete transaction", danger: true, onClick: remove }] : []),
  ];

  return (
    <div className={`group py-3 ${compact ? "" : "px-2 -mx-2"} rounded-sm transition-colors duration-fast ${selected ? "bg-accent-tint/70" : ""}`}
      data-selected={selected || undefined}>
      <div className="flex items-center gap-3">
        <span aria-hidden className="w-9 h-9 rounded-sm bg-sunken text-ink-2 flex items-center justify-center font-display font-semibold shrink-0">
          {(name || "?")[0].toUpperCase()}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[15px] font-medium text-ink truncate">
            {name}
            {txn.is_sample && <span className="ml-2 align-middle rounded-full bg-warn-tint px-2 py-0.5 text-micro font-medium text-ink" title="A sample from trying vaulta.in out. It isn't counted anywhere and goes by itself within an hour.">Sample</span>}
          </p>
          <div className="text-micro text-muted flex items-center gap-1.5 flex-wrap">
            {txn.is_sample ? (
              <span>{sub ? `${local.category} › ${sub}` : local.category || "Uncategorized"} · not counted</span>
            ) : editing === "category" ? (
              <CategorySelect autoFocus value={categoryValue(local.category, local.subcategory)} empty="Uncategorized"
                onChange={(v) => change("category", v)} onBlur={() => setEditing(null)} onKeyDown={escape}
                className="input h-8 min-h-0 py-0 text-micro w-auto max-w-[14rem]" aria-label="Category" />
            ) : (
              <button ref={categoryButton} onClick={() => setEditing("category")} title="Change category"
                className="inline-flex items-center py-1 text-left hover:text-accent-text hover:underline">
                {sub ? `${local.category} › ${sub}` : local.category || "Uncategorized"}
              </button>
            )}
            {!txn.is_sample && <span aria-hidden>·</span>}
            {txn.is_sample ? null : editing === "kind" ? select("kind", kindsFor(txn.direction).map(([v, k]) => <option key={v} value={v}>{k.label}</option>)) : (
              <button onClick={() => setEditing("kind")} title="Change what this transaction is"
                className={`inline-flex items-center py-1 hover:text-accent-text hover:underline ${counted ? "" : "text-warn"}`}>
                {atm ? "Cash withdrawal" : KINDS[local.kind]?.label ?? local.kind}
              </button>
            )}
            <span aria-hidden>·</span>
            <span>{day(txn.transaction_date)}</span>
            {txn.source === "manual" && <span>· added by you</span>}
            {local.tags.map((t) => (
              <button key={t} onClick={() => onTag?.(t)} disabled={!onTag} title={onTag ? `Show everything tagged ${t}` : undefined}
                className="inline-flex items-center py-1 rounded-full bg-sunken px-2 text-ink-2 enabled:hover:text-accent-text">#{t}</button>
            ))}
          </div>
          {editing === "why" && (
            <div role="status" className="mt-2 rounded-sm bg-sunken px-3 py-2 text-micro text-ink-2 max-w-prose">
              {why ? why.text : "Loading…"}
              {why?.alternatives?.length > 1 && why.source !== "you" && (
                <span className="block mt-1 text-muted">
                  Other guesses: {why.alternatives.slice(1).map((a) => `${a.name} (${Math.round(a.probability * 100)}%)`).join(", ")}
                </span>
              )}
            </div>
          )}
          {editing === "tags" && (
            <TagEditor tags={local.tags} onSave={(tags) => change("tags", tags)} onCancel={() => setEditing(null)} />
          )}
        </div>
        <Money value={txn.amount} flow={flow} className={`text-[15px] font-semibold shrink-0 ${counted ? "" : "text-muted"}`} />
        <div className="hidden sm:flex items-center shrink-0 pointer-fine:opacity-0 pointer-fine:group-hover:opacity-100 pointer-fine:group-focus-within:opacity-100 transition-opacity duration-fast">
          {actions.map((a) => (
            <button key={a.key} onClick={a.onClick} aria-label={a.label} aria-expanded={a.expanded} title={a.title}
              className={`btn-quiet h-8 px-2 text-micro text-muted ${a.danger ? "hover:text-danger" : ""}`}>
              <a.Icon size={15} aria-hidden />
            </button>
          ))}
        </div>
        {/* phones: one button, so the text keeps its width */}
        {actions.length > 0 && <button onClick={() => setEditing(editing === "more" ? null : "more")} className="sm:hidden btn-quiet px-2 text-muted shrink-0"
          aria-label={`More for ${name}`} aria-expanded={editing === "more"}>
          <DotsThree size={18} aria-hidden />
        </button>}
      </div>
      {editing === "more" && (
        <div className="sm:hidden mt-1 ml-12 flex flex-wrap gap-1">
          {actions.map((a) => (
            <button key={a.key} onClick={a.onClick} aria-label={a.label}
              className={`btn-quiet px-2 text-micro text-ink-2 inline-flex items-center gap-1.5 ${a.danger ? "hover:text-danger" : ""}`}>
              <a.Icon size={15} aria-hidden />{a.title}
            </button>
          ))}
        </div>
      )}
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
