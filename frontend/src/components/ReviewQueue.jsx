import { useState } from "react";
import api from "../lib/api";
import { useApi } from "../lib/format";

/** "Needs review": one question at a time, each answered in one tap. */
export default function ReviewQueue({ onAnswered }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data } = useApi("/api/review", refreshKey);
  const [queue, setQueue] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const current = queue ?? data;

  if (!current || current.count === 0) return null;
  const card = current.items[0];

  const answer = async (value) => {
    setBusy(true);
    setError(null);
    try {
      const { data: next } = await api.post(`/api/review/${encodeURIComponent(card.id)}/answer`, { answer: value });
      setQueue(next);
      if (value !== "skip") onAnswered?.();
    } catch {
      setError("Couldn't save that answer.");
      setQueue(null);
      setRefreshKey((k) => k + 1);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card p-5 space-y-3" aria-live="polite">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Needs review</h2>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-gold/15 text-gold">{current.count}</span>
      </div>
      <p className="text-sm font-medium text-ink-900">{card.question}</p>
      {card.detail && <p className="text-xs text-ink-500">{card.detail}</p>}
      <div className="flex flex-wrap gap-2">
        {card.options.map((o) => (
          <button key={o.value} onClick={() => answer(o.value)} disabled={busy}
            className={`text-sm px-3 py-1.5 rounded-lg disabled:opacity-50 ${o.value === "skip" ? "text-ink-400 hover:text-ink-700" : "bg-forest-50 text-forest-700 hover:bg-forest-100"}`}>
            {o.label}
          </button>
        ))}
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
    </section>
  );
}
