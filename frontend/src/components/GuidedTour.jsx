import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import api from "../lib/api";

// The guided tour of the home page (Phase 8). Its place is kept on the server (/api/tour), so it resumes on any device;
// Settings and the "?" button replay it. Each step points at an element marked data-tour="<id>" and says something
// about the user's own numbers, or what will appear there when there's no data yet. On phones the step is a bottom
// sheet; elsewhere a card next to the element. Keyboard: ←/→ move, Escape skips, Tab stays inside.

const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function useTargetRect(id, step) {
  const [rect, setRect] = useState(null);
  useLayoutEffect(() => {
    const find = () => [...document.querySelectorAll(`[data-tour="${id}"]`)].find((e) => e.getClientRects().length);
    const measure = () => { const el = find(); setRect(el ? el.getBoundingClientRect() : null); };
    const target = find();
    // a target taller than most of the screen (a long list) is shown from its top, the rest centred
    target?.scrollIntoView({ block: target.offsetHeight > window.innerHeight * 0.6 ? "start" : "center",
      behavior: reduced() ? "auto" : "smooth" });
    const raf = requestAnimationFrame(measure);
    const t = setTimeout(measure, reduced() ? 0 : 350);         // after the smooth scroll settles
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    return () => { cancelAnimationFrame(raf); clearTimeout(t); window.removeEventListener("resize", measure); window.removeEventListener("scroll", measure); };
  }, [id, step]);
  return rect;
}

export default function GuidedTour({ steps, start = 0, onFinish }) {
  const [i, setI] = useState(Math.min(start, steps.length - 1));
  const step = steps[i];
  const rect = useTargetRect(step.id, i);
  const box = useRef(null);
  const [phone, setPhone] = useState(() => window.matchMedia("(max-width: 639px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const on = () => setPhone(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const go = useCallback((next) => {
    if (next >= steps.length) { onFinish("done"); return; }
    setI(next);
    api.patch("/api/tour", { step: next }).catch(() => {});
  }, [steps.length, onFinish]);

  // focus the card on every step, keep Tab inside it, arrows move, Escape skips
  useEffect(() => { box.current?.querySelector("[data-primary]")?.focus(); }, [i]);
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); onFinish("skipped"); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(i + 1); }
      else if (e.key === "ArrowLeft" && i > 0) { e.preventDefault(); go(i - 1); }
      else if (e.key === "Tab" && box.current) {
        const f = [...box.current.querySelectorAll("button")];
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        else if (!box.current.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [i, go, onFinish]);

  const pad = 8;
  const spot = rect && { top: rect.top - pad, left: rect.left - pad, width: rect.width + 2 * pad, height: rect.height + 2 * pad };
  // the card goes below the element if there's room, else above, else inside the screen's bottom-right corner (a tall
  // element); centred when the element isn't on the page
  const room = 220;
  const left = spot && Math.max(16, Math.min(spot.left, window.innerWidth - 376));
  const cardStyle = phone || !spot ? undefined
    : window.innerHeight - (spot.top + spot.height) >= room ? { top: spot.top + spot.height + 12, left }
      : spot.top >= room ? { bottom: window.innerHeight - spot.top + 12, left }
        : { bottom: 16, right: 16 };
  const motion = reduced() ? "" : "transition-all duration-200";

  // in a portal on <body>: an ancestor's transform (the page's enter animation) would otherwise become the
  // containing block of these fixed elements and shift them
  return createPortal(
    <div className="fixed inset-0 z-[60]" data-testid="tour">
      {spot ? (
        <div aria-hidden className={`fixed rounded-md pointer-events-none ${motion}`}
          style={{ ...spot, boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.55)", outline: "2px solid rgb(var(--accent))", outlineOffset: 2 }} />
      ) : <div aria-hidden className="fixed inset-0 bg-black/55" />}
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-body"
        className={phone
          ? "fixed inset-x-0 bottom-0 rounded-t-lg border-t border-line bg-surface p-5 pb-safe-3 shadow-lg"
          : `fixed w-[22rem] max-w-[calc(100vw-2rem)] rounded-md border border-line bg-surface p-5 shadow-lg ${!spot ? "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" : ""}`}
        style={cardStyle}>
        <p className="text-micro text-muted" aria-live="polite">Step {i + 1} of {steps.length}</p>
        <h2 id="tour-title" className="mt-1 font-display text-lg text-ink">{step.title}</h2>
        <p id="tour-body" className="mt-2 text-sm text-ink-2">{step.body}</p>
        <div className="mt-4 flex items-center gap-2">
          <button onClick={() => onFinish("skipped")} className="btn-quiet text-muted mr-auto">Skip tour</button>
          {i > 0 && <button onClick={() => go(i - 1)} className="btn-secondary">Back</button>}
          <button data-primary onClick={() => go(i + 1)} className="btn-primary">{i === steps.length - 1 ? "Done" : "Next"}</button>
        </div>
      </div>
    </div>
  , document.body);
}
