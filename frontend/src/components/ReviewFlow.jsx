import { useEffect, useState } from "react";
import api from "../lib/api";
import { ReviewCard } from "./ReviewQueue";

const TYPE_LABELS = { person: "People", repayment: "People", recurring: "Recurring", transfer: "Transfers", budget: "Suggested budgets",
  merchant: "Categories", anomaly: "Worth a second look", cash: "Cash" };

/** The review queue as a focused flow: one large card at a time until it's empty. */
export default function ReviewFlow({ onDone, doneLabel = "Done" }) {
  const [queue, setQueue] = useState(null);
  const [answered, setAnswered] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/api/review").then((r) => setQueue(r.data)).catch(() => setError("Couldn't load your questions."));
  }, []);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!queue) return <p className="text-sm text-ink-400">Loading…</p>;
  if (queue.count === 0) {
    return (
      <div className="text-center space-y-3 py-6">
        <p className="text-lg font-medium text-ink-900">{answered ? "All caught up." : "Nothing to review right now."}</p>
        <p className="text-sm text-ink-500">{answered ? `You answered ${answered} question${answered === 1 ? "" : "s"}. Your numbers are updated.` : "Questions appear here when Vaulta isn't sure about something."}</p>
        {onDone && <button onClick={onDone} className="btn-primary">{doneLabel}</button>}
      </div>
    );
  }
  const card = queue.items[0];
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="flex justify-between text-xs text-ink-400">
        <span className="uppercase tracking-widest font-semibold">{TYPE_LABELS[card.type] || "Question"}</span>
        <span>{queue.count} left</span>
      </div>
      <div className="card p-6">
        <ReviewCard key={card.id} card={card} large onAnswered={(next, value) => {
          setQueue(next);
          if (value !== "skip") setAnswered((n) => n + 1);
        }} />
      </div>
      {onDone && <button onClick={onDone} className="text-sm text-ink-400 hover:text-ink-700">Finish later</button>}
    </div>
  );
}
