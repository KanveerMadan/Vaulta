import { useState } from "react";
import api from "../lib/api";
import { refreshCategoryTree, useCategoryTree } from "../lib/categories";

/** "Re-check categories": preview what the current categoriser would change, apply it, undo it. Corrected rows are never touched. */
function Recheck() {
  const [state, setState] = useState({ step: "idle" });   // idle | checking | preview | applied | undone | error
  const check = async () => {
    setState({ step: "checking" });
    try { setState({ step: "preview", plan: (await api.post("/api/categories/recategorise", { dry_run: true })).data }); }
    catch { setState({ step: "error" }); }
  };
  const apply = async () => {
    try { setState({ step: "applied", run: (await api.post("/api/categories/recategorise", { dry_run: false })).data }); }
    catch { setState({ step: "error" }); }
  };
  const undo = async () => {
    try { setState({ step: "undone", restored: (await api.post(`/api/categories/recategorise/${state.run.run_id}/undo`)).data.restored }); }
    catch { setState({ step: "error" }); }
  };
  const { plan } = state;
  return (
    <div className="border-t border-line pt-3 space-y-2" aria-live="polite">
      <p className="text-sm text-ink-500">Re-check your past transactions with Vaulta's current categories. Ones you changed yourself are never touched, and you can undo it.</p>
      {state.step === "idle" || state.step === "undone" || state.step === "error" ? (
        <>
          {state.step === "undone" && <p className="text-sm text-ink">Undone: {state.restored} transactions are back as they were.</p>}
          {state.step === "error" && <p role="alert" className="text-sm text-danger">That didn't work. Nothing was changed.</p>}
          <button onClick={check} className="btn-secondary h-10">Re-check categories</button>
        </>
      ) : state.step === "checking" ? <p className="text-sm text-muted">Checking…</p>
        : state.step === "preview" ? (
          plan.changed === 0 ? <p className="text-sm text-ink">Nothing would change.</p> : (
            <div className="space-y-2">
              <p className="text-sm text-ink">{plan.changed} transaction{plan.changed === 1 ? "" : "s"} would change:</p>
              <ul className="text-sm text-ink-2 list-disc pl-5">
                {Object.entries(plan.summary).slice(0, 8).map(([k, n]) => <li key={k}>{k}: {n}</li>)}
              </ul>
              <div className="flex gap-2">
                <button onClick={apply} className="btn-primary h-10">Apply</button>
                <button onClick={() => setState({ step: "idle" })} className="btn-quiet h-10">Not now</button>
              </div>
            </div>
          )
        ) : (
          <div className="flex items-center gap-3 flex-wrap">
            <p className="text-sm text-ink">Changed {state.run.changed} transaction{state.run.changed === 1 ? "" : "s"}.</p>
            {state.run.changed > 0 && <button onClick={undo} className="btn-secondary h-10">Undo</button>}
          </div>
        )}
    </div>
  );
}

/** Settings → Categories: your own subcategories, training consent, and re-checking past categories. */
export default function CustomSubcategories({ consent, onConsent }) {
  const tree = useCategoryTree();
  const [group, setGroup] = useState(tree.groups[0]?.name || "");
  const [name, setName] = useState("");
  const [error, setError] = useState(null);
  const mine = tree.groups.flatMap((g) => g.subcategories.filter((s) => s.custom).map((s) => ({ ...s, group: g.name })));

  const add = async (e) => {
    e.preventDefault();
    try {
      await api.post("/api/categories/subcategories", { group, name: name.trim() });
      setName(""); setError(null);
      refreshCategoryTree();
    } catch (err) {
      setError(typeof err?.response?.data?.detail === "string" ? err.response.data.detail : "Couldn't add that.");
    }
  };
  const remove = async (s) => {
    if (!window.confirm(`Remove “${s.name}”? Its transactions stay in ${s.group}.`)) return;
    await api.delete(`/api/categories/subcategories/${s.id.replace("custom:", "")}`);
    refreshCategoryTree();
  };

  return (
    <section className="card p-5 space-y-3" aria-labelledby="categories-title">
      <h2 id="categories-title" className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Categories</h2>
      <p className="text-sm text-ink-500">Every category has subcategories. Add your own when none fits.</p>
      {mine.length > 0 && (
        <ul className="divide-y divide-line">
          {mine.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span><span className="text-ink-400">{s.group} › </span><span className="text-ink">{s.name}</span></span>
              <button onClick={() => remove(s)} className="text-xs text-ink-400 hover:text-danger">Remove</button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="flex flex-wrap gap-2">
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Category" className="input h-10 sm:w-48">
          {tree.groups.map((g) => <option key={g.name}>{g.name}</option>)}
        </select>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required aria-label="New subcategory name"
          placeholder="Office lunch" className="input h-10 flex-1 min-w-[10rem]" />
        <button type="submit" disabled={!name.trim()} className="btn-secondary h-10">Add</button>
      </form>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <Recheck />
      {onConsent && (
        <div className="border-t border-line pt-3 space-y-1">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={consent} onChange={(e) => onConsent(e.target.checked)} />
            Let my category corrections help improve Vaulta's categories
          </label>
          <p className="text-xs text-ink-500">
            Off unless you turn it on. When on, the corrections you make (the merchant text with personal details already
            removed, and the category you chose) may be used to retrain the model that suggests categories. Nothing else
            is used, and turning it off stops it for any retraining after that.
          </p>
        </div>
      )}
    </section>
  );
}
