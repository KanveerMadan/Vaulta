import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "../lib/api";
import { GOAL_STATUS, useApi } from "../lib/format";
import { formatINR } from "../lib/money";
import Money from "../ui/Money";
import Meter from "../ui/Meter";
import BarChart from "../ui/BarChart";

const TYPES = [["weekly", "Weekly"], ["monthly", "Monthly"], ["annual", "Annual"]];



const pct = (v) => (v == null ? "n/a" : `${v}%`);
const TYPE_NAME = { weekly: "Weekly report", monthly: "Monthly report", annual: "Annual report" };
const longDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });

function Block({ title, children, className = "" }) {
  return (
    <section className={`rule pt-5 ${className}`}>
      <h2 className="eyebrow mb-3">{title}</h2>
      {children}
    </section>
  );
}

function ListOf({ items, render, empty = "Nothing this period." }) {
  if (!items?.length) return <p className="text-sm text-muted">{empty}</p>;
  return <ul className="divide-y divide-line">{items.map((x, i) => <li key={i} className="flex items-baseline justify-between gap-4 py-2 text-[15px]">{render(x)}</li>)}</ul>;
}

function ReportView({ report }) {
  const d = report.data;
  const t = d.totals;
  const p = d.previous;
  const change = Number(p.spend_change);
  const anomalyText = (a) => ({
    duplicate_charge: `Possible duplicate at ${a.merchant}`,
    unusual_amount: `Unusually large at ${a.merchant}`,
    category_spike: `${a.category} jumped`,
    unreversed_failed_upi: `Failed payment to ${a.merchant} not refunded`,
  }[a.type] || a.type);
  const budgets = d.budget ? [...(d.budget.overall ? [d.budget.overall] : []), ...d.budget.categories] : [];
  const lines = report.narrative.split("\n").filter(Boolean);
  const suggestion = lines.find((l) => l.startsWith("Suggestion:"));
  const story = lines.filter((l) => l !== suggestion);

  return (
    <article className="max-w-3xl mx-auto">
      <Link to="/reports" className="text-sm text-accent-text hover:underline">← All reports</Link>
      <header className="mt-6 pb-8">
        <p className="eyebrow">{TYPE_NAME[report.period_type]}</p>
        <h1 className="mt-2 font-display text-display-m sm:text-[4rem] leading-none tracking-tight text-ink">{d.period.label}</h1>
        <p className="mt-3 text-sm text-muted">{longDate(d.period.start)} to {longDate(d.period.end)}</p>
      </header>

      <section aria-labelledby="summary-title">
        <h2 id="summary-title" className="sr-only">Summary</h2>
        <p className="font-display text-xl sm:text-2xl leading-snug text-ink">{story.join(" ")}</p>
        {suggestion && <p className="mt-4 text-ink-2 border-l-2 border-accent pl-4">{suggestion}</p>}
      </section>

      <dl className="mt-10 grid grid-cols-2 sm:grid-cols-4 border-y border-line divide-x divide-line">
        {[["Spent", <Money key="s" value={t.spend} />], ["Income", <Money key="i" value={t.income} />],
          ["Saved", <Money key="v" value={t.saved} />], ["Kept", pct(t.savings_rate_pct)]].map(([k, v]) => (
          <div key={k} className="py-4 px-4 first:pl-0 [&:nth-child(3)]:pl-0 sm:[&:nth-child(3)]:pl-4">
            <dt className="text-micro text-muted">{k}</dt>
            <dd className="mt-1 font-display text-2xl text-ink num">{v}</dd>
          </div>
        ))}
      </dl>
      {p.spend_change_pct != null && (
        <p className="mt-4 text-sm text-ink-2">
          {change > 0 ? "▲" : "▼"} <Money value={Math.abs(change)} className="font-semibold text-ink" /> {change > 0 ? "more" : "less"} than the previous period
          ({p.spend_change_pct > 0 ? "+" : ""}{p.spend_change_pct}%), when you spent <Money value={p.spend} />.
        </p>
      )}

      <div className="mt-10 grid gap-10 sm:grid-cols-2">
        <Block title="Top categories">
          {d.top_categories?.length ? <BarChart title="Spent by category" data={d.top_categories.map((c) => ({ label: c.name, value: c.amount }))} />
            : <p className="text-sm text-muted">No spending this period.</p>}
        </Block>
        <Block title="Top merchants">
          <ListOf items={d.top_merchants} render={(m) => <><span className="text-ink truncate">{m.name}</span><Money value={m.amount} className="text-ink-2 shrink-0" /></>} />
        </Block>
      </div>

      {d.tags?.length > 0 && (
        <Block title="By tag" className="mt-10">
          <ListOf items={d.tags} render={(t) => <><span className="text-ink truncate">#{t.name}</span><Money value={t.amount} className="text-ink-2 shrink-0" /></>} />
          <p className="mt-2 text-micro text-muted">A transaction with two tags counts under both.</p>
        </Block>
      )}

      {budgets.length > 0 && (
        <Block title="Budgets" className="mt-10">
          <div className="space-y-4">{budgets.map((b) => <Meter key={b.subcategory || b.category} label={b.group ? `${b.group} › ${b.category}` : b.category} spent={Number(b.spent)} limit={Number(b.limit)} />)}</div>
        </Block>
      )}

      <div className="mt-10 grid gap-10 sm:grid-cols-2">
        <Block title="Recurring">
          <ListOf empty="No new, stopped or re-priced payments." items={[
            ...d.recurring.new.map((s) => ({ text: `New: ${s.name}`, amount: s.amount })),
            ...d.recurring.price_changed.map((s) => ({ text: `${s.name}, was ${formatINR(s.old_amount)}`, amount: s.amount })),
            ...d.recurring.cancelled.map((s) => ({ text: `Stopped: ${s.name}`, amount: s.amount })),
          ]} render={(x) => <><span className="text-ink">{x.text}</span><Money value={x.amount} className="text-ink-2" /></>} />
        </Block>
        <Block title="Worth a look">
          <ListOf empty="Nothing unusual." items={d.anomalies} render={(a) => <><span className="text-ink">{anomalyText(a)}</span><span className="text-muted text-sm shrink-0">{a.amount ? formatINR(a.amount) : ""}</span></>} />
        </Block>
        <Block title="Money owed">
          <ListOf empty="Nobody owes anybody." items={[...d.people.owed_to_you.map((x) => ({ ...x, text: `${x.name} owes you` })), ...d.people.you_owe.map((x) => ({ ...x, text: `You owe ${x.name}` }))]}
            render={(x) => <><span className="text-ink">{x.text}{x.days != null ? <span className="text-muted text-sm">, {x.days} days</span> : null}</span><Money value={x.amount} className="text-ink-2" /></>} />
        </Block>
        {d.goals?.length > 0 && (
          <Block title="Goals">
            <ListOf items={d.goals} render={(g) => <><span className="text-ink">{g.name} <span className="text-muted text-sm">{GOAL_STATUS[g.status]}</span></span><span className="text-ink-2 text-sm"><Money value={g.saved} /> of <Money value={g.target_amount} /></span></>} />
          </Block>
        )}
      </div>

      {d.safe_to_spend_next?.amount != null && (
        <Block title="Next period" className="mt-10">
          <p className="text-ink-2">Safe to spend: <Money value={d.safe_to_spend_next.amount} className="font-semibold text-ink" /> (<Money value={d.safe_to_spend_next.per_day} /> a day), from your {d.safe_to_spend_next.basis} after <Money value={d.safe_to_spend_next.recurring_committed} /> of recurring payments.</p>
        </Block>
      )}
      {d.wrapped && (
        <section className="mt-12 rounded-lg bg-inverse text-on-inverse p-8 flex flex-col sm:flex-row sm:items-center gap-4 justify-between">
          <div>
            <h2 className="font-display text-2xl">Money Wrapped</h2>
            <p className="text-sm opacity-80 mt-1">Your year in a few screens, with a card you can share.</p>
          </div>
          <Link to={`/reports/${report.id}/wrapped`} className="btn bg-on-inverse text-inverse hover:opacity-90 h-11 px-5">Play Money Wrapped</Link>
        </section>
      )}
    </article>
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
  if (!data) return <div className="space-y-3" aria-label="Loading"><div className="skeleton h-10 w-48" /><div className="skeleton h-4 w-full" /><div className="skeleton h-4 w-3/4" /></div>;
  return (
    <div className="space-y-10">
      <header>
        <h1 className="font-display text-display-s text-ink">Reports</h1>
        <p className="text-ink-2 mt-2">Weekly, monthly and yearly summaries. Each one is readable in about a minute, and can come by email (Settings).</p>
      </header>
      {TYPES.map(([type, title]) => {
        const items = data.filter((r) => r.period_type === type);
        return (
          <section key={type} aria-labelledby={`h-${type}`}>
            <div className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
              <h2 id={`h-${type}`} className="font-display text-xl text-ink">{title}</h2>
              <button onClick={() => generate(type)} disabled={busy === type} className="btn-quiet text-sm text-accent-text">
                {busy === type ? "Building…" : "Build latest"}
              </button>
            </div>
            {items.length ? (
              <ul className="divide-y divide-line">
                {items.map((r) => (
                  <li key={r.id} className="flex items-center gap-3">
                    <Link to={`/reports/${r.id}`} className="group flex-1 flex items-baseline justify-between gap-4 py-3 hover:text-accent-text">
                      <span className="text-[15px] text-ink group-hover:text-accent-text">{r.label}</span>
                      <span className="text-sm text-muted"><Money value={r.spend} className="text-ink-2" /> spent</span>
                    </Link>
                    {type === "annual" && <Link to={`/reports/${r.id}/wrapped`} className="tag-positive hover:underline">Wrapped</Link>}
                  </li>
                ))}
              </ul>
            ) : <p className="py-3 text-sm text-muted">No {title.toLowerCase()} reports yet. They appear on their own, or use Build latest.</p>}
          </section>
        );
      })}
    </div>
  );
}

function OneReport({ id }) {
  const { data, error } = useApi(`/api/reports/${id}`, id);
  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="space-y-3" aria-label="Loading"><div className="skeleton h-10 w-48" /><div className="skeleton h-4 w-full" /><div className="skeleton h-4 w-3/4" /></div>;
  return <ReportView report={data} />;
}

export default function Reports() {
  const { id } = useParams();
  return <div className="max-w-3xl mx-auto">{id ? <OneReport id={id} /> : <Archive />}</div>;
}
