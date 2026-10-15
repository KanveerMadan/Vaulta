import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "../lib/api";
import { rupees, useApi } from "../lib/format";

const TYPES = [["weekly", "Weekly"], ["monthly", "Monthly"], ["annual", "Annual"]];

function Section({ title, children }) {
  return (
    <section className="card p-5 space-y-2">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">{title}</h2>
      {children}
    </section>
  );
}

function Rows({ items, render }) {
  if (!items?.length) return <p className="text-sm text-ink-400">None.</p>;
  return <ul className="text-sm space-y-1">{items.map((x, i) => <li key={i} className="flex justify-between gap-3">{render(x)}</li>)}</ul>;
}

const pct = (v) => (v == null ? "—" : `${v}%`);

function ReportView({ report }) {
  const d = report.data;
  const t = d.totals;
  const p = d.previous;
  const anomalyText = (a) => ({
    duplicate_charge: `Possible duplicate: ${a.merchant} ${rupees(a.amount)}`,
    unusual_amount: `Unusual: ${rupees(a.amount)} at ${a.merchant} (usually ${rupees(a.typical)})`,
    category_spike: `${a.category} spiked to ${rupees(a.amount)} (usually ${rupees(a.trailing_average)})`,
    unreversed_failed_upi: `Failed payment to ${a.merchant} not reversed: ${rupees(a.amount)}`,
  }[a.type]);
  return (
    <div className="space-y-4">
      <div>
        <Link to="/reports" className="text-xs text-forest-600 hover:underline">← All reports</Link>
        <h1 className="font-display text-2xl font-semibold text-ink-900 mt-1">{d.period.label}</h1>
      </div>
      <Section title="Summary"><p className="text-sm text-ink-700 whitespace-pre-line leading-relaxed">{report.narrative}</p></Section>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[["Spent", rupees(t.spend)], ["Income", rupees(t.income)], ["Saved", rupees(t.saved)], ["Savings rate", pct(t.savings_rate_pct)]].map(([k, v]) => (
          <div key={k} className="card p-4"><p className="text-xs text-ink-400">{k}</p><p className="font-mono text-lg font-semibold">{v}</p></div>
        ))}
      </div>
      <Section title="Compared with the previous period">
        <p className="text-sm text-ink-700">
          {rupees(p.spend)} before → {rupees(t.spend)} now
          {p.spend_change_pct != null && ` (${Number(p.spend_change) >= 0 ? "+" : ""}${p.spend_change_pct}%)`}
        </p>
      </Section>
      {d.budget && (d.budget.overall || d.budget.categories.length > 0) && (
        <Section title="Budgets">
          <Rows items={[...(d.budget.overall ? [d.budget.overall] : []), ...d.budget.categories]} render={(b) => (
            <><span>{b.category}</span><span className={b.over ? "text-danger" : "text-ink-500"}>{rupees(b.spent)} / {rupees(b.limit)}</span></>
          )} />
        </Section>
      )}
      <div className="grid sm:grid-cols-2 gap-4">
        <Section title="Top categories"><Rows items={d.top_categories} render={(c) => <><span>{c.name}</span><span className="font-mono">{rupees(c.amount)}</span></>} /></Section>
        <Section title="Top merchants"><Rows items={d.top_merchants} render={(m) => <><span>{m.name}</span><span className="font-mono">{rupees(m.amount)}</span></>} /></Section>
      </div>
      <Section title="Recurring">
        <Rows items={[
          ...d.recurring.new.map((s) => ({ text: `New: ${s.name}`, amount: s.amount })),
          ...d.recurring.price_changed.map((s) => ({ text: `Price change: ${s.name} ${rupees(s.old_amount)} →`, amount: s.amount })),
          ...d.recurring.cancelled.map((s) => ({ text: `Stopped: ${s.name}`, amount: s.amount })),
        ]} render={(x) => <><span>{x.text}</span><span className="font-mono">{rupees(x.amount)}</span></>} />
      </Section>
      <Section title="Worth a look"><Rows items={d.anomalies} render={(a) => <><span>{anomalyText(a)}</span><span className="text-ink-400">{a.date}</span></>} /></Section>
      <Section title="Money owed">
        <Rows items={[...d.people.owed_to_you.map((x) => ({ ...x, text: `${x.name} owes you` })), ...d.people.you_owe.map((x) => ({ ...x, text: `You owe ${x.name}` }))]}
          render={(x) => <><span>{x.text}{x.days != null ? ` · ${x.days} days` : ""}</span><span className="font-mono">{rupees(x.amount)}</span></>} />
      </Section>
      {d.safe_to_spend_next?.amount != null && (
        <Section title="Safe to spend next period">
          <p className="text-sm text-ink-700">
            {rupees(d.safe_to_spend_next.amount)} ({rupees(d.safe_to_spend_next.per_day)} a day), from your {d.safe_to_spend_next.basis} after {rupees(d.safe_to_spend_next.recurring_committed)} of recurring payments.
          </p>
        </Section>
      )}
      {d.wrapped && (
        <Section title="Money Wrapped">
          <ul className="text-sm space-y-1 text-ink-700">
            {d.wrapped.top_merchant_by_visits && <li>Most visited: {d.wrapped.top_merchant_by_visits.name} ({d.wrapped.top_merchant_by_visits.visits} times)</li>}
            {d.wrapped.top_merchant_by_spend && <li>Biggest spend: {d.wrapped.top_merchant_by_spend.name} ({rupees(d.wrapped.top_merchant_by_spend.amount)})</li>}
            {d.wrapped.most_expensive_month && <li>Most expensive month: {d.wrapped.most_expensive_month.month} ({rupees(d.wrapped.most_expensive_month.amount)})</li>}
            <li>Subscriptions: {rupees(d.wrapped.subscriptions_total)}</li>
            {d.wrapped.biggest_category_change && <li>Biggest change: {d.wrapped.biggest_category_change.category} ({rupees(d.wrapped.biggest_category_change.last_year)} → {rupees(d.wrapped.biggest_category_change.this_year)})</li>}
            <li>Transactions: {d.wrapped.transaction_count}</li>
            <li>Savings rate: {pct(d.wrapped.savings_rate_pct)}</li>
          </ul>
        </Section>
      )}
    </div>
  );
}

function Archive() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/reports", refreshKey);
  const [busy, setBusy] = useState(null);
  const generate = async (type) => {
    setBusy(type);
    try { await api.post("/api/reports/generate", { period_type: type }); setRefreshKey((k) => k + 1); } finally { setBusy(null); }
  };
  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900">Reports</h1>
        <p className="text-sm text-ink-500 mt-1">Weekly, monthly and yearly summaries, also sent by email if you choose in Settings.</p>
      </div>
      {TYPES.map(([type, title]) => {
        const items = data.filter((r) => r.period_type === type);
        return (
          <section key={type} className="card p-5">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">{title}</h2>
              <button onClick={() => generate(type)} disabled={busy === type} className="text-xs text-forest-600 font-medium disabled:opacity-50">
                {busy === type ? "Building…" : "Build latest"}
              </button>
            </div>
            {items.length ? (
              <ul className="divide-y divide-sage-50">
                {items.map((r) => (
                  <li key={r.id}>
                    <Link to={`/reports/${r.id}`} className="flex justify-between py-2 text-sm hover:text-forest-600">
                      <span>{r.label}</span><span className="font-mono text-ink-500">{rupees(r.spend)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-ink-400">No {title.toLowerCase()} reports yet.</p>}
          </section>
        );
      })}
    </div>
  );
}

function OneReport({ id }) {
  const { data, error } = useApi(`/api/reports/${id}`, id);
  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;
  return <ReportView report={data} />;
}

export default function Reports() {
  const { id } = useParams();
  return <div className="max-w-3xl mx-auto">{id ? <OneReport id={id} /> : <Archive />}</div>;
}
