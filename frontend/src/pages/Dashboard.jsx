import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarBlank, CaretLeft, CaretRight, CheckCircle, ClipboardText, Plugs, Receipt, TrendUp, Warning } from "@phosphor-icons/react";
import api from "../lib/api";
import { shortDay, useApi } from "../lib/format";
import { formatINR } from "../lib/money";
import { useFinanceStore } from "../store/financeStore";
import { useAuthStore } from "../store/authStore";
import SubscriptionBanner from "../components/SubscriptionBanner";
import QuickAddBar from "../components/QuickAddBar";
import { ReviewCard } from "../components/ReviewQueue";
import TransactionRow from "../components/TransactionRow";
import { ruleToast } from "../lib/ruleToast";
import Money from "../ui/Money";
import Meter from "../ui/Meter";
import Empty from "../ui/Empty";
import { SkeletonRows } from "../ui/Skeleton";

const RECENT = 10;
const monthKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
const shiftMonth = (key, by) => { const [y, m] = key.split("-").map(Number); return monthKey(new Date(y, m - 1 + by, 1)); };
const monthLabel = (key) => new Date(`${key}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
const lastDay = (key) => { const [y, m] = key.split("-").map(Number); return new Date(y, m, 0).getDate(); };
const todayLong = () => new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });

function Panel({ title, action, children, className = "" }) {
  return (
    <section className={`rule pt-4 ${className}`} aria-label={title}>
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** The hero: what can be spent today, in the display face, and the arithmetic on tap. */
function SafeToSpend({ safe }) {
  const [open, setOpen] = useState(false);
  if (!safe) return null;
  if (safe.amount === null) {
    return (
      <div>
        <p className="text-[15px] text-ink-2">Safe to spend today</p>
        <p className="mt-2 font-display text-3xl text-ink-2">Not yet</p>
        <Empty to="/budgets" cta="Set a monthly budget">It needs a budget or this month's income to measure against.</Empty>
      </div>
    );
  }
  return (
    <div>
      <p className="text-sm text-muted"><time dateTime={new Date().toISOString().slice(0, 10)}>{todayLong()}</time></p>
      <p className="mt-3 text-[15px] text-ink-2">Safe to spend today</p>
      <Money value={safe.amount} decimals={0} className="block font-display font-semibold text-[clamp(3.6rem,9vw,6rem)] leading-[0.9] tracking-[-0.04em] text-ink mt-1" />
      <p className="mt-3 text-sm text-ink-2">
        <Money value={safe.remaining} decimals={0} className="font-semibold text-ink" /> left this month for <span className="num">{safe.days_left_including_today}</span> day{safe.days_left_including_today === 1 ? "" : "s"}
      </p>
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="mt-1 text-sm font-medium text-accent-text hover:underline">
        {open ? "Hide the working" : "How is this worked out?"}
      </button>
      {open && (
        <p className="mt-2 text-sm text-ink-2 max-w-[48ch] animate-rise" data-testid="safe-explanation">
          Your {safe.basis} is {formatINR(safe.limit)}. You've spent {formatINR(safe.spent_so_far)} and {formatINR(safe.recurring_due)} of
          recurring payments is still due, leaving {formatINR(safe.remaining)} for {safe.days_left_including_today} day{safe.days_left_including_today === 1 ? "" : "s"} including today.
        </p>
      )}
    </div>
  );
}

const STATUS = {
  green: { icon: CheckCircle, cls: "text-accent-text" },
  amber: { icon: Warning, cls: "text-warn" },
  red: { icon: TrendUp, cls: "text-danger" },
};

/** Where the month is heading: spent, still due and the projection, against the limit. */
function Outlook({ outlook, current }) {
  const st = STATUS[outlook.status];
  const diff = Number(outlook.difference);
  const limit = Number(outlook.limit) || 0;
  const scale = Math.max(limit, Number(outlook.forecast), 1);
  const seg = (v) => `${Math.max((Number(v) / scale) * 100, 0)}%`;
  const projected = Math.max(Number(outlook.forecast) - Number(outlook.so_far) - Number(outlook.recurring_due), 0);
  return (
    <div data-testid="outlook">
      <p className="text-sm text-muted">{current ? "This month" : monthLabel(outlook.month)}</p>
      <p className="mt-3 text-[15px] text-ink-2">{current ? "On pace for" : "Spent"}</p>
      <Money value={outlook.forecast} decimals={0} className="block font-display font-semibold text-[2.6rem] leading-none tracking-tight text-ink mt-1" />
      {st ? (
        <p className={`mt-3 flex items-center gap-1.5 text-sm font-medium ${st.cls}`}>
          <st.icon size={16} weight="bold" aria-hidden />
          <Money value={Math.abs(diff)} decimals={0} tone={false} /> {diff > 0 ? "over" : "under"} {outlook.basis === "income this month" ? "your income" : "budget"}
        </p>
      ) : <Empty to="/budgets" cta="Set a budget">No budget to compare with yet.</Empty>}
      {st && (
        <div className="mt-4" aria-hidden="true">
          <div className="relative h-2.5 rounded-full bg-sunken overflow-hidden flex">
            <span className="h-full bg-accent" style={{ width: seg(outlook.so_far) }} />
            {current && <span className="h-full outlook-due" style={{ width: seg(outlook.recurring_due) }} />}
            {current && <span className="h-full bg-line-strong" style={{ width: seg(projected) }} />}
          </div>
          <div className="relative h-4">
            {limit > 0 && <span className="absolute top-0.5 -translate-x-1/2 text-[10px] text-muted whitespace-nowrap" style={{ left: `min(${seg(limit)}, calc(100% - 1.6rem))` }}>▲ limit</span>}
          </div>
          {current && (
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-micro text-muted">
              <li><span className="inline-block w-2 h-2 rounded-sm bg-accent mr-1.5" />Spent <Money value={outlook.so_far} className="text-ink-2" /></li>
              <li><span className="inline-block w-2 h-2 rounded-sm outlook-due mr-1.5" />Still due <Money value={outlook.recurring_due} className="text-ink-2" /></li>
              <li><span className="inline-block w-2 h-2 rounded-sm bg-line-strong mr-1.5" />At this pace <Money value={projected} className="text-ink-2" /></li>
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Upcoming({ items }) {
  return (
    <Panel title="Coming up" action={<Link to="/recurring" className="text-micro font-medium text-accent-text hover:underline">All recurring</Link>}>
      {items.length ? (
        <ul className="divide-y divide-line">
          {items.map((s) => (
            <li key={s.id} className="flex items-center gap-3 py-2.5 text-sm">
              <span className="w-12 shrink-0 text-micro text-muted num">{shortDay(s.next_expected)}</span>
              <span className="flex-1 text-ink truncate">{s.name}</span>
              <Money value={s.typical_amount} className="text-ink font-medium" />
            </li>
          ))}
        </ul>
      ) : <Empty icon={CalendarBlank} to="/recurring" cta="See recurring">Nothing due in the next 14 days. Bills and subscriptions appear here once they repeat.</Empty>}
    </Panel>
  );
}

function Attention({ attention, onAnswered }) {
  const { review_count: count, review_cards: cards, anomaly_count: anomalies } = attention;
  return (
    <Panel title="Needs attention" action={count > 0 && <span className="num text-micro font-semibold px-2 py-0.5 rounded-sm bg-warn-tint text-warn">{count}</span>}>
      {count === 0 ? (
        <Empty icon={CheckCircle} title="All caught up">New questions appear here when Vaulta isn't sure about something.</Empty>
      ) : (
        <div className="space-y-4">
          {anomalies > 0 && <p className="text-sm text-ink-2 flex items-center gap-2"><Warning size={16} className="text-warn" aria-hidden />{anomalies} unusual charge{anomalies === 1 ? "" : "s"} worth a second look.</p>}
          {cards.map((c) => <div key={c.id} className="rounded-md border border-line bg-surface p-4 animate-rise"><ReviewCard card={c} onAnswered={onAnswered} /></div>)}
          {count > cards.length && <Link to="/review" className="inline-flex items-center gap-1 text-sm font-medium text-accent-text hover:underline">Answer all {count} <ArrowRight size={14} aria-hidden /></Link>}
        </div>
      )}
    </Panel>
  );
}

const ago = (iso) => {
  const mins = Math.round((Date.now() - new Date(iso)) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)} min ago`;
  if (mins < 60 * 48) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} days ago`;
};

function Coverage({ coverage, cashBalance }) {
  const s = coverage.statements, e = coverage.email;
  const items = [
    ["Statements", s.active ? `${shortDay(s.from)} ${s.from.slice(0, 4)} to ${shortDay(s.to)} ${s.to.slice(0, 4)}` : "None imported", s.active],
    ["Bank alerts", e.connected ? `Last ${ago(e.last_at)}${e.stale ? ", check forwarding" : ""}` : "Not set up", e.active],
    ["Telegram", coverage.telegram.active ? "Linked" : "Not linked", coverage.telegram.active],
    ["Cash wallet", coverage.cash.active ? `${formatINR(cashBalance)} expected in hand` : "No cash logged", coverage.cash.active],
  ];
  return (
    <Panel title="Coverage" action={coverage.needs_attention.length > 0 && <Link to="/connect" className="inline-flex items-center gap-1 text-micro font-medium text-accent-text hover:underline"><Plugs size={13} aria-hidden />Fix in Connect</Link>}>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
        {items.map(([name, text, ok]) => (
          <li key={name} className="flex items-start gap-2 text-sm">
            {ok ? <CheckCircle size={16} weight="fill" className="mt-0.5 text-accent-text shrink-0" aria-hidden />
              : <span aria-hidden className="mt-[5px] w-3 h-3 rounded-full border border-line-strong shrink-0" />}
            <span><span className="text-ink font-medium">{name}</span> <span className="text-muted">{text}</span><span className="sr-only">{ok ? ", active" : ", not active"}</span></span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function AskBar() {
  const ask = useFinanceStore((s) => s.ask);
  const [q, setQ] = useState("");
  const submit = (e) => {
    e.preventDefault();
    if (q.trim()) { ask(q.trim()); setQ(""); }
  };
  return (
    <form onSubmit={submit} className="flex gap-2" role="search">
      <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={1000} className="input flex-1"
        placeholder="Ask anything, like “how much on food this month?”" aria-label="Ask a question" />
      <button className="btn-primary shrink-0" disabled={!q.trim()}>Ask</button>
    </form>
  );
}

function PeriodTotals() {
  const [period, setPeriod] = useState("month");
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    api.get(`/api/transactions/summary?period=${period}`).then((r) => alive && setData(r.data)).catch(() => alive && setData(null));
    return () => { alive = false; };
  }, [period]);
  return (
    <Panel title="Totals" action={
      <div className="flex gap-0.5 bg-sunken rounded-sm p-0.5" role="group" aria-label="Period">
        {[["month", "Month"], ["year", "Year"], ["lifetime", "All time"]].map(([v, l]) => (
          <button key={v} onClick={() => setPeriod(v)} aria-pressed={period === v}
            className={`px-3 h-8 rounded-[6px] text-micro font-medium ${period === v ? "bg-surface text-ink shadow-1" : "text-muted"}`}>{l}</button>
        ))}
      </div>
    }>
      {data ? (
        <dl className="grid grid-cols-3 gap-3">
          {[["Spent", data.total_spend], ["Money in", data.total_received], ["Net", data.net_cash_flow]].map(([k, v]) => (
            <div key={k}><dt className="text-micro text-muted">{k}</dt><dd><Money value={v} className="font-display text-xl text-ink" /></dd></div>
          ))}
        </dl>
      ) : <div className="skeleton h-8 w-full" aria-label="Loading totals" />}
    </Panel>
  );
}

export default function Dashboard() {
  const thisMonth = monthKey(new Date());
  const [month, setMonth] = useState(thisMonth);
  const [refreshKey, setRefreshKey] = useState(0);
  const demo = useAuthStore((s) => s.demoToken);
  const current = month === thisMonth;
  const range = current ? "" : `&date_from=${month}-01T00:00:00&date_to=${month}-${lastDay(month)}T23:59:59`;
  const { data: home, error } = useApi(`/api/home?month=${month}`, refreshKey);
  const { data: txnPage } = useApi(`/api/transactions?page=1&page_size=${RECENT}${range}`, refreshKey);
  const txns = txnPage?.items ?? null;
  const { data: onboarding } = useApi("/api/onboarding", 0);
  const refresh = () => setRefreshKey((k) => k + 1);

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {!demo && <SubscriptionBanner />}
      {onboarding?.status === "active" && (
        <Link to="/onboarding" className="flex items-center justify-between gap-3 rounded-md border border-accent-line bg-accent-tint/60 px-4 py-3 text-sm text-ink hover:bg-accent-tint">
          <span>Finish setting up. Tracking coverage is {onboarding.coverage.percent}%.</span>
          <span className="font-medium text-accent-text inline-flex items-center gap-1">Continue <ArrowRight size={14} aria-hidden /></span>
        </Link>
      )}

      <div className="flex items-center justify-between gap-2">
        <h1 className="sr-only">{current ? "Today" : monthLabel(month)}</h1>
        {!current ? (
          <button onClick={() => setMonth(thisMonth)} className="btn-quiet text-accent-text"><CaretLeft size={14} aria-hidden />Back to this month</button>
        ) : <span />}
        <div className="flex items-center gap-1" role="group" aria-label="Month">
          <button onClick={() => setMonth(shiftMonth(month, -1))} className="btn-ghost w-9 h-9 !p-0" aria-label="Previous month"><CaretLeft size={16} /></button>
          <time dateTime={month} className="text-sm text-ink-2 min-w-[8.5rem] text-center">{monthLabel(month)}</time>
          <button onClick={() => setMonth(shiftMonth(month, 1))} disabled={current} className="btn-ghost w-9 h-9 !p-0" aria-label="Next month"><CaretRight size={16} /></button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-danger/30 bg-danger-tint p-5 flex items-center justify-between gap-3">
          <p className="text-sm text-ink">{error}</p>
          <button onClick={refresh} className="btn-secondary">Try again</button>
        </div>
      ) : !home ? (
        <div className="grid md:grid-cols-[1.3fr_1fr] gap-10" aria-label="Loading">
          <div className="space-y-3"><div className="skeleton h-4 w-40" /><div className="skeleton h-20 w-64" /><div className="skeleton h-4 w-56" /></div>
          <div className="space-y-3"><div className="skeleton h-4 w-24" /><div className="skeleton h-12 w-48" /><div className="skeleton h-2.5 w-full" /></div>
        </div>
      ) : (
        <>
          <div className="grid md:grid-cols-[1.3fr_1fr] gap-10 md:gap-14 items-start">
            {current ? <SafeToSpend safe={home.safe_to_spend} /> : <PeriodTotals />}
            <Outlook outlook={home.outlook} current={current} />
          </div>

          {current && (
            <div className="grid gap-3">
              <AskBar />
              <QuickAddBar onAdded={refresh} />
            </div>
          )}

          <div className="grid lg:grid-cols-[1.4fr_1fr] gap-x-12 gap-y-8 items-start">
            <div className="space-y-8 min-w-0">
              <Attention attention={home.attention} onAnswered={refresh} />
              <Panel title={current ? "Recent transactions" : `Transactions in ${monthLabel(month)}`}
                action={<Link to="/transactions" className="text-micro font-medium text-accent-text hover:underline">All transactions</Link>}>
                {txns === null ? <SkeletonRows rows={5} /> : txns.length ? (
                  <div className="divide-y divide-line">
                    {txns.map((t) => <TransactionRow key={t.id} txn={t} onChanged={refresh} onRuleLearned={(rule) => ruleToast(rule, refresh)} />)}
                  </div>
                ) : (
                  <Empty icon={Receipt} to="/connect" cta="Import a statement">
                    {current ? "No transactions yet. Add one above, forward your bank alerts, or" : "Nothing recorded in this month."}
                  </Empty>
                )}
              </Panel>
            </div>
            <div className="space-y-8 min-w-0">
              <Panel title="Budgets" action={<Link to="/budgets" className="text-micro font-medium text-accent-text hover:underline">{home.budgets.categories.length || home.budgets.overall ? "Edit" : "Set limits"}</Link>}>
                {home.budgets.overall || home.budgets.categories.length ? (
                  <div className="space-y-4">
                    {[...(home.budgets.overall ? [home.budgets.overall] : []), ...home.budgets.categories].map((b) => (
                      <Meter key={b.category} label={b.category} spent={Number(b.spent)} limit={Number(b.limit)} />
                    ))}
                  </div>
                ) : <Empty icon={ClipboardText} to="/budgets" cta="Set monthly limits">No budgets yet. Limits drive the bars here and the safe-to-spend figure.</Empty>}
              </Panel>
              {current && <Upcoming items={home.upcoming} />}
              <Coverage coverage={home.coverage} cashBalance={home.cash_balance} />
              {current && <PeriodTotals />}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
