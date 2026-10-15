import { useState } from "react";
import api from "../lib/api";
import { useApi } from "../lib/format";

function ago(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function Copy({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* clipboard blocked */ }
  };
  return <button onClick={copy} className="text-xs px-2 py-1 rounded bg-forest-50 text-forest-700 shrink-0">{done ? "Copied" : label}</button>;
}

/** Bank alert forwarding: address, Gmail setup, and what has arrived. */
export default function InboundCard({ banks = null }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/inbound", refreshKey);
  const [showBanks, setShowBanks] = useState(false);
  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;
  if (!data.address) return null;   // server not set up for inbound email

  const regenerate = async () => {
    if (!window.confirm("Get a new address? The current one stops working, so update your Gmail filter afterwards.")) return;
    await api.post("/api/inbound/regenerate");
    setRefreshKey((k) => k + 1);
  };
  const dismiss = async () => { await api.post("/api/inbound/gmail-confirmation/dismiss"); setRefreshKey((k) => k + 1); };
  // onboarding passes the banks the user picked; the filter then covers only those
  const chosen = banks?.length ? data.banks.filter((b) => banks.includes(b.key)) : data.banks;
  const filter = `from:(${chosen.flatMap((b) => b.senders).join(" OR ")})`;

  return (
    <section className="card p-5 space-y-4">
      <div>
        <h3 className="font-medium text-ink-900">Bank alerts by email</h3>
        <p className="text-sm text-ink-500 mt-1">
          Forward your bank's transaction alert emails here and they're added automatically. Only alerts from known bank
          senders that pass email authentication are read; the email itself is never stored.
        </p>
      </div>

      <div className="flex items-center gap-2 bg-sage-50 rounded-lg px-3 py-2">
        <code className="text-sm text-ink-900 flex-1 truncate">{data.address}</code>
        <Copy text={data.address} />
      </div>

      {data.gmail_confirmation && (
        <div className="bg-gold/10 border border-gold/30 rounded-xl px-4 py-3 text-sm space-y-2">
          <p className="font-medium text-ink-900">Gmail is asking you to confirm forwarding</p>
          {data.gmail_confirmation.link && (
            <a href={data.gmail_confirmation.link} target="_blank" rel="noopener noreferrer"
              className="inline-block btn-primary text-sm py-1.5 px-3">Click to confirm Gmail forwarding</a>
          )}
          {data.gmail_confirmation.code && <p className="text-ink-700">Or enter code <code>{data.gmail_confirmation.code}</code> in Gmail settings.</p>}
          <button onClick={dismiss} className="text-xs text-ink-500">Done, hide this</button>
        </div>
      )}

      {data.total === 0 ? (
        <p className="text-sm text-ink-500">Waiting for your first alert…</p>
      ) : (
        <p className="text-sm text-safe">✓ Last alert received {ago(data.last_received_at)} · {data.this_week} this week</p>
      )}
      {data.sources.length > 0 && (
        <ul className="text-xs text-ink-500 space-y-0.5">
          {data.sources.map((s) => <li key={s.bank}>{s.bank}: {s.count} alert{s.count === 1 ? "" : "s"}</li>)}
        </ul>
      )}
      {data.unreadable.map((u) => (
        <p key={u.bank} className="text-xs text-gold">
          {u.count} alert{u.count === 1 ? "" : "s"} from {u.bank} we couldn't read. Nothing from {u.count === 1 ? "it" : "them"} was saved.
        </p>
      ))}

      <details className="text-sm" open={data.total === 0}>
        <summary className="cursor-pointer text-forest-600 font-medium">Set up forwarding in Gmail</summary>
        <ol className="list-decimal pl-5 mt-2 space-y-1 text-ink-700">
          <li>Gmail → Settings → Forwarding and POP/IMAP → Add a forwarding address → paste the address above.</li>
          <li>Gmail sends a confirmation email to that address; it shows up on this page. Click the link to confirm.</li>
          <li>Gmail → search bar → paste the filter below → Create filter → Forward it to the address above.</li>
        </ol>
        <div className="flex items-start gap-2 mt-2 bg-sage-50 rounded-lg px-3 py-2">
          <code className="text-xs text-ink-700 flex-1 break-all">{filter}</code>
          <Copy text={filter} label="Copy filter" />
        </div>
        <button onClick={() => setShowBanks((v) => !v)} className="text-xs text-forest-600 mt-2">
          {showBanks ? "Hide" : "Show"} sender addresses by bank
        </button>
        {showBanks && (
          <ul className="mt-2 text-xs text-ink-500 space-y-0.5">
            {chosen.map((b) => <li key={b.name}><span className="text-ink-700">{b.name}:</span> {b.senders.join(", ")}</li>)}
          </ul>
        )}
      </details>

      <button onClick={regenerate} className="text-xs text-ink-400 hover:text-danger">Get a new address</button>
    </section>
  );
}
