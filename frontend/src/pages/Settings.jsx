import { useState } from "react";
import api from "../lib/api";
import { useApi } from "../lib/format";

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

      <section className="card p-5 space-y-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">AI chat</h2>
        <Toggle checked={data.ai_chat_enabled} onChange={(v) => save({ ai_chat_enabled: v })} label="Let me ask questions in chat" />
        <p className="text-xs text-ink-500">
          When on, your question and the figures needed to answer it (merchant names, categories, amounts, dates) go to an AI
          service. Statement text, account details and UPI IDs never do. Report summaries use the same rule.
        </p>
      </section>

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
    </div>
  );
}
