import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useApi } from "../lib/format";
import TelegramLink from "../components/TelegramLink";
import SecuritySettings from "../components/SecuritySettings";

const REPORTS = [
  ["weekly", "Weekly", "Monday to Sunday, sent Sunday at 7 pm"],
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
          className="border border-sage-200 rounded-lg px-2 py-1.5 bg-surface">
          {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hour(h)}</option>)}
        </select>
        <span>to</span>
        <select value={data.quiet_end} onChange={(e) => save({ quiet_end: Number(e.target.value) })} aria-label="Quiet hours end"
          className="border border-sage-200 rounded-lg px-2 py-1.5 bg-surface">
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

const ACTIVITY = {
  sign_in: "Signed in",
  export: "Exported your data",
  deleted: (d) => `Deleted ${d?.what || "an item"}`,
  telegram_linked: "Linked Telegram",
  telegram_unlinked: "Unlinked Telegram",
  address_regenerated: "Got a new forwarding address",
  settings_changed: (d) => `Changed settings${d?.fields?.length ? `: ${d.fields.map((f) => f.replaceAll("_", " ")).join(", ")}` : ""}`,
  profile_changed: "Changed your profile",
};
const describe = (e) => (typeof ACTIVITY[e.kind] === "function" ? ACTIVITY[e.kind](e.detail) : ACTIVITY[e.kind] || e.kind);
const when = (iso) => new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

function YourData() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const { data: events } = useApi("/api/activity", refreshKey);
  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.get("/api/export", { responseType: "blob", timeout: 120000, recent: true });
      const name = /filename="([^"]+)"/.exec(res.headers["content-disposition"] || "")?.[1] || "vaulta-export.zip";
      const url = URL.createObjectURL(res.data);
      const a = Object.assign(document.createElement("a"), { href: url, download: name });
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setError(err?.response?.status === 429 ? "You've exported a lot this hour. Try again later." : "Couldn't export your data. Try again.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card p-5 space-y-3" aria-labelledby="your-data-title">
      <h2 id="your-data-title" className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Your data</h2>
      <p className="text-sm text-ink-600">
        Download everything Vaulta holds about you as a zip: one JSON file and a CSV for each kind of record. It's built
        when you ask and isn't kept afterwards.
      </p>
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <button onClick={download} disabled={busy} className="btn-secondary">{busy ? "Preparing…" : "Export my data"}</button>
      <h3 className="text-sm font-medium text-ink-900 pt-2">Activity</h3>
      {!events ? <p className="text-xs text-ink-400">Loading…</p> : events.length === 0 ? (
        <p className="text-xs text-ink-500">Nothing yet. Sign-ins, exports, deletions, Telegram links and settings changes appear here.</p>
      ) : (
        <ul className="divide-y divide-sage-50 text-sm" aria-label="Account activity">
          {events.slice(0, 20).map((e, i) => (
            <li key={i} className="py-1.5 flex justify-between gap-4">
              <span className="text-ink-700">{describe(e)}</span>
              <time dateTime={e.at} className="text-ink-500 text-xs shrink-0">{when(e.at)}</time>
            </li>
          ))}
        </ul>
      )}
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
      await api.delete("/auth/me", { recent: true });
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
      <h1 className="font-display text-display-s text-ink">Settings</h1>
      {saveError && <p className="text-sm text-danger">{saveError}</p>}

      <ResumeSetup />

      <section className="card p-5 space-y-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">AI chat</h2>
        <Toggle checked={data.ai_chat_enabled} onChange={(v) => save({ ai_chat_enabled: v })} label="Let me ask questions in chat" />
        <p className="text-xs text-ink-500">
          When on, your question and the figures needed to answer it (merchant names, categories, amounts, dates) go to Groq,
          the AI service Vaulta uses. Statement text, account details, UPI IDs and notes never do. Report summaries are
          written the same way, from the report's figures, whether or not chat is on.
        </p>
      </section>

      <TelegramLink />

      <AlertsSection data={data} save={save} />

      <section className="card p-5 space-y-2">
        <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Time zone</h2>
        <select value={data.timezone} onChange={(e) => save({ timezone: e.target.value })} aria-label="Time zone"
          className="border border-sage-200 rounded-lg px-2 py-1.5 text-sm bg-surface">
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

      <SecuritySettings />

      <YourData />

      <DeleteEverything />
    </div>
  );
}
