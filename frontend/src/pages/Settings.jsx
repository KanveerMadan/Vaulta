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

function TelegramSection() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data } = useApi("/api/telegram", refreshKey);
  const [code, setCode] = useState(null);
  const reload = () => setRefreshKey((k) => k + 1);
  if (!data || !data.configured) return null;

  const getCode = async () => setCode((await api.post("/api/telegram/link-code")).data);
  const unlink = async () => { await api.delete("/api/telegram"); setCode(null); reload(); };
  const setWeekly = async (weekly) => { await api.patch("/api/telegram", { weekly }); reload(); };

  return (
    <section className="card p-5 space-y-3">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Telegram</h2>
      <p className="text-xs text-ink-500">
        Log expenses and ask questions from Telegram. Messages you send to the bot pass through Telegram.
        Bill photos are never read there; use Scan bill in the app so the photo stays on your phone.
      </p>
      {data.linked ? (
        <>
          <p className="text-sm text-safe">✓ Linked{data.bot_username ? ` to @${data.bot_username}` : ""}</p>
          <Toggle checked={data.weekly} onChange={setWeekly} label="Also send my weekly report summary on Telegram" />
          <button onClick={unlink} className="text-xs text-ink-400 hover:text-danger">Unlink Telegram</button>
        </>
      ) : code ? (
        <div className="text-sm space-y-2">
          {data.bot_username && (
            <a href={`https://t.me/${data.bot_username}?start=${code.code}`} target="_blank" rel="noopener noreferrer"
              className="inline-block btn-primary text-sm py-1.5 px-3">Open @{data.bot_username} and link</a>
          )}
          <p className="text-ink-700">Or send <code>/start {code.code}</code> to the bot. The code works once, for 10 minutes.</p>
          <button onClick={reload} className="text-xs text-forest-600">I've sent it</button>
        </div>
      ) : (
        <button onClick={getCode} className="btn-primary-light text-sm py-1.5 px-3">Link Telegram</button>
      )}
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

      <section className="card p-5 space-y-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">AI chat</h2>
        <Toggle checked={data.ai_chat_enabled} onChange={(v) => save({ ai_chat_enabled: v })} label="Let me ask questions in chat" />
        <p className="text-xs text-ink-500">
          When on, your question and the figures needed to answer it (merchant names, categories, amounts, dates) go to an AI
          service. Statement text, account details and UPI IDs never do. Report summaries use the same rule.
        </p>
      </section>

      <TelegramSection />

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
    </div>
  );
}
