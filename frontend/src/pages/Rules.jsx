import { useState } from "react";
import api from "../lib/api";
import { KINDS } from "../lib/categories";
import CategorySelect from "../components/CategorySelect";
import { useApi } from "../lib/format";

const ORIGIN = { learned: "Learned from your edits", review: "From a review answer", manual: "Added by you" };

function RuleRow({ rule, onChange }) {
  const save = async (value) => { await api.patch(`/api/rules/${rule.id}`, { value }); onChange(); };
  const remove = async () => { await api.delete(`/api/rules/${rule.id}`); onChange(); };
  return (
    <div className="py-3 border-b border-sage-50 last:border-0 flex items-center gap-3 flex-wrap text-sm">
      <span className="font-medium text-ink-900">{rule.merchant}</span>
      <span className="text-ink-400">→ {rule.field === "category" ? "category" : "kind"}</span>
      {rule.field === "category" ? (
        <CategorySelect value={rule.value} onChange={save} aria-label="Rule value"
          className="border border-sage-200 rounded px-1 py-0.5 text-xs bg-surface max-w-[14rem]" />
      ) : (
        <select value={rule.value} onChange={(e) => save(e.target.value)} aria-label="Rule value"
          className="border border-sage-200 rounded px-1 py-0.5 text-xs bg-surface">
          {Object.entries(KINDS).map(([value, k]) => <option key={value} value={value}>{k.label}</option>)}
        </select>
      )}
      <span className="text-xs text-ink-400">{rule.matches} transactions · {ORIGIN[rule.origin]}</span>
      <button onClick={remove} className="ml-auto text-xs text-ink-400 hover:text-danger">Delete</button>
    </div>
  );
}

export default function Rules() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/rules", refreshKey);
  const reload = () => setRefreshKey((k) => k + 1);
  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;
  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div>
        <h1 className="font-display text-display-s text-ink">Rules</h1>
        <p className="text-sm text-ink-500 mt-1">
          Correct the same merchant twice the same way and Vaulta makes a rule for it. Rules apply to past and future
          transactions, except ones you changed individually. Deleting a rule puts those transactions back.
        </p>
      </div>
      <section className="card p-5">
        {data.rules.length ? data.rules.map((r) => <RuleRow key={r.id} rule={r} onChange={reload} />)
          : <p className="text-sm text-ink-400 text-center">No rules yet.</p>}
      </section>
    </div>
  );
}
