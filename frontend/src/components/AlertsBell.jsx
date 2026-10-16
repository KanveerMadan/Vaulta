import { useEffect, useRef, useState } from "react";
import api from "../lib/api";
import { useApi } from "../lib/format";

const POLL_MS = 60000;
const when = (iso) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/** The bell: unread count, and the latest alerts in a panel. Opening it marks them read. */
export default function AlertsBell() {
  const [tick, setTick] = useState(0);
  const { data } = useApi("/api/alerts", tick);
  const [list, setList] = useState(null);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const current = list ?? data;

  useEffect(() => {
    const id = setInterval(() => { setList(null); setTick((t) => t + 1); }, POLL_MS);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const toggle = async () => {
    const opening = !open;
    setOpen(opening);
    if (opening && current?.unread) {
      try { setList((await api.post("/api/alerts/read", {})).data); } catch { /* the demo is read-only; leave them unread */ }
    }
  };
  const unread = current?.unread ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button onClick={toggle} aria-label={unread ? `Alerts, ${unread} unread` : "Alerts"} aria-expanded={open}
        className="relative w-11 h-11 flex items-center justify-center rounded-lg text-ink-500 hover:bg-sage-100">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span data-testid="unread-count" className="absolute top-1 right-1 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-danger text-white text-[10px] font-semibold flex items-center justify-center">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Alerts" className="fixed sm:absolute left-2 right-2 sm:left-auto sm:right-0 top-16 sm:top-12 sm:w-96 z-50 card max-h-[70dvh] overflow-y-auto">
          <p className="px-4 pt-3 pb-2 text-xs font-semibold text-ink-400 uppercase tracking-widest">Alerts</p>
          {current?.items?.length ? (
            <ul className="divide-y divide-sage-50">
              {current.items.map((a) => (
                <li key={a.id} className={`px-4 py-3 text-sm ${a.read ? "text-ink-600" : "text-ink-900 font-medium"}`}>
                  <p>{a.message}</p>
                  <p className="text-xs text-ink-400 font-normal mt-0.5">{when(a.created_at)}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 pb-4 text-sm text-ink-500">No alerts yet. Budget warnings, duplicate charges, renewals and more will show up here.</p>
          )}
        </div>
      )}
    </div>
  );
}
