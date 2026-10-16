import { useState } from "react";
import api from "../lib/api";
import { rupees, shortDay, useApi } from "../lib/format";

const TAGS = ["Rent", "Splits", "Family", "Friend", "Lent", "Other"];

function balanceText(p) {
  const n = Number(p.balance);
  if (n > 0) return `owes you ${rupees(n)}${p.outstanding_days != null ? ` · ${p.outstanding_days} days` : ""}`;
  if (n < 0) return `you owe ${rupees(-n)}${p.outstanding_days != null ? ` · ${p.outstanding_days} days` : ""}`;
  return null;
}

function PersonRow({ p, others, onChange }) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(p.name);
  const [error, setError] = useState(null);
  const patch = async (body) => {
    try {
      await api.patch(`/api/people/${p.id}`, body);
      setError(null);
      onChange();
    } catch {
      setError("Couldn't save.");
    }
  };
  const balance = balanceText(p);
  const mergeInto = async (targetId) => {
    if (!targetId) return;
    const target = others.find((o) => o.id === targetId);
    if (!window.confirm(`Merge ${p.name} into ${target.name}? Their transactions, tag and balance move to ${target.name}.`)) return;
    try {
      await api.post(`/api/people/${targetId}/merge`, { source_id: p.id });
      onChange();
    } catch {
      setError("Couldn't merge.");
    }
  };

  return (
    <div className="py-3 border-b border-sage-50 last:border-0 space-y-1">
      <div className="flex items-center gap-2 flex-wrap">
        {renaming ? (
          <form onSubmit={(e) => { e.preventDefault(); setRenaming(false); patch({ display_name: name.trim() }); }}>
            <input autoFocus value={name} maxLength={100} onChange={(e) => setName(e.target.value)}
              onBlur={() => setRenaming(false)} className="border border-sage-200 rounded px-2 py-0.5 text-sm" />
          </form>
        ) : (
          <button onClick={() => setRenaming(true)} className="font-medium text-sm text-ink-900 hover:underline" title="Rename">{p.name}</button>
        )}
        {p.masked_vpa && <span className="text-xs text-ink-400 font-mono">{p.masked_vpa}</span>}
        {balance && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${Number(p.balance) > 0 ? "bg-safe/15 text-safe" : "bg-gold/15 text-gold"}`}>
            {balance}
          </span>
        )}
        <select value={p.tag || ""} onChange={(e) => patch({ tag: e.target.value || null })} aria-label="Tag"
          className="ml-auto border border-sage-200 rounded px-1 py-0.5 text-xs bg-surface">
          <option value="">No tag</option>
          {TAGS.map((t) => <option key={t}>{t}</option>)}
        </select>
      </div>
      <div className="text-xs text-ink-500 flex gap-3 flex-wrap">
        <span>Paid {rupees(p.paid_total)}</span>
        <span>Received {rupees(p.received_total)}</span>
        <span>{p.transaction_count} transactions · last {shortDay(p.last_date)}</span>
        {others.length > 0 && (
          <select value="" onChange={(e) => mergeInto(e.target.value)} aria-label={`Merge ${p.name} into another person`}
            className="border border-sage-200 rounded px-1 py-0.5 bg-surface text-ink-500">
            <option value="">Same person as…</option>
            {others.map((o) => <option key={o.id} value={o.id}>{o.name}{o.masked_vpa ? ` (${o.masked_vpa})` : ""}</option>)}
          </select>
        )}
        {p.tag && (
          <span className="text-ink-400">
            Applies {p.default_category || "no category"}{p.default_kind ? ` · ${p.default_kind}` : ""} to their transactions
          </span>
        )}
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

export default function People() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/people", refreshKey);
  const reload = () => setRefreshKey((k) => k + 1);

  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;
  const owed = data.people.filter((p) => Number(p.balance) !== 0);

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div>
        <h1 className="font-display text-display-s text-ink">People</h1>
        <p className="text-sm text-ink-500 mt-1">
          Everyone you pay or get paid by over UPI. Tag someone once and it applies to all their transactions.
          Mark a payment as lent or borrowed from its transaction row to track who owes whom.
        </p>
      </div>
      {owed.length > 0 && (
        <div className="card p-5">
          <p className="text-xs font-medium text-ink-400 uppercase tracking-widest mb-2">Outstanding</p>
          <ul className="space-y-1 text-sm">
            {owed.map((p) => <li key={p.id}><span className="text-ink-900">{p.name}</span> <span className="text-ink-500">{balanceText(p)}</span></li>)}
          </ul>
        </div>
      )}
      <section className="card p-5">
        {data.people.length ? data.people.map((p) => <PersonRow key={p.id} p={p} others={data.people.filter((o) => o.id !== p.id)} onChange={reload} />)
          : <p className="text-sm text-ink-400 text-center">No person-to-person payments yet.</p>}
      </section>
    </div>
  );
}
