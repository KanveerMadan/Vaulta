import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useApi } from "../lib/format";
import TelegramLink from "../components/TelegramLink";

const REPORTS = [
  ["weekly", "Weekly", "Monday–Sunday, on Sunday at 7 pm"],
  ["monthly", "Monthly", "the previous month, on the 1st at 9 am"],
  ["annual", "Yearly", "with Money Wrapped, on 1 January at 9 am"],
];
const ZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney"];

function Toggle({ checked, onChange, label, disabled }) {
  return (
    <label className={`flex items-center gap-2 text-sm ${disabled ? "opacity-50" : ""}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

const ALERTS = {
  budget_threshold: "Budget reaches 80% / 100%",
  duplicate_charge: "Possible duplicate charge",
  failed_upi_unreversed: "Failed payment not refunded",
  renewal_tomorrow: "Bill or subscription due tomorrow",
  price_change: "Subscription price change",
  salary_received: "Salary or large income received",
  unusual_amount: "Unusually large payment",
};
const hour = (h) => `${String(h).padStart(2, "0")}:00`;

function AlertsSection({ data, save }) {
  return (
    <section className="card p-5 space-y-3">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Alerts</h2>
      <p className="text-xs text-ink-500">Every alert appears under the bell. Choose where else each one goes. Alerts contain merchant names and amounts only.</p>
      <ul className="divide-y divide-sage-50">
        {Object.entries(ALERTS).map(([type, label]) => (
          <li key={type} className="py-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="text-sm text-ink-900 flex-1 min-w-[12rem]">{label}</span>
            <Toggle checked={data.alert_channels[type].telegram} label="Telegram"
              onChange={(v) => save({ alert_channels: { [type]: { telegram: v } } })} />
            <Toggle checked={data.alert_channels[type].email} label="Email" disabled={!data.email_configured}
              onChange={(v) => save({ alert_channels: { [type]: { email: v } } })} />
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-700">
        <span>Quiet hours for Telegram:</span>
        <select value={data.quiet_start} onChange={(e) => save({ quiet_start: Number(e.target.value) })} aria-label="Quiet hours start"
          className="border border-sage-200 rounded-lg px-2 py-1.5 bg-white">
          {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hour(h)}</option>)}
        </select>
        <span>to</span>
        <select value={data.quiet_end} onChange={(e) => save({ quiet_end: Number(e.target.value) })} aria-label="Quiet hours end"
          className="border border-sage-200 rounded-lg px-2 py-1.5 bg-white">
          {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hour(h)}</option>)}
        </select>
      </div>
      <p className="text-xs text-ink-500">Telegram alerts that arrive during quiet hours are sent when they end.</p>
    </section>
  );
}

function ResumeSetup() {
  const navigate = useNavigate();
  const { data } = useApi("/api/onboarding", 0);
  if (!data) return null;
  const resume = async () => {
    await api.patch("/api/onboarding", { status: "active", ...(data.status === "done" ? { step: "basics" } : {}) });
    navigate("/onboarding");
  };
  return (
    <section className="card p-5 space-y-2">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Setup</h2>
      <p className="text-sm text-ink-600">Tracking coverage {data.coverage.percent}%{data.status === "done" ? " · setup finished" : ""}.</p>
      <button onClick={resume} className="btn-primary-light text-sm">{data.status === "done" ? "Run setup again" : "Resume setup"}</button>
    </section>
  );
}

function DeleteEverything() {
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  const [error, setError] = useState(null);
  const remove = async () => {
    setError(null);
    try {
      await api.delete("/auth/me");
    } catch (err) {
      setError(err?.response?.data?.detail || "Couldn't delete your data. Try again.");
      return;
    }
    const { getAuth, signOut } = await import("firebase/auth");
    try { await getAuth().currentUser?.delete(); } catch { await signOut(getAuth()); }   // needs a recent sign-in
    navigate("/welcome");
  };
  return (
    <section className="card p-5 space-y-2">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Delete everything</h2>
      <p className="text-sm text-ink-600">
        Permanently deletes your account and all your data from Vaulta: transactions, budgets, goals, reports, alerts, chat
        history and settings. This can't be undone.
      </p>
      <label className="text-sm text-ink-600 block">Type DELETE to confirm
        <input className="input mt-1" value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Type DELETE to confirm" />
      </label>
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <button onClick={remove} disabled={typed !== "DELETE"} className="btn-ghost text-danger disabled:opacity-40">Delete my account and data</button>
    </section>
  );
}

export default function Settings() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/settings", refreshKey);
  const [saveError, setSaveError] = useState(null);
  const save = async (changes) => {
    try {
      await api.patch("/api/settings", changes);
      setSaveError(null);
    } catch {
      setSaveError("Couldn't save that setting.");
    }
    setRefreshKey((k) => k + 1);
  };
  if (error) return <div className="card p-5 text-sm text-danger">{error}</div>;
  if (!data) return <div className="card p-5 text-sm text-ink-400">Loading…</div>;
  const zones = ZONES.includes(data.timezone) ? ZONES : [data.timezone, ...ZONES];

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <h1 className="font-display text-2xl font-semibold text-ink-900">Settings</h1>
      {saveError && <p className="text-sm text-danger">{saveError}</p>}

      <ResumeSetup />

      <section className="card p-5 space-y-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">AI chat</h2>
        <Toggle checked={data.ai_chat_enabled} onChange={(v) => save({ ai_chat_enabled: v })} label="Let me ask questions in chat" />
        <p className="text-xs text-ink-500">
          When on, your question and the figures needed to answer it (merchant names, categories, amounts, dates) go to an AI
          service. Statement text, account details and UPI IDs never do. Report summaries use the same rule.
        </p>
      </section>

      <TelegramLink />

      <AlertsSection data={data} save={save} />

      <section className="card p-5 space-y-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Time zone</h2>
        <select value={data.timezone} onChange={(e) => save({ timezone: e.target.value })} aria-label="Time zone"
          className="border border-sage-200 rounded-lg px-2 py-1.5 text-sm bg-white">
          {zones.map((z) => <option key={z}>{z}</option>)}
        </select>
        <p className="text-xs text-ink-500">Reports are sent at these local times.</p>
      </section>

      <section className="card p-5 space-y-3">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Reports</h2>
        {!data.email_configured && <p className="text-xs text-gold">Email isn't set up on this server yet; reports still appear in the app.</p>}
        {REPORTS.map(([key, title, when]) => (
          <div key={key} className="flex items-center gap-4 flex-wrap border-b border-sage-50 last:border-0 pb-2">
            <div className="flex-1 min-w-[12rem]">
              <p className="text-sm font-medium text-ink-900">{title}</p>
              <p className="text-xs text-ink-500">{when}</p>
            </div>
            <Toggle checked={data[`reports_${key}`]} onChange={(v) => save({ [`reports_${key}`]: v })} label="Build" />
            <Toggle checked={data[`email_${key}`]} disabled={!data[`reports_${key}`]}
              onChange={(v) => save({ [`email_${key}`]: v })} label="Email me" />
          </div>
        ))}
      </section>

      <DeleteEverything />
    </div>
  );
}
