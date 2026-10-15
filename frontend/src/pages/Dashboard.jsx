import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { rupees, shortDay, useApi } from "../lib/format";
import { useFinanceStore } from "../store/financeStore";
import { SkeletonMetricCard, SkeletonTransactionFeed } from "../components/Skeletons";
import SubscriptionBanner from "../components/SubscriptionBanner";
import QuickAddBar from "../components/QuickAddBar";
import BudgetBars from "../components/BudgetBars";
import { ReviewCard } from "../components/ReviewQueue";
import TransactionRow, { RuleToast } from "../components/TransactionRow";

const RECENT = 10;
const OUTLOOK_STYLE = {
  green: { ring: "border-forest-300", text: "text-safe", label: "On track" },
  amber: { ring: "border-gold", text: "text-gold", label: "Close to the limit" },
  red: { ring: "border-danger", text: "text-danger", label: "Over" },
};

const monthKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
const shiftMonth = (key, by) => {
  const [y, m] = key.split("-").map(Number);
  return monthKey(new Date(y, m - 1 + by, 1));
};
const monthLabel = (key) => new Date(`${key}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
const lastDay = (key) => {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m, 0).getDate();
};

function Card({ title, action, children, className = "" }) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          {title && <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

function Empty({ children, to, cta }) {
  return (
    <p className="text-sm text-ink-500">
      {children}{" "}
      {to && <Link to={to} className="font-medium text-forest-600 hover:underline">{cta} →</Link>}
    </p>
  );
}

function SafeToSpend({ safe }) {
  const [open, setOpen] = useState(false);
  if (!safe) return null;
  if (safe.amount === null) {
    return (
      <Card>
        <p className="text-sm text-ink-500">Safe to spend today</p>
        <Empty to="/budgets" cta="Set a monthly budget">
          Needs a budget or this month's income to measure against.
        </Empty>
      </Card>
    );
  }
  return (
    <section className="card p-5">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="w-full text-left">
        <p className="text-sm text-ink-500">Safe to spend today</p>
        <p className="font-mono text-4xl font-semibold text-ink-900 mt-1">{rupees(safe.amount)}</p>
        <p className="text-xs text-forest-600 mt-1">{open ? "Hide" : "How is this worked out?"}</p>
      </button>
      {open && (
        <p className="text-sm text-ink-600 mt-3" data-testid="safe-explanation">
          Your {safe.basis} is {rupees(safe.limit)}. You've spent {rupees(safe.spent_so_far)} and{" "}
          {rupees(safe.recurring_due)} of recurring payments is still due, leaving {rupees(safe.remaining)} for{" "}
          {safe.days_left_including_today} day{safe.days_left_including_today === 1 ? "" : "s"} including today.
        </p>
      )}
    </section>
  );
}

function Outlook({ outlook, current }) {
  const style = OUTLOOK_STYLE[outlook.status];
  const diff = Number(outlook.difference);
  const verb = current ? "On pace for" : "Spent";
  return (
    <section className={`card p-5 border-l-4 ${style ? style.ring : "border-sage-200"}`} data-testid="outlook">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest mb-2">{current ? "Month forecast" : "Month total"}</h2>
      <p className="text-lg text-ink-900">
        {verb} <span className="font-mono font-semibold">{rupees(outlook.forecast)}</span>
        {style && (
          <span className={`${style.text} font-medium`}>
            {" — "}{diff > 0 ? `${rupees(diff)} over` : `${rupees(-diff)} under`} {outlook.basis === "income this month" ? "your income" : "budget"}
          </span>
        )}
      </p>
      {!style ? (
        <Empty to="/budgets" cta="Set a budget">No budget to compare with.</Empty>
      ) : current && (
        <p className="text-xs text-ink-400 mt-1">
          {rupees(outlook.so_far)} so far · {rupees(outlook.recurring_due)} recurring still due · {rupees(outlook.discretionary_daily)}/day for {outlook.days_left} more days
        </p>
      )}
    </section>
  );
}

function Budgets({ budgets }) {
  const rows = [...(budgets.overall ? [budgets.overall] : []), ...budgets.categories]
    .map((b) => ({ category: b.category, spent: Number(b.spent), limit: Number(b.limit) }));
  return (
    <Card title="Budgets" action={<Link to="/budgets" className="text-xs text-forest-600 font-medium hover:underline">{rows.length ? "Edit" : "Set limits"} →</Link>}>
      {rows.length ? <BudgetBars rows={rows} /> : (
        <Empty to="/budgets" cta="Set monthly limits">No budgets yet. Limits turn into the bars here and the safe-to-spend figure.</Empty>
      )}
    </Card>
  );
}

function Upcoming({ items }) {
  return (
    <Card title="Upcoming · 14 days">
      {items.length ? (
        <ul className="divide-y divide-sage-50">
          {items.map((s) => (
            <li key={s.id} className="flex justify-between gap-3 py-2 text-sm">
              <span className="text-ink-800 truncate">{s.name}</span>
              <span className="shrink-0 text-ink-500"><span className="font-mono text-ink-800">{rupees(s.typical_amount)}</span> · {shortDay(s.next_expected)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty to="/recurring" cta="See recurring">Nothing due. Bills and subscriptions show up here once Vaulta has seen them repeat.</Empty>
      )}
    </Card>
  );
}

function Attention({ attention, onAnswered }) {
  const { review_count: count, review_cards: cards, anomaly_count: anomalies } = attention;
  return (
    <Card title="Needs attention" action={count > 0 && <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-gold/15 text-gold">{count}</span>}>
      {count === 0 ? (
        <p className="text-sm text-ink-500">All caught up. New questions appear here when Vaulta isn't sure about something.</p>
      ) : (
        <div className="space-y-5">
          {anomalies > 0 && <p className="text-xs text-ink-500">{anomalies} unusual charge{anomalies === 1 ? "" : "s"} worth a second look.</p>}
          {cards.map((c) => <ReviewCard key={c.id} card={c} onAnswered={onAnswered} />)}
          {count > cards.length && <Link to="/review" className="text-sm font-medium text-forest-600 hover:underline">Answer all {count} →</Link>}
        </div>
      )}
    </Card>
  );
}

const timeAgo = (iso) => {
  const mins = Math.round((Date.now() - new Date(iso)) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)} min ago`;
  if (mins < 60 * 48) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} days ago`;
};

function Coverage({ coverage, cashBalance }) {
  const s = coverage.statements, e = coverage.email;
  const items = [
    ["Statements", s.active ? `${shortDay(s.from)} ${s.from.slice(0, 4)} – ${shortDay(s.to)} ${s.to.slice(0, 4)}` : "None imported", s.active],
    ["Bank alerts", e.connected ? `Last ${timeAgo(e.last_at)}${e.stale ? " — check forwarding" : ""}` : "Not set up", e.active],
    ["Telegram", coverage.telegram.active ? "Linked" : "Not linked", coverage.telegram.active],
    ["Cash wallet", coverage.cash.active ? `${rupees(cashBalance)} expected in hand` : "No cash logged", coverage.cash.active],
  ];
  return (
    <Card title="Coverage" action={coverage.needs_attention.length > 0 && <Link to="/connect" className="text-xs text-forest-600 font-medium hover:underline">Fix in Connect →</Link>}>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {items.map(([name, text, ok]) => (
          <li key={name} className="flex items-start gap-2 text-sm">
            <span aria-hidden className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${ok ? "bg-forest-400" : "bg-sage-300"}`} />
            <span><span className="text-ink-800 font-medium">{name}</span> <span className="text-ink-500">· {text}</span></span>
          </li>
        ))}
      </ul>
    </Card>
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
        placeholder="Ask anything — “how much on food this month?”" aria-label="Ask a question" />
      <button className="btn-primary shrink-0" disabled={!q.trim()}>Ask</button>
    </form>
  );
}

function PeriodTotals() {
  const [period, setPeriod] = useState("month");
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get(`/api/transactions/summary?period=${period}`).then((r) => setData(r.data)).catch(() => setData(null));
  }, [period]);
  return (
    <Card title="Totals" action={
      <div className="flex gap-1 bg-sage-100 rounded-lg p-1">
        {[["month", "Month"], ["year", "Year"], ["lifetime", "All time"]].map(([v, l]) => (
          <button key={v} onClick={() => setPeriod(v)} aria-pressed={period === v}
            className={`px-3 py-1 rounded-md text-xs font-medium ${period === v ? "bg-white text-ink-900 shadow-sm" : "text-ink-500"}`}>{l}</button>
        ))}
      </div>
    }>
      {data ? (
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div><p className="text-xs text-ink-400">Spent</p><p className="font-mono font-semibold">{rupees(data.total_spend)}</p></div>
          <div><p className="text-xs text-ink-400">Money in</p><p className="font-mono font-semibold">{rupees(data.total_received)}</p></div>
          <div><p className="text-xs text-ink-400">Net</p><p className="font-mono font-semibold">{rupees(data.net_cash_flow)}</p></div>
        </div>
      ) : <p className="text-sm text-ink-400">Loading…</p>}
    </Card>
  );
}

export default function Dashboard() {
  const thisMonth = monthKey(new Date());
  const [month, setMonth] = useState(thisMonth);
  const [refreshKey, setRefreshKey] = useState(0);
  const [learnedRule, setLearnedRule] = useState(null);
  const current = month === thisMonth;
  const range = current ? "" : `&date_from=${month}-01T00:00:00&date_to=${month}-${lastDay(month)}T23:59:59`;
  const { data: home, error } = useApi(`/api/home?month=${month}`, refreshKey);
  const { data: txnPage } = useApi(`/api/transactions?page=1&page_size=${RECENT}${range}`, refreshKey);
  const txns = txnPage?.items ?? null;
  const refresh = () => setRefreshKey((k) => k + 1);

  const undoRule = async () => {
    const id = learnedRule.rule_id;
    setLearnedRule(null);
    await api.delete(`/api/rules/${id}`);
    refresh();
  };

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <SubscriptionBanner />
      {learnedRule && <RuleToast rule={learnedRule} onUndo={undoRule} onClose={() => setLearnedRule(null)} />}

      <div className="flex items-center justify-between gap-2">
        <h1 className="font-display text-2xl text-ink-900">{current ? "Today" : monthLabel(month)}</h1>
        <div className="flex items-center gap-1" aria-label="Month">
          <button onClick={() => setMonth(shiftMonth(month, -1))} className="btn-ghost px-3 py-1.5" aria-label="Previous month">‹</button>
          <span className="text-sm text-ink-600 min-w-[7.5rem] text-center">{monthLabel(month)}</span>
          <button onClick={() => setMonth(shiftMonth(month, 1))} disabled={current} className="btn-ghost px-3 py-1.5 disabled:opacity-30" aria-label="Next month">›</button>
        </div>
      </div>
      {!current && (
        <button onClick={() => setMonth(thisMonth)} className="text-sm font-medium text-forest-600 hover:underline">← Back to this month</button>
      )}

      {error ? (
        <div className="card p-5 text-center space-y-3">
          <p className="text-sm text-ink-600">{error}</p>
          <button onClick={refresh} className="btn-ghost text-sm">Try again</button>
        </div>
      ) : !home ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3"><SkeletonMetricCard /><SkeletonMetricCard /></div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {current && <SafeToSpend safe={home.safe_to_spend} />}
            <Outlook outlook={home.outlook} current={current} />
          </div>
          {current && <AskBar />}
          {current && <QuickAddBar onAdded={refresh} />}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Budgets budgets={home.budgets} />
            {current ? <Upcoming items={home.upcoming} /> : <PeriodTotals />}
            <Attention attention={home.attention} onAnswered={refresh} />
            <Coverage coverage={home.coverage} cashBalance={home.cash_balance} />
          </div>
        </>
      )}

      <Card title={current ? "Recent transactions" : `Transactions · ${monthLabel(month)}`}>
        {txns === null ? <SkeletonTransactionFeed /> : txns.length ? (
          txns.map((t) => <TransactionRow key={t.id} txn={t} onChanged={refresh} onRuleLearned={setLearnedRule} />)
        ) : (
          <Empty to="/connect" cta="Import a statement">
            {current ? "No transactions yet. Add one above, forward bank alerts, or" : "Nothing recorded this month."}
          </Empty>
        )}
      </Card>
      {current && <PeriodTotals />}
    </div>
  );
}
