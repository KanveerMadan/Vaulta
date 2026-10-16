import { useState } from "react";
import api from "../lib/api";
import { useApi } from "../lib/format";

/** One review question, answered in one tap. `onAnswered(nextQueue, value)` after the server applies it. */
export function ReviewCard({ card, onAnswered, large = false }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const answer = async (value) => {
    setBusy(true);
    setError(null);
    try {
      const { data: next } = await api.post(`/api/review/${encodeURIComponent(card.id)}/answer`, { answer: value });
      onAnswered?.(next, value);
    } catch (err) {
      setError(err?.response?.status === 403 ? err.response.data.detail : "Couldn't save that answer.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className={`${large ? "text-lg" : "text-sm"} font-medium text-ink-900`}>{card.question}</p>
      {card.detail && <p className={`${large ? "text-sm" : "text-xs"} text-ink-500`}>{card.detail}</p>}
      <div className="flex flex-wrap gap-2">
        {card.options.map((o) => (
          <button key={o.value} onClick={() => answer(o.value)} disabled={busy}
            className={o.value === "skip" ? "btn-quiet h-9 text-muted" : "btn-secondary h-9"}>
            {o.label}
          </button>
        ))}
      </div>
      {error && <p className="text-xs text-danger" role="alert">{error}</p>}
    </div>
  );
}

/** "Needs review": one question at a time. */
export default function ReviewQueue({ onAnswered }) {
  const { data } = useApi("/api/review", 0);
  const [queue, setQueue] = useState(null);
  const current = queue ?? data;

  if (!current || current.count === 0) return null;
  const card = current.items[0];

  return (
    <section className="card p-5 space-y-3" aria-live="polite">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Needs review</h2>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-gold/15 text-gold">{current.count}</span>
      </div>
      <ReviewCard key={card.id} card={card} onAnswered={(next, value) => {
        setQueue(next);
        if (value !== "skip") onAnswered?.();
      }} />
    </section>
  );
}
