import { useEffect, useId, useState } from "react";
import api from "../lib/api";

/** Comma-separated tags for one transaction, suggesting the user's existing tags. Enter saves, Escape cancels. */
export default function TagEditor({ tags, onSave, onCancel }) {
  const [value, setValue] = useState(tags.join(", "));
  const [known, setKnown] = useState([]);
  const list = useId();
  useEffect(() => { api.get("/api/tags").then((r) => setKnown(r.data.items.map((t) => t.name))).catch(() => {}); }, []);
  const save = (e) => {
    e.preventDefault();
    onSave(value.split(",").map((t) => t.trim()).filter(Boolean));
  };
  return (
    <form onSubmit={save} className="mt-2 flex items-center gap-2">
      <label className="flex-1">
        <span className="sr-only">Tags, separated by commas</span>
        <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} list={list} maxLength={300}
          onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onCancel(); } }}
          placeholder="Goa trip, Reimbursable" className="input h-9 text-sm" />
      </label>
      <datalist id={list}>{known.map((t) => <option key={t} value={t} />)}</datalist>
      <button type="submit" className="btn-secondary h-9">Save</button>
      <button type="button" onClick={onCancel} className="btn-quiet h-9">Cancel</button>
    </form>
  );
}
