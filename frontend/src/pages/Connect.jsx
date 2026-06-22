import { useState } from "react";
import { useAuthStore } from "../store/authStore";
import StatementUpload from "../components/StatementUpload";

// ─────────────────────────────────────────────
// Data source definitions
// ─────────────────────────────────────────────
// Gmail and Account Aggregator were evaluated and REJECTED — not deferred:
//   - Gmail requires Google's restricted-scope OAuth verification to serve
//     more than 100 manually-added test users, plus a recurring paid annual
//     security audit. Incompatible with a fully-public product.
//   - Account Aggregator requires the integrating entity to already hold a
//     financial-service regulatory license (SEBI/RBI/IRDAI). Vaulta does not
//     have one and is not pursuing one.
// CSV/PDF statement upload (any bank, any UPI app, auto-detected) is the
// permanent, primary, fully public data path going forward.

function useDataSources(user) {
  return [
    {
      id: "statement",
      label: "Bank or UPI Statement",
      description: "Upload a statement from your bank's net banking portal, or from Google Pay, PhonePe, or Paytm. We detect the source automatically — no need to tell us which.",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
      available: true,
      action: "import",
      badge: "Instant",
      badgeColor: "safe",
      supportedFormats: "CSV or PDF",
      supportedSources: ["HDFC", "ICICI", "SBI", "Axis", "Kotak", "Google Pay"],
    },
    {
      id: "manual",
      label: "Manual Entry",
      description: "Log cash spending or anything that doesn't show up in a statement — a quick add, no file needed.",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 4v16m8-8H4" />
        </svg>
      ),
      available: false,  // Not yet built
      action: "add",
      badge: "Coming soon",
      badgeColor: "neutral",
    },
  ];
}

// ─────────────────────────────────────────────
// Source card
// ─────────────────────────────────────────────

function SourceCard({ source, onAction }) {
  const isAvailable = source.available;

  return (
    <div className={`
      card p-5 flex flex-col gap-4 transition-all
      ${!isAvailable ? "opacity-60" : ""}
    `}>
      <div className="flex items-start gap-3">
        <div className={`
          w-10 h-10 rounded-xl flex items-center justify-center shrink-0
          ${isAvailable ? "bg-forest-100 text-forest-600" : "bg-sage-100 text-ink-400"}
        `}>
          {source.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-medium text-ink-900">{source.label}</h3>
            <span className={`
              inline-block text-xs px-2 py-0.5 rounded-full font-medium
              ${source.badgeColor === "safe" ? "bg-safe/15 text-safe" : "bg-sage-100 text-ink-500"}
            `}>
              {source.badge}
            </span>
          </div>
          <p className="text-sm text-ink-500 mt-1 leading-relaxed">{source.description}</p>
          {source.supportedSources && (
            <p className="text-xs text-ink-400 mt-1.5">
              Supports: {source.supportedSources.join(", ")} ({source.supportedFormats})
            </p>
          )}
        </div>
      </div>

      {isAvailable && (
        <button onClick={() => onAction?.(source.id)} className="btn-primary-light text-sm py-2">
          {source.action === "import" ? "Upload statement" : "Add manually"}
        </button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Privacy table
// ─────────────────────────────────────────────

const PRIVACY_ROWS = [
  { can: "Read transaction amounts and merchant names", cannot: "Access your bank login or UPI PIN" },
  { can: "Categorize your spending automatically", cannot: "Share your data with advertisers" },
  { can: "Show you patterns in your spending", cannot: "Sell your data or profit from your behaviour" },
  { can: "Process the file you upload, then discard it", cannot: "Read anything you don't explicitly upload" },
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
  const [showUpload, setShowUpload] = useState(false);

  const sources = useDataSources(user);

  const handleSourceAction = (sourceId) => {
    if (sourceId === "statement") {
      setShowUpload(true);
    }
    // "manual" and "aa" are not yet available — no action wired
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

      {/* Page header */}
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900">Connect your accounts</h1>
        <p className="text-ink-500 mt-1 text-sm">
          Upload a bank or UPI statement to get started — it takes 30 seconds, and we detect the source automatically.
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
          <SourceCard key={source.id} source={source} onAction={handleSourceAction} />
        ))}
      </div>

      {/* Privacy table */}
      <PrivacyTable />

      {/* Statement upload modal */}
      {showUpload && (
        <StatementUpload onClose={() => setShowUpload(false)} />
      )}
    </div>
  );
}