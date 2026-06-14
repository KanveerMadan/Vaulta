import { useState } from "react";
import { useAuthStore } from "../store/authStore";
import CSVUpload from "../components/CSVUpload";
import { useCallback } from "react";

// ─────────────────────────────────────────────
// Data source definitions
// ─────────────────────────────────────────────

function useDataSources(user) {
  return [
    {
      id: "csv",
      label: "Bank Statement CSV",
      description: "Import transactions from any Indian bank instantly. Download your statement as CSV from net banking — no login sharing required.",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
      available: true,
      connected: false,  // CSV is stateless — always show "Import"
      action: "import",
      badge: "Instant",
      badgeColor: "safe",
      supportedBanks: ["HDFC", "ICICI", "SBI", "Axis", "Kotak"],
    },
    {
      id: "gmail",
      label: "Gmail",
      description: "Automatically pull receipts and order confirmations from Swiggy, Zomato, Amazon, Flipkart, IRCTC, and more. Read-only access to transaction emails only — never your personal mail.",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      ),
      available: false,  // Phase 2
      connected: user?.gmail_connected,
      action: "connect",
      badge: "Coming in Phase 2",
      badgeColor: "neutral",
    },
    {
      id: "sms",
      label: "Bank SMS",
      description: "Transaction SMS alerts from your bank, read directly on your phone. Available in the Vaulta mobile app.",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
      ),
      available: false,  // Requires native app (Capacitor, Phase 6)
      connected: user?.sms_connected,
      action: "connect",
      badge: "Mobile app only",
      badgeColor: "neutral",
    },
    {
      id: "aa",
      label: "Account Aggregator",
      description: "RBI's Account Aggregator framework — the most complete picture of your finances, including FDs, mutual funds, and credit cards, with your explicit consent.",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
      available: false,  // Phase 2+
      connected: user?.aa_connected,
      action: "connect",
      badge: "Coming soon",
      badgeColor: "neutral",
    },
  ];
}

// ─────────────────────────────────────────────
// Source card
// ─────────────────────────────────────────────

function SourceCard({ source, onImport }) {
  const isConnected = source.connected;
  const isAvailable = source.available;

  return (
    <div className={`
      card p-5 flex flex-col gap-4 transition-all
      ${!isAvailable ? "opacity-60" : ""}
    `}>
      <div className="flex items-start gap-3">
        <div className={`
          w-10 h-10 rounded-xl flex items-center justify-center shrink-0
          ${isConnected ? "bg-safe/15 text-safe" : isAvailable ? "bg-forest-100 text-forest-600" : "bg-sage-100 text-ink-400"}
        `}>
          {source.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-medium text-ink-900">{source.label}</h3>
            <span className={`
              inline-block text-xs px-2 py-0.5 rounded-full font-medium
              ${source.badgeColor === "safe" ? "bg-safe/15 text-safe" : "bg-sage-100 text-ink-500"}
              ${isConnected ? "!bg-safe/15 !text-safe" : ""}
            `}>
              {isConnected ? "Connected" : source.badge}
            </span>
          </div>
          <p className="text-sm text-ink-500 mt-1 leading-relaxed">{source.description}</p>
          {source.supportedBanks && (
            <p className="text-xs text-ink-400 mt-1.5">
              Supports: {source.supportedBanks.join(", ")}
            </p>
          )}
        </div>
      </div>

      {isAvailable && (
        <button
          onClick={() => onImport?.(source.id)}
          className={isConnected ? "btn-ghost text-sm py-2" : "btn-primary-light text-sm py-2"}
        >
          {isConnected ? "Manage" : source.action === "import" ? "Import statement" : "Connect"}
        </button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Privacy table
// ─────────────────────────────────────────────

const PRIVACY_ROWS = [
  { can: "Read transaction amounts and merchant names", cannot: "Read email body text or personal messages" },
  { can: "Categorize your spending automatically", cannot: "Access your contacts or attachments" },
  { can: "Show you patterns in your spending", cannot: "Share your data with advertisers" },
  { can: "Help you understand where your money goes", cannot: "Sell your data or profit from your behaviour" },
];

function PrivacyTable() {
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-sage-100">
        <h3 className="font-medium text-ink-900">What Vaulta can and cannot see</h3>
      </div>
      <div className="divide-y divide-sage-50">
        {PRIVACY_ROWS.map((row, i) => (
          <div key={i} className="grid grid-cols-2 text-sm">
            <div className="flex items-start gap-2 px-5 py-3 bg-safe/5">
              <svg className="w-4 h-4 text-safe mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span className="text-ink-700">{row.can}</span>
            </div>
            <div className="flex items-start gap-2 px-5 py-3">
              <svg className="w-4 h-4 text-danger mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span className="text-ink-500">{row.cannot}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Main Connect page
// ─────────────────────────────────────────────

export default function Connect() {
  const { user } = useAuthStore();
  const [showCSVUpload, setShowCSVUpload] = useState(false);

  const sources = useDataSources(user);

  const handleSourceAction = (sourceId) => {
    if (sourceId === "csv") {
      setShowCSVUpload(true);
    }
    // Gmail OAuth: Phase 2 — will navigate to /api/gmail/auth
  };

  const handleCSVSuccess = useCallback(() => {
    // Dashboard re-fetches summary/transactions on mount,
    // so no action needed here — just close the modal.
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

      {/* Page header */}
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900">Connect your accounts</h1>
        <p className="text-ink-500 mt-1 text-sm">
          The more sources you connect, the more complete your picture. Start with a CSV — it takes 30 seconds.
        </p>
      </div>

      {/* Trust signal */}
      <div className="flex items-center gap-3 bg-forest-50 border border-forest-200 rounded-xl px-4 py-3">
        <svg className="w-4 h-4 text-forest-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <p className="text-sm text-forest-800">
          Vaulta's revenue is your subscription — not your data.{" "}
          <a
            href="https://github.com/vaulta-finance"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium underline underline-offset-2"
          >
            The code is publicly auditable.
          </a>
        </p>
      </div>

      {/* Source cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {sources.map((source) => (
          <SourceCard
            key={source.id}
            source={source}
            onImport={handleSourceAction}
          />
        ))}
      </div>

      {/* Privacy table */}
      <PrivacyTable />

      {/* CSV Upload modal */}
      {showCSVUpload && (
        <CSVUpload
          onSuccess={handleCSVSuccess}
          onClose={() => setShowCSVUpload(false)}
        />
      )}
    </div>
  );
}