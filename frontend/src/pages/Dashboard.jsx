import { useEffect, useCallback, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { useFinanceStore } from "../store/financeStore";
import { useAuthStore } from "../store/authStore";
import api from "../lib/api";
import {
  SkeletonMetricCard,
  SkeletonChart,
  SkeletonTransactionFeed,
  SkeletonInsightCard,
} from "../components/Skeletons";
import SubscriptionBanner from "../components/SubscriptionBanner";
import QuickAddBar from "../components/QuickAddBar";
import SplitModal from "../components/SplitModal";
import ReviewQueue from "../components/ReviewQueue";
import { rupees } from "../lib/format";
import { CATEGORIES, KINDS, kindsFor } from "../lib/categories";
import { updateTransaction, deleteTransaction } from "../lib/transactions";

const CATEGORY_COLORS = [
  "#2d6a4f", "#40916c", "#52b788", "#74c69d", "#95d5b2",
  "#b7e4c7", "#d8f3dc", "#1b4332", "#081c15",
];

const PERIOD_OPTIONS = [
  { value: "month",    label: "Month"    },
  { value: "year",     label: "Year"     },
  { value: "lifetime", label: "All Time" },
];

// ─────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────

function MetricCard({ label, value, sub, progress, progressDanger, highlight }) {
  return (
    <div className={`card p-5 space-y-2 ${highlight ? "ring-1 ring-forest-300" : ""}`}>
      <p className="text-xs font-medium text-ink-400 uppercase tracking-widest">{label}</p>
      <p className="font-mono text-2xl font-semibold text-ink-900">{value}</p>
      {progress !== undefined && (
        <div className="h-1.5 bg-sage-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              progressDanger ? "bg-danger" : "bg-forest-500"
            }`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      )}
      {sub && <p className="text-xs text-ink-400">{sub}</p>}
    </div>
  );
}

function InsightCard({ insight }) {
  return (
    <div className="card p-5 space-y-2">
      <p className="tag-positive inline-block text-xs">Insight</p>
      <p className="text-sm text-ink-700 leading-relaxed">{insight.text}</p>
      <p className="text-xs text-ink-400">{insight.sub}</p>
    </div>
  );
}

function RuleToast({ rule, onUndo, onClose }) {
  const what = rule.field === "kind" ? (KINDS[rule.value]?.label ?? rule.value) : rule.value;
  return (
    <div role="status" className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-ink-900 text-white text-sm rounded-xl shadow-lg px-4 py-3 flex items-center gap-3 max-w-[calc(100vw-2rem)]">
      <span>
        {rule.applied_count > 0
          ? `Applied ${what} to ${rule.applied_count} other ${rule.merchant} transaction${rule.applied_count === 1 ? "" : "s"}.`
          : `${rule.merchant} will be ${what} from now on.`}
      </span>
      <button onClick={onUndo} className="font-semibold underline">Undo</button>
      <button onClick={onClose} aria-label="Dismiss" className="text-white/60">✕</button>
    </div>
  );
}

function TransactionRow({ txn, onChanged, onRuleLearned }) {
  const isCredit = txn.direction === "credit";
  const counted = txn.kind === "spend" || txn.kind === "income" || txn.kind === "refund";
  const [editing, setEditing] = useState(false);
  const [editingKind, setEditingKind] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setEditing(false);
      setEditingKind(false);
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.detail || "Couldn't save that change.");
    } finally {
      setBusy(false);
    }
  };

  const update = async (changes) => {
    const res = await updateTransaction(txn.id, changes);
    if (res.rule_applied) onRuleLearned?.(res.rule_applied);
  };
  const setCategory = (category) => act(() => update({ category: category || null }));
  const setKind = (kind) => act(() => update({ kind }));
  const unsplit = () => act(() => api.delete(`/api/transactions/${txn.id}/split`));
  const remove = () => {
    if (window.confirm(`Delete ${txn.merchant_clean || txn.merchant_raw}, ₹${txn.amount}?`)) act(() => deleteTransaction(txn.id));
  };

  return (
    <div className="py-2.5 border-b border-sage-50 last:border-0">
    <div className="flex items-center gap-3">
      <div className="w-9 h-9 rounded-full bg-sage-100 flex items-center justify-center text-ink-500 text-sm shrink-0">
        {(txn.merchant_clean || txn.merchant_raw || "?")[0].toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-ink-900 truncate">
          {txn.merchant_clean || txn.merchant_raw}
        </p>
        <div className="text-xs text-ink-400 flex items-center gap-1">
          {editing ? (
            <select
              autoFocus
              disabled={busy}
              defaultValue={txn.category || ""}
              onChange={(e) => setCategory(e.target.value)}
              onBlur={() => !busy && setEditing(false)}
              className="border border-sage-200 rounded px-1 py-0.5 text-xs bg-white text-ink-700"
              aria-label="Category"
            >
              <option value="">Uncategorized</option>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          ) : (
            <button onClick={() => setEditing(true)} className="hover:text-forest-600 hover:underline" title="Change category">
              {txn.category || "Uncategorized"}
            </button>
          )}
          <span>·</span>
          {editingKind ? (
            <select
              autoFocus
              disabled={busy}
              defaultValue={txn.kind}
              onChange={(e) => setKind(e.target.value)}
              onBlur={() => !busy && setEditingKind(false)}
              className="border border-sage-200 rounded px-1 py-0.5 text-xs bg-white text-ink-700"
              aria-label="Kind"
            >
              {kindsFor(txn.direction).map(([value, k]) => <option key={value} value={value}>{k.label}</option>)}
            </select>
          ) : (
            <button onClick={() => setEditingKind(true)} title="Change what this transaction is"
              className={`hover:text-forest-600 hover:underline ${counted ? "" : "text-gold"}`}>
              {KINDS[txn.kind]?.label ?? txn.kind}
            </button>
          )}
          <span>·</span>
          <span>
            {new Date(txn.transaction_date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
          </span>
          {txn.source === "manual" && <span className="text-ink-300">· added by you</span>}
        </div>
        {error && <p className="text-xs text-danger mt-0.5">{error}</p>}
      </div>
      <p className={`font-mono text-sm font-medium shrink-0 ${
        !counted ? "text-ink-400" : isCredit ? "text-safe" : "text-ink-800"
      }`}>
        {txn.kind === "transfer" ? "↔" : isCredit ? "+" : "-"}
        ₹{Math.abs(txn.amount).toLocaleString("en-IN")}
      </p>
      {(txn.kind === "spend" || txn.kind === "income") && !txn.is_split && (
        <button onClick={() => setSplitting(true)} disabled={busy} className="text-xs text-ink-300 hover:text-forest-600 shrink-0">Split</button>
      )}
      {txn.source === "manual" && (
        <button onClick={remove} disabled={busy} className="p-1 text-ink-300 hover:text-danger shrink-0" aria-label="Delete transaction">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
    {txn.is_split && (
      <div className="ml-12 mt-1.5 space-y-0.5 text-xs text-ink-500">
        {txn.splits.map((part) => (
          <div key={part.id} className="flex justify-between">
            <span>↳ {part.category || "Uncategorized"}</span>
            <span className="font-mono">{rupees(part.amount)}</span>
          </div>
        ))}
        <button onClick={unsplit} disabled={busy} className="text-ink-400 hover:text-danger">Unsplit</button>
      </div>
    )}
    {splitting && <SplitModal txn={txn} onClose={() => setSplitting(false)} onSaved={onChanged} />}
    </div>
  );
}

function ErrorRetry({ message, onRetry }) {
  return (
    <div className="card p-5 flex flex-col items-center gap-3 text-center">
      <div className="w-10 h-10 rounded-full bg-danger/10 flex items-center justify-center">
        <svg className="w-5 h-5 text-danger" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p className="text-sm text-ink-600">{message}</p>
      <button onClick={onRetry} className="btn-ghost text-sm py-1.5 px-4">
        Try again
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────
// Main Dashboard
// ─────────────────────────────────────────────

export default function Dashboard() {
  const { user } = useAuthStore();
  const [period, setPeriod] = useState("month");

  const {
    summary, summaryLoading, summaryError,
    setSummary, setSummaryLoading, setSummaryError,
    transactions, transactionsLoading, transactionsError,
    setTransactions, setTransactionsLoading, setTransactionsError,
    categorySpend, setCategorySpend,
  } = useFinanceStore();

  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const { data } = await api.get(`/api/transactions/summary?period=${period}`);
      setSummary(data);
      setCategorySpend(
        (data.categories || []).map((c, i) => ({
          name: c.category,
          value: parseFloat(c.total),
          color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
          budget: c.budget_limit ? parseFloat(c.budget_limit) : null,
          pct: parseFloat(c.percentage_of_spend),
        }))
      );
    } catch (err) {
      setSummaryError(
        err?.response?.status === 404
          ? "No transaction data yet. Upload a bank statement to get started."
          : "Couldn't load your summary. Check your connection and try again."
      );
    } finally {
      setSummaryLoading(false);
    }
  }, [period, setSummary, setSummaryLoading, setSummaryError, setCategorySpend]);

  const fetchTransactions = useCallback(async () => {
    setTransactionsLoading(true);
    try {
      const { data } = await api.get("/api/transactions?page=1&page_size=20");
      setTransactions(data.items, data.total);
    } catch (err) {
      setTransactionsError("Couldn't load transactions. Try again in a moment.");
    } finally {
      setTransactionsLoading(false);
    }
  }, [setTransactions, setTransactionsLoading, setTransactionsError]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const refresh = () => {
    fetchSummary();
    fetchTransactions();
  };
  const [learnedRule, setLearnedRule] = useState(null);
  const undoRule = async () => {
    const id = learnedRule.rule_id;
    setLearnedRule(null);
    await api.delete(`/api/rules/${id}`);
    refresh();
  };

  // ── Derived values ─────────────────────────────────────────────────────────
  const totalSpend        = summary ? parseFloat(summary.total_spend)       : 0;
  const totalReceived     = summary ? parseFloat(summary.total_received)    : 0;
  const netCashFlow       = summary ? parseFloat(summary.net_cash_flow)     : 0;
  const totalBudget       = summary?.total_budget ? parseFloat(summary.total_budget) : null;
  const budgetPct         = totalBudget ? (totalSpend / totalBudget) * 100 : null;
  const daysRemaining     = summary?.days_remaining ?? null;
  const avgMonthlySpend   = summary?.avg_monthly_spend ? parseFloat(summary.avg_monthly_spend) : null;
  const momDelta          = summary?.mom_total_delta ? parseFloat(summary.mom_total_delta) : null;
  const momPct            = summary?.mom_total_delta_pct ? parseFloat(summary.mom_total_delta_pct) : null;
  const netPositive       = netCashFlow >= 0;
  const isMonth           = period === "month";

  const periodLabel = isMonth
    ? new Date().toLocaleString("en-IN", { month: "long", year: "numeric" })
    : period === "year"
    ? new Date().getFullYear().toString()
    : "All Time";

  const insights = summary?.categories?.length
    ? [
        summary.categories[0] && {
          text: `${summary.categories[0].category} is your biggest spend category at ₹${parseFloat(summary.categories[0].total).toLocaleString("en-IN")}.`,
          sub: `${summary.categories[0].transaction_count} transactions`,
        },
        isMonth && momDelta !== null && {
          text: momDelta > 0
            ? `You've spent ₹${Math.abs(momDelta).toLocaleString("en-IN")} more than last month (${Math.abs(momPct ?? 0).toFixed(1)}% up).`
            : `You've spent ₹${Math.abs(momDelta).toLocaleString("en-IN")} less than last month. Good going.`,
          sub: "Month-over-month",
        },
        totalReceived > 0 && {
          text: `₹${totalReceived.toLocaleString("en-IN")} received across payments and income.`,
          sub: "Money in",
        },
      ].filter(Boolean)
    : [];

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">

      <SubscriptionBanner />
      {learnedRule && <RuleToast rule={learnedRule} onUndo={undoRule} onClose={() => setLearnedRule(null)} />}

      <QuickAddBar onAdded={refresh} />

      <ReviewQueue onAnswered={refresh} />

      {summary && summary.transaction_count > 0 && (
        <div className="flex items-center gap-3 bg-gold/10 border border-gold/30 rounded-xl px-4 py-3">
          <svg className="w-4 h-4 text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-ink-700">
            Upload your UPI app statement alongside your bank CSV for a complete picture.{" "}
            <a href="/connect" className="font-medium text-forest-600 hover:underline">
              Add another source →
            </a>
          </p>
        </div>
      )}

      {/* Period toggle + section header */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">
            {periodLabel}
          </h2>
          <div className="flex gap-1 bg-sage-100 rounded-lg p-1">
            {PERIOD_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setPeriod(value)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  period === value
                    ? "bg-white text-ink-900 shadow-sm"
                    : "text-ink-500 hover:text-ink-700"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Metric cards */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {summaryLoading ? (
            <>
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
            </>
          ) : summaryError ? (
            <div className="col-span-2 lg:col-span-3">
              <ErrorRetry message={summaryError} onRetry={fetchSummary} />
            </div>
          ) : summary ? (
            <>
              {/* Row 1 — money flow */}
              <MetricCard
                label="Total spent"
                value={`₹${totalSpend.toLocaleString("en-IN")}`}
                sub={isMonth && momDelta !== null
                  ? `${momDelta > 0 ? "▲" : "▼"} ${Math.abs(momPct ?? 0).toFixed(1)}% vs last month`
                  : "Merchant spend + payments to people"
                }
              />
              <MetricCard
                label="Money in"
                value={`₹${totalReceived.toLocaleString("en-IN")}`}
                sub="Income + payments received"
              />
              <MetricCard
                label="Net cash flow"
                value={`${netPositive ? "+" : "−"}₹${Math.abs(netCashFlow).toLocaleString("en-IN")}`}
                sub={netPositive ? "You're ahead" : "Spending exceeded income"}
                highlight={netPositive}
              />

              {/* Row 2 — budget / avg / activity */}
              <MetricCard
                label="Budget used"
                value={isMonth && totalBudget ? `${budgetPct?.toFixed(0)}%` : "—"}
                progress={isMonth ? (budgetPct ?? undefined) : undefined}
                progressDanger={isMonth && budgetPct !== null && budgetPct > 80}
                sub={isMonth
                  ? (totalBudget
                      ? `₹${(totalBudget - totalSpend).toLocaleString("en-IN")} remaining`
                      : "No budget set")
                  : "Budget tracking is monthly only"
                }
              />
              <MetricCard
                label="Transactions"
                value={summary.transaction_count.toLocaleString("en-IN")}
                sub={isMonth ? "This month" : period === "year" ? "This year" : "All time"}
              />
              <MetricCard
                label={isMonth ? "Days left" : "Avg monthly spend"}
                value={
                  isMonth
                    ? (daysRemaining ?? "—")
                    : avgMonthlySpend !== null
                    ? `₹${avgMonthlySpend.toLocaleString("en-IN")}`
                    : "—"
                }
                sub={isMonth ? "In this billing period" : "Based on available data"}
              />
            </>
          ) : (
            <div className="col-span-2 lg:col-span-3 card p-6 text-center">
              <p className="text-ink-400 text-sm">No data yet.</p>
              <a href="/connect" className="text-forest-600 text-sm font-medium hover:underline mt-1 inline-block">
                Upload a bank statement to get started →
              </a>
            </div>
          )}
        </div>
      </section>

      {/* Spend chart + Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2">
          {summaryLoading ? (
            <SkeletonChart />
          ) : summaryError ? (
            <ErrorRetry message="Chart unavailable" onRetry={fetchSummary} />
          ) : categorySpend.length > 0 ? (
            <div className="card p-5">
              <p className="text-xs font-semibold text-ink-400 uppercase tracking-widest mb-4">
                Spending by category
              </p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={categorySpend} margin={{ left: 0, right: 0, top: 0, bottom: 0 }}>
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10, fill: "#6b7280" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: "#6b7280" }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    formatter={(v) => [`₹${parseFloat(v).toLocaleString("en-IN")}`, "Spent"]}
                    contentStyle={{
                      background: "#fff",
                      border: "1px solid #e5e7eb",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {categorySpend.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="card p-5 flex items-center justify-center h-full min-h-[220px]">
              <p className="text-ink-400 text-sm">No category data yet.</p>
            </div>
          )}
        </div>

        <div className="space-y-3">
          {summaryLoading ? (
            <>
              <SkeletonInsightCard />
              <SkeletonInsightCard />
            </>
          ) : insights.length > 0 ? (
            insights.map((insight, i) => <InsightCard key={i} insight={insight} />)
          ) : (
            <div className="card p-5 text-center">
              <p className="text-ink-400 text-sm">Insights appear once your transactions are loaded.</p>
            </div>
          )}
        </div>
      </div>

      {/* Recent transactions */}
      <section>
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest mb-3">
          Recent transactions
        </h2>
        {transactionsLoading ? (
          <SkeletonTransactionFeed />
        ) : transactionsError ? (
          <ErrorRetry message={transactionsError} onRetry={fetchTransactions} />
        ) : transactions.length > 0 ? (
          <div className="card p-5">
            {transactions.map((txn) => (
              <TransactionRow key={txn.id} txn={txn} onChanged={refresh} onRuleLearned={setLearnedRule} />
            ))}
            {transactions.length >= 20 && (
              <button className="w-full mt-3 text-sm text-forest-600 font-medium hover:underline py-2">
                View all transactions →
              </button>
            )}
          </div>
        ) : (
          <div className="card p-6 text-center">
            <p className="text-ink-400 text-sm">No transactions yet.</p>
            <a href="/connect" className="text-forest-600 text-sm font-medium hover:underline mt-1 inline-block">
              Upload a bank statement to see them here →
            </a>
          </div>
        )}
      </section>
    </div>
  );
}