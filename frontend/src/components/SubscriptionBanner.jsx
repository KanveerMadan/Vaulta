import { useEffect, useState, useCallback } from "react";
import api from "../lib/api";

// ─────────────────────────────────────────────
// Razorpay Checkout loader
// ─────────────────────────────────────────────

function loadRazorpayScript() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = resolve;
    script.onerror = () => reject(new Error("Failed to load Razorpay checkout"));
    document.body.appendChild(script);
  });
}

function timeRemaining(isoString) {
  if (!isoString) return null;
  const diffMs = new Date(isoString).getTime() - Date.now();
  if (diffMs <= 0) return "expired";
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);
  if (days >= 1) return `${days} day${days === 1 ? "" : "s"}`;
  return `${hours} hour${hours === 1 ? "" : "s"}`;
}

// ─────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────

export default function SubscriptionBanner() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(false);
  const [error, setError] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await api.get("/api/payments/status");
      setStatus(data);
    } catch (err) {
      // 503 = payments not configured yet — treat as no banner, not an error
      if (err?.response?.status !== 503) {
        setError("Couldn't load subscription status.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleSubscribe = async () => {
    setSubscribing(true);
    setError(null);
    try {
      const { data } = await api.post("/api/payments/create-subscription");
      await loadRazorpayScript();

      const options = {
        key: data.razorpay_key_id,
        subscription_id: data.subscription_id,
        name: "Vaulta",
        description: "Vaulta Monthly — ₹99/month",
        theme: { color: "#2d6a4f" },
        handler: function () {
          // Webhook updates subscription_status asynchronously;
          // poll once after a short delay to reflect the change
          setTimeout(fetchStatus, 2000);
        },
        modal: {
          ondismiss: function () {
            setSubscribing(false);
          },
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      const msg = err?.response?.data?.detail || "Couldn't start checkout. Please try again.";
      setError(msg);
      setSubscribing(false);
    }
  };

  if (loading || !status) return null;

  // Active subscription — no banner needed
  if (status.subscription_status === "active") return null;

  // Trial — informational, not urgent
  if (status.subscription_status === "trial") {
    return (
      <div className="flex items-center justify-between gap-3 bg-forest-50 border border-forest-200 rounded-xl px-4 py-3">
        <div className="flex items-center gap-3">
          <svg className="w-4 h-4 text-forest-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-forest-800">
            You're on the free tier — last 30 days of data only.
          </p>
        </div>
        <button
          onClick={handleSubscribe}
          disabled={subscribing}
          className="btn-primary text-sm py-1.5 px-4 shrink-0 disabled:opacity-50"
        >
          {subscribing ? "Loading..." : "Subscribe — ₹99/mo"}
        </button>
      </div>
    );
  }

  // Past due — grace period warning
  if (status.subscription_status === "past_due") {
    const remaining = timeRemaining(status.grace_period_ends_at);
    const expired = remaining === "expired";
    return (
      <div className={`
        flex items-center justify-between gap-3 rounded-xl px-4 py-3 border
        ${expired ? "bg-danger/5 border-danger/20" : "bg-gold/10 border-gold/30"}
      `}>
        <div className="flex items-center gap-3">
          <svg className={`w-4 h-4 shrink-0 ${expired ? "text-danger" : "text-gold"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          </svg>
          <p className={`text-sm ${expired ? "text-danger" : "text-ink-700"}`}>
            {expired
              ? "Your payment is overdue. Update your payment method to continue using Vaulta."
              : `Payment failed — you have ${remaining} left before access is restricted.`}
          </p>
        </div>
        <button
          onClick={handleSubscribe}
          disabled={subscribing}
          className="btn-primary text-sm py-1.5 px-4 shrink-0 disabled:opacity-50"
        >
          {subscribing ? "Loading..." : "Update payment"}
        </button>
      </div>
    );
  }

  // Cancelled
  if (status.subscription_status === "cancelled") {
    return (
      <div className="flex items-center justify-between gap-3 bg-danger/5 border border-danger/20 rounded-xl px-4 py-3">
        <div className="flex items-center gap-3">
          <svg className="w-4 h-4 text-danger shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
          <p className="text-sm text-danger">
            Your subscription was cancelled. Subscribe again to continue using Vaulta.
          </p>
        </div>
        <button
          onClick={handleSubscribe}
          disabled={subscribing}
          className="btn-primary text-sm py-1.5 px-4 shrink-0 disabled:opacity-50"
        >
          {subscribing ? "Loading..." : "Resubscribe — ₹99/mo"}
        </button>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 bg-danger/5 border border-danger/20 rounded-xl px-4 py-3">
        <p className="text-sm text-danger">{error}</p>
      </div>
    );
  }

  return null;
}