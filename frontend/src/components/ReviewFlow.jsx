import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "../lib/api";

const TYPE_LABELS = { person: "People", repayment: "People", recurring: "Recurring", transfer: "Transfers", budget: "Suggested budgets",
  merchant: "Categories", anomaly: "Worth a second look", cash: "Cash" };
const SWIPE_PX = 90;
const EXIT_MS = 220;
const reduceMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * The review queue as a card stack: answer with a tap, a number key (desktop) or swipe the
 * card away to skip it (phones). Skipping never changes data; the buttons always work too.
 */
export default function ReviewFlow({ onDone, doneLabel = "Done" }) {
  const [queue, setQueue] = useState(null);
  const [answered, setAnswered] = useState(0);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const top = useRef(null);
  const drag = useRef(null);

  useEffect(() => {
    api.get("/api/review").then((r) => setQueue(r.data)).catch(() => setError("Couldn't load your questions."));
  }, []);

  const card = queue?.items?.[0];
  const options = useMemo(() => (card ? card.options.filter((o) => o.value !== "skip") : []), [card]);

  const answer = useCallback(async (value, direction = value === "skip" ? -1 : 1) => {
    if (!card || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data: next } = await api.post(`/api/review/${encodeURIComponent(card.id)}/answer`, { answer: value });
      const el = top.current;
      if (el && !reduceMotion()) {
        el.style.transition = `transform ${EXIT_MS}ms var(--ease-out), opacity ${EXIT_MS}ms var(--ease-out)`;
        el.style.transform = `translateX(${direction * 110}%) rotate(${direction * 6}deg)`;
        el.style.opacity = "0";
        await new Promise((r) => setTimeout(r, EXIT_MS));
      }
      setQueue(next);
      if (value !== "skip") setAnswered((n) => n + 1);
    } catch (err) {
      setError(err?.response?.status === 403 ? err.response.data.detail : "Couldn't save that answer. Try again.");
      if (top.current) { top.current.style.transform = ""; top.current.style.opacity = ""; }
    } finally {
      setBusy(false);
    }
  }, [card, busy]);

  // Keyboard: 1-9 pick an option, S or ← → skip
  useEffect(() => {
    if (!card) return undefined;
    const onKey = (e) => {
      if (e.target.closest?.("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
      const n = Number(e.key);
      if (n >= 1 && n <= options.length) { e.preventDefault(); answer(options[n - 1].value); }
      else if (e.key === "s" || e.key === "S" || e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); answer("skip", e.key === "ArrowRight" ? 1 : -1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, options, answer]);

  // Swipe: the card follows the finger; past the threshold it's skipped
  const onPointerDown = (e) => {
    if (e.pointerType === "mouse" || e.target.closest("button")) return;
    drag.current = { x: e.clientX, dx: 0 };
    top.current.setPointerCapture(e.pointerId);
    top.current.style.transition = "none";
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    drag.current.dx = e.clientX - drag.current.x;
    top.current.style.transform = `translateX(${drag.current.dx}px) rotate(${drag.current.dx / 40}deg)`;
  };
  const onPointerUp = () => {
    if (!drag.current) return;
    const { dx } = drag.current;
    drag.current = null;
    if (Math.abs(dx) > SWIPE_PX) answer("skip", Math.sign(dx));
    else { top.current.style.transition = `transform ${EXIT_MS}ms var(--ease-out)`; top.current.style.transform = ""; }
  };

  if (error && !queue) return <p className="text-sm text-danger">{error}</p>;
  if (!queue) return <div className="skeleton h-56 rounded-lg" aria-label="Loading questions" />;
  if (queue.count === 0) {
    return (
      <div className="text-center space-y-3 py-10 animate-rise">
        <p className="font-display text-2xl text-ink">{answered ? "All caught up." : "Nothing to review right now."}</p>
        <p className="text-sm text-muted">{answered ? `You answered ${answered} question${answered === 1 ? "" : "s"}. Your numbers are updated.` : "Questions appear here when Vaulta isn't sure about something."}</p>
        {onDone && <button onClick={onDone} className="btn-primary mt-2">{doneLabel}</button>}
      </div>
    );
  }

  const behind = queue.items.slice(1, 3);
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-baseline text-sm">
        <span className="eyebrow">{TYPE_LABELS[card.type] || "Question"}</span>
        <span className="num text-muted">{queue.count} left</span>
      </div>
      <div className="relative" aria-live="polite">
        {behind.map((c, i) => (
          <div key={c.id} aria-hidden className="absolute inset-x-0 top-0 h-full rounded-lg border border-line bg-surface transition-transform duration-slow"
            style={{ transform: `translateY(${(i + 1) * 10}px) scale(${1 - (i + 1) * 0.04})`, zIndex: 2 - i, opacity: 1 - (i + 1) * 0.25 }} />
        ))}
        <div key={card.id} ref={top} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
          className="card relative z-10 p-6 sm:p-8 shadow-2 animate-rise touch-pan-y select-none">
          <h3 className="font-display text-xl sm:text-2xl leading-snug text-ink">{card.question}</h3>
          {card.detail && <p className="mt-2 text-sm text-muted">{card.detail}</p>}
          <div className="mt-6 grid gap-2 sm:grid-cols-2">
            {options.map((o, i) => (
              <button key={o.value} onClick={() => answer(o.value)} disabled={busy}
                className="btn-secondary justify-between h-12 text-[15px]">
                <span>{o.label}</span>
                <kbd aria-hidden className="hidden pointer-fine:inline num text-micro text-muted border border-line rounded px-1.5">{i + 1}</kbd>
              </button>
            ))}
          </div>
          {error && <p className="mt-3 text-sm text-danger" role="alert">{error}</p>}
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 text-sm">
        <button onClick={() => answer("skip")} disabled={busy} className="btn-quiet">Skip <kbd aria-hidden className="hidden pointer-fine:inline text-micro text-muted border border-line rounded px-1.5 ml-1">S</kbd></button>
        <span className="text-micro text-muted hidden pointer-coarse:inline">Swipe the card to skip</span>
        {onDone && <button onClick={onDone} className="btn-quiet text-muted">Finish later</button>}
      </div>
    </div>
  );
}
