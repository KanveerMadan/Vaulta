import { useState } from "react";
import api from "../lib/api";
import { refreshCategoryTree, useCategoryTree } from "../lib/categories";

/** Settings → Categories: add your own subcategories to a group, or remove them (their transactions keep the group). */
export default function CustomSubcategories() {
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
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Category" className="input h-10 min-h-0 sm:w-48">
          {tree.groups.map((g) => <option key={g.name}>{g.name}</option>)}
        </select>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required aria-label="New subcategory name"
          placeholder="Office lunch" className="input h-10 min-h-0 flex-1 min-w-[10rem]" />
        <button type="submit" disabled={!name.trim()} className="btn-secondary h-10 min-h-0">Add</button>
      </form>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </section>
  );
}
