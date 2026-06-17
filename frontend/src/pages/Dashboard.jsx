import { useEffect, useCallback } from "react";
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

// ─────────────────────────────────────────────
// Category colour palette (matches SpendChart)
// ─────────────────────────────────────────────
const CATEGORY_COLORS = [
  "#2d6a4f", "#40916c", "#52b788", "#74c69d", "#95d5b2",
  "#b7e4c7", "#d8f3dc", "#1b4332", "#081c15",
];

// ─────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────

function MetricCard({ label, value, sub, progress, progressDanger }) {
  return (
    <div className="card p-5 space-y-2">
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

function TransactionRow({ txn }) {
  const sign = txn.amount >= 0 ? "-" : "+";
  const isCredit = txn.amount < 0;
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-sage-50 last:border-0">
      <div className="w-9 h-9 rounded-full bg-sage-100 flex items-center justify-center text-ink-500 text-sm shrink-0">
        {(txn.merchant_clean || txn.merchant_raw || "?")[0].toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-ink-900 truncate">
          {txn.merchant_clean || txn.merchant_raw}
        </p>
        <p className="text-xs text-ink-400">
          {txn.category || "Uncategorized"} ·{" "}
          {new Date(txn.transaction_date).toLocaleDateString("en-IN", {
            day: "numeric", month: "short",
          })}
        </p>
      </div>
      <p className={`font-mono text-sm font-medium shrink-0 ${isCredit ? "text-safe" : "text-ink-800"}`}>
        {isCredit ? "+" : "-"}₹{Math.abs(txn.amount).toLocaleString("en-IN")}
      </p>
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
  const {
    summary, summaryLoading, summaryError,
    setSummary, setSummaryLoading, setSummaryError,
    transactions, transactionsLoading, transactionsError,
    setTransactions, setTransactionsLoading, setTransactionsError,
    categorySpend, setCategorySpend,
  } = useFinanceStore();

  const hasDataSource =
    user?.gmail_connected || user?.sms_connected || user?.aa_connected;

  // ── Fetch summary ──────────────────────────────────────────────────────────
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const { data } = await api.get("/api/transactions/summary");
      setSummary(data);
      // Derive categorySpend for SpendChart
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
  }, [setSummary, setSummaryLoading, setSummaryError, setCategorySpend]);

  // ── Fetch transactions ─────────────────────────────────────────────────────
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
    fetchTransactions();
  }, [fetchSummary, fetchTransactions]);

  // ── Derived values ─────────────────────────────────────────────────────────
  const totalSpend = summary ? parseFloat(summary.total_spend) : 0;
  const totalBudget = summary?.total_budget ? parseFloat(summary.total_budget) : null;
  const budgetPct = totalBudget ? (totalSpend / totalBudget) * 100 : null;
  const daysRemaining = summary?.days_remaining ?? null;
  const momDelta = summary?.mom_total_delta ? parseFloat(summary.mom_total_delta) : null;
  const momPct = summary?.mom_total_delta_pct ? parseFloat(summary.mom_total_delta_pct) : null;

  // Synthetic insights from summary data (Phase 3 will replace with real AI)
  const insights = summary?.categories?.length
    ? [
        summary.categories[0] && {
          text: `${summary.categories[0].category} is your biggest spend category this month at ₹${parseFloat(summary.categories[0].total).toLocaleString("en-IN")}.`,
          sub: `${summary.categories[0].transaction_count} transactions`,
        },
        momDelta !== null && {
          text: momDelta > 0
            ? `You've spent ₹${Math.abs(momDelta).toLocaleString("en-IN")} more than last month (${Math.abs(momPct ?? 0).toFixed(1)}% up).`
            : `You've spent ₹${Math.abs(momDelta).toLocaleString("en-IN")} less than last month. Good going.`,
          sub: "Month-over-month",
        },
      ].filter(Boolean)
    : [];

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">

      {/* Subscription status — trial/past_due/cancelled banners */}
      <SubscriptionBanner />

      {/* Demo banner — only shown when no data source connected */}
      {!hasDataSource && (
        <div className="flex items-center gap-3 bg-gold/10 border border-gold/30 rounded-xl px-4 py-3">
          <svg className="w-4 h-4 text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-ink-700">
            You're looking at real data from your uploaded statements.{" "}
            <a href="/connect" className="font-medium text-forest-600 hover:underline">
              Connect more sources
            </a>{" "}
            for a complete picture.
          </p>
        </div>
      )}

      {/* Metric cards */}
      <section>
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest mb-3">
          {new Date().toLocaleString("en-IN", { month: "long", year: "numeric" })}
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {summaryLoading ? (
            <>
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
            </>
          ) : summaryError ? (
            <div className="col-span-2 lg:col-span-4">
              <ErrorRetry message={summaryError} onRetry={fetchSummary} />
            </div>
          ) : summary ? (
            <>
              <MetricCard
                label="Total spent"
                value={`₹${totalSpend.toLocaleString("en-IN")}`}
                sub={momDelta !== null
                  ? `${momDelta > 0 ? "▲" : "▼"} ${Math.abs(momPct ?? 0).toFixed(1)}% vs last month`
                  : undefined
                }
              />
              <MetricCard
                label="Budget used"
                value={totalBudget
                  ? `${budgetPct?.toFixed(0)}%`
                  : "—"
                }
                progress={budgetPct ?? undefined}
                progressDanger={budgetPct !== null && budgetPct > 80}
                sub={totalBudget
                  ? `₹${(totalBudget - totalSpend).toLocaleString("en-IN")} remaining`
                  : "No budget set"
                }
              />
              <MetricCard
                label="Transactions"
                value={summary.transaction_count.toLocaleString("en-IN")}
                sub={`This month`}
              />
              <MetricCard
                label="Days left"
                value={daysRemaining ?? "—"}
                sub="In this billing period"
              />
            </>
          ) : (
            <div className="col-span-2 lg:col-span-4 card p-6 text-center">
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

        {/* Insights */}
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
              <TransactionRow key={txn.id} txn={txn} />
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