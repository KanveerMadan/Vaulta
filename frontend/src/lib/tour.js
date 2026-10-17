import { formatINR } from "./money";

// The guided tour's steps (components/GuidedTour.jsx), written for the user's own numbers.

/** The steps for this user's data (`home`: /api/home; `txnCount`: transactions on the page). */
export function tourSteps(home, txnCount) {
  const safe = home?.safe_to_spend;
  const attention = home?.attention?.review_count ?? 0;
  return [
    {
      id: "safe", title: "Safe to spend today",
      body: safe?.amount != null
        ? `${formatINR(safe.amount)} is what you can spend today and still stay within this month's limit. It updates as you spend.`
        : "Once Vaulta knows your income or a budget, this shows how much you can spend today and still stay within the month.",
    },
    {
      id: "quick-add", title: "Add anything in one line",
      body: "Type something like “150 auto cash” and Vaulta fills in the amount, merchant, category, date and how you paid.",
    },
    {
      id: "attention", title: "Questions that fix your numbers",
      body: attention
        ? `${attention} question${attention === 1 ? "" : "s"} here. Each answer corrects your totals, and Vaulta remembers it for next time.`
        : "When Vaulta isn't sure about a payment, it asks here, one tap per question.",
    },
    {
      id: "recent", title: "Your transactions",
      body: txnCount
        ? "Tap a category to change it. Vaulta learns from two consistent changes, and “Why is it filed here?” explains any of them."
        : "Import a statement or forward a bank alert, and your transactions appear here, already sorted into categories.",
    },
    {
      id: "ask", title: "Ask about your money",
      body: "Ask in your own words, like “how much on food this month?”. Answers come from your own numbers.",
    },
    {
      id: "coverage", title: "Where your numbers come from",
      body: "Statements, forwarded bank alerts, Telegram and cash. The more of these are connected, the more complete your numbers are.",
    },
    {
      id: "help", title: "That's the tour",
      body: "Replay it any time from this button or from Settings.",
    },
  ];
}

