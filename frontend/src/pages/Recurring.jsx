import { useState } from "react";
import api from "../lib/api";
import { rupees, shortDay as day, useApi } from "../lib/format";

const TYPES = ["subscription", "rent", "emi", "sip", "bill", "other"];
const TYPE_LABELS = { subscription: "Subscription", rent: "Rent", emi: "EMI", sip: "SIP", bill: "Bill", other: "Other" };
const CADENCE = { weekly: "every week", monthly: "every month", yearly: "every year" };
const STATUS_STYLE = {
  active: "bg-safe/15 text-safe",
  missed: "bg-gold/15 text-gold",
  cancelled: "bg-sage-100 text-ink-400",
};


function SeriesRow({ s, onChange }) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(s.name);
  const patch = async (body) => {
    await api.patch(`/api/recurring/${s.id}`, body);
    onChange();
  };

  return (
    <div className="py-3 border-b border-sage-50 last:border-0 space-y-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        {renaming ? (
          <form onSubmit={(e) => { e.preventDefault(); setRenaming(false); patch({ name: name.trim() }); }}>
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={100}
              onBlur={() => setRenaming(false)} className="border border-sage-200 rounded px-2 py-0.5 text-sm" />
          </form>
        ) : (
          <button onClick={() => setRenaming(true)} className="font-medium text-sm text-ink-900 hover:underline" title="Rename">{s.name}</button>
        )}
        <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLE[s.status]}`}>{s.status}</span>
        {s.price_change && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-danger/10 text-danger">
            Price {Number(s.price_change.new) > Number(s.price_change.old) ? "up" : "down"}: {rupees(s.price_change.old)} → {rupees(s.price_change.new)}
          </span>
        )}
        {s.user_status !== "confirmed" && <span className="text-xs text-ink-400">detected</span>}
        <span className="ml-auto num text-sm text-ink-900">{rupees(s.typical_amount)}</span>
      </div>
      <div className="flex items-center gap-2 flex-wrap text-xs text-ink-500">
        <span>{CADENCE[s.cadence]}</span>
        <span>·</span>
        <span>{s.status === "cancelled" ? `last paid ${day(s.last_date)}` : `next ${day(s.next_expected)}`}</span>
        <span>·</span>
        <select value={s.type} onChange={(e) => patch({ type: e.target.value })} aria-label="Type"
          className="border border-sage-200 rounded px-1 py-0.5 bg-surface">
          {TYPES.map((t) => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
        </select>
        <div className="ml-auto flex gap-1">
          {s.user_status !== "confirmed" && (
            <button onClick={() => patch({ user_status: "confirmed" })} className="px-2 py-0.5 rounded bg-forest-50 text-forest-700">Confirm</button>
          )}
          {s.type === "subscription" && ["keep", "review"].map((u) => (
            <button key={u} onClick={() => patch({ usage: u })}
              className={`px-2 py-0.5 rounded ${s.usage === u ? "bg-ink-900 text-white" : "bg-sage-100 text-ink-600"}`}>
              {u === "keep" ? "Keep" : "Review"}
            </button>
          ))}
          <button onClick={() => patch({ user_status: "dismissed" })} className="px-2 py-0.5 rounded text-ink-400 hover:text-danger">Not recurring</button>
        </div>
      </div>
    </div>
  );
}

export default function Recurring() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/recurring", refreshKey);
  const load = () => setRefreshKey((k) => k + 1);

  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;

  const groups = ["active", "missed", "cancelled"].map((st) => [st, data.series.filter((s) => s.status === st)]);
  const review = data.series.filter((s) => s.usage === "review");

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div>
        <h1 className="font-display text-display-s text-ink">Recurring & subscriptions</h1>
        <p className="text-sm text-ink-500 mt-1">Detected from payments that repeat on a schedule.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="card p-5">
          <p className="text-xs font-medium text-ink-400 uppercase tracking-widest">Committed per month</p>
          <p className="num text-2xl font-semibold text-ink-900 mt-2">{rupees(data.monthly_committed)}</p>
        </div>
        <div className="card p-5 sm:col-span-2">
          <p className="text-xs font-medium text-ink-400 uppercase tracking-widest mb-2">Upcoming in the next 14 days</p>
          {data.upcoming.length ? (
            <ul className="space-y-1 text-sm">
              {data.upcoming.map((s) => (
                <li key={s.id} className="flex justify-between">
                  <span className="text-ink-700">{day(s.next_expected)} · {s.name}</span>
                  <span className="num">{rupees(s.typical_amount)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-400">Nothing due.</p>}
        </div>
      </div>

      {review.length > 0 && (
        <div className="card p-4 text-sm text-ink-700">
          Marked for review: {review.map((s) => s.name).join(", ")}: {rupees(review.reduce((t, s) => t + Number(s.monthly_amount), 0))}/month.
        </div>
      )}

      {data.series.length === 0 ? (
        <div className="card p-6 text-center text-sm text-ink-400">
          No recurring payments yet. They appear after 3 payments on a schedule (2 for yearly).
        </div>
      ) : groups.map(([st, list]) => list.length > 0 && (
        <section key={st} className="card p-5">
          <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest mb-1">
            {st === "active" ? "Active" : st === "missed" ? "Payment late" : "Stopped"} ({list.length})
          </h2>
          {list.map((s) => <SeriesRow key={s.id} s={s} onChange={load} />)}
        </section>
      ))}
    </div>
  );
}
