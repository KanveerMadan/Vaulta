import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useApi } from "../lib/format";
import InboundCard from "../components/InboundCard";
import TelegramLink from "../components/TelegramLink";
import StatementUpload from "../components/StatementUpload";
import ReviewFlow from "../components/ReviewFlow";

const STEP_TITLES = { basics: "Basics", connect: "Connect", import: "Import history", review: "First review", finish: "Done" };
const ZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney"];

// What the in-browser importer reads, per bank (src/import). Anything else: CSV/XLS with a one-time column mapping.
const STATEMENTS = {
  hdfc: ["Account statement: CSV, Excel or the PDF e-statement", "Credit card: the PDF statement"],
  icici: ["Account statement: CSV or Excel", "Credit card: the PDF statement"],
  sbi: ["Account statement: CSV or Excel"],
  sbicard: ["Credit card: the PDF statement"],
  axis: ["Account statement: CSV or Excel", "Credit card: the PDF statement"],
  kotak: ["Account statement: CSV or Excel"],
};
const UPI_STATEMENTS = { "Google Pay": "Google Pay: the PDF statement", PhonePe: "PhonePe: the PDF statement", Paytm: "Paytm: the PDF statement" };
const OTHER = "Account statement as CSV or Excel. You'll match the columns once and Vaulta remembers them.";

function Chips({ choices, selected, onChange, label }) {
  const toggle = (v) => onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
  return (
    <fieldset>
      <legend className="text-sm text-ink-600 mb-2">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {choices.map(({ value, name }) => (
          <button type="button" key={value} onClick={() => toggle(value)} aria-pressed={selected.includes(value)}
            className={`text-sm px-3 py-2 rounded-full border ${selected.includes(value) ? "bg-forest-400 text-white border-forest-400" : "bg-surface text-ink-700 border-sage-200"}`}>
            {name}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function Basics({ state, save }) {
  const [form, setForm] = useState({
    income: state.income ?? "", payday: state.payday ?? "", banks: state.banks, upi_apps: state.upi_apps, timezone: state.timezone,
  });
  const submit = (e) => {
    e.preventDefault();
    save({ income: form.income === "" ? null : form.income, payday: form.payday === "" ? null : Number(form.payday),
      banks: form.banks, upi_apps: form.upi_apps, timezone: form.timezone, step: "connect", status: "active" });
  };
  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label className="text-sm text-ink-600 space-y-1 block">Monthly take-home income (optional)
          <input className="input" inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={form.income} placeholder="85000"
            onChange={(e) => setForm({ ...form, income: e.target.value })} />
        </label>
        <label className="text-sm text-ink-600 space-y-1 block">Payday
          <select className="input" value={form.payday} onChange={(e) => setForm({ ...form, payday: e.target.value })}>
            <option value="">Not sure</option>
            {Array.from({ length: 31 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
          </select>
        </label>
      </div>
      <Chips label="Banks and cards you use" selected={form.banks} onChange={(banks) => setForm({ ...form, banks })}
        choices={state.bank_choices.map((b) => ({ value: b.key, name: b.name }))} />
      <Chips label="UPI apps you use" selected={form.upi_apps} onChange={(upi_apps) => setForm({ ...form, upi_apps })}
        choices={state.upi_choices.map((n) => ({ value: n, name: n }))} />
      <label className="text-sm text-ink-600 space-y-1 block">Time zone
        <select className="input" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })}>
          {(ZONES.includes(form.timezone) ? ZONES : [form.timezone, ...ZONES]).map((z) => <option key={z}>{z}</option>)}
        </select>
      </label>
      <button className="btn-primary">Continue</button>
    </form>
  );
}

function EmailTest({ state, onStart }) {
  if (state.test_received) return <p className="text-sm text-safe">✓ Your forwarding address works.</p>;
  if (!state.test_started_at) {
    return (
      <button onClick={onStart} className="btn-primary-light">Send test</button>
    );
  }
  return (
    <p className="text-sm text-ink-600" role="status">
      Waiting for your test… Send any email from your inbox to the address above (or set up the Gmail forward — its
      confirmation email counts too). This checks for it every few seconds.
    </p>
  );
}

function Connect({ state, save, reload }) {
  useEffect(() => {
    if (!state.test_started_at || state.test_received) return undefined;
    const id = setInterval(reload, 5000);
    return () => clearInterval(id);
  }, [state.test_started_at, state.test_received, reload]);
  const startTest = async () => { await api.post("/api/onboarding/test-email"); reload(); };
  return (
    <div className="space-y-4">
      <InboundCard banks={state.banks} />
      <div className="card p-5 space-y-2">
        <h3 className="font-medium text-ink-900">Check the address</h3>
        <EmailTest state={state} onStart={startTest} />
      </div>
      <TelegramLink />
      <div className="flex gap-3">
        <button onClick={() => save({ step: "import" })} className="btn-primary">Continue</button>
        <button onClick={() => save({ step: "import" })} className="btn-ghost">Skip for now</button>
      </div>
    </div>
  );
}

function ImportHistory({ state, save }) {
  const [uploading, setUploading] = useState(false);
  const lines = [...new Set([
    ...state.banks.flatMap((k) => (STATEMENTS[k] || [OTHER]).map((l) => `${state.bank_choices.find((b) => b.key === k)?.name}: ${l}`)),
    ...state.upi_apps.filter((a) => UPI_STATEMENTS[a]).map((a) => UPI_STATEMENTS[a]),
  ])];
  const months = state.sources.statements.months;
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-600">
        Import the last 3–6 months so Vaulta can spot your recurring payments, the people you pay and what's normal for you.
        Statements are read on this device; only the rows you confirm are sent.
      </p>
      {lines.length > 0 && (
        <div className="card p-5">
          <h3 className="text-sm font-medium text-ink-900 mb-2">What to download</h3>
          <ul className="list-disc pl-5 text-sm text-ink-600 space-y-1">{lines.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}
      {months > 0 && <p className="text-sm text-safe">✓ {months} month{months === 1 ? "" : "s"} of history imported.</p>}
      {uploading ? (
        <StatementUpload onClose={() => { setUploading(false); save({}); }} onSuccess={() => save({})} />
      ) : (
        <button onClick={() => setUploading(true)} className="btn-primary-light">Import a statement</button>
      )}
      <div className="flex gap-3">
        <button onClick={() => save({ step: "review" })} className="btn-primary">Continue</button>
        <button onClick={() => save({ step: "review" })} className="btn-ghost">Skip for now</button>
      </div>
    </div>
  );
}

function Finish({ state, done }) {
  const s = state.sources;
  const setUp = [
    s.statements.active && `${s.statements.months} month${s.statements.months === 1 ? "" : "s"} of statement history`,
    (s.email.connected || state.test_received) && "Bank alert forwarding",
    s.telegram.active && "Telegram",
    state.banks.length > 0 && `${state.banks.length} bank${state.banks.length === 1 ? "" : "s"} and cards noted`,
  ].filter(Boolean);
  return (
    <div className="space-y-5">
      <div className="card p-5">
        <h3 className="font-medium text-ink-900 mb-2">Set up</h3>
        {setUp.length ? <ul className="list-disc pl-5 text-sm text-ink-700 space-y-1">{setUp.map((x) => <li key={x}>{x}</li>)}</ul>
          : <p className="text-sm text-ink-500">Nothing yet — you can add sources any time from Connect.</p>}
      </div>
      <div className="card p-5">
        <h3 className="font-medium text-ink-900 mb-2">What Vaulta does from here</h3>
        <ul className="list-disc pl-5 text-sm text-ink-700 space-y-1">
          {(s.email.connected || state.test_received) && <li>Adds each forwarded bank alert as a transaction.</li>}
          <li>Works out what's safe to spend each day and how the month is going.</li>
          <li>Alerts you about budgets nearing their limit, duplicate charges, failed payments and renewals.</li>
          <li>Sends a weekly and a monthly report (change this in Settings).</li>
          <li>Asks you a quick question when it isn't sure about something.</li>
        </ul>
      </div>
      <button onClick={done} className="btn-primary">Go to home</button>
    </div>
  );
}

export default function Onboarding() {
  const navigate = useNavigate();
  const [refreshKey, setRefreshKey] = useState(0);
  const { data: fetched, error } = useApi("/api/onboarding", refreshKey);
  const [local, setLocal] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const state = local ?? fetched;
  const reload = () => { setLocal(null); setRefreshKey((k) => k + 1); };

  const save = async (changes) => {
    try {
      setLocal((await api.patch("/api/onboarding", changes)).data);
      setSaveError(null);
    } catch (err) {
      setSaveError(err?.response?.data?.detail && typeof err.response.data.detail === "string"
        ? err.response.data.detail : "Couldn't save that. Try again.");
    }
  };
  const leave = async (status) => { await save({ status }); navigate("/"); };

  if (error) return <div className="max-w-xl mx-auto p-6 text-sm text-danger">{error}</div>;
  if (!state) return <div className="max-w-xl mx-auto p-6 text-sm text-ink-400">Loading…</div>;
  const index = state.steps.indexOf(state.step);
  const pct = state.coverage.percent;

  return (
    <div className="min-h-dvh bg-sage-50">
      <header className="bg-surface border-b border-sage-200">
        <div className="max-w-2xl mx-auto px-4 py-3 space-y-2">
          <div className="flex items-center justify-between gap-3">
            <span className="font-display text-lg text-ink-900">Vaulta</span>
            {state.step !== "finish" && <button onClick={() => leave("skipped")} className="text-sm text-ink-400 hover:text-ink-700 px-2 py-2">Skip setup</button>}
          </div>
          <div>
            <div className="flex justify-between text-xs text-ink-500 mb-1">
              <span>Tracking coverage {pct}%</span>
              <span>Step {Math.min(index + 1, 4)} of 4 · {STEP_TITLES[state.step]}</span>
            </div>
            <div className="h-2 bg-sage-100 rounded-full overflow-hidden" role="progressbar" aria-label="Tracking coverage"
              aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full bg-forest-400 rounded-full transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>
      </header>
      <main className="max-w-2xl mx-auto px-4 py-6 space-y-4">
        <h1 className="font-display text-2xl text-ink-900">{STEP_TITLES[state.step]}</h1>
        {saveError && <p className="text-sm text-danger" role="alert">{saveError}</p>}
        {state.step === "basics" && <Basics state={state} save={save} />}
        {state.step === "connect" && <Connect state={state} save={save} reload={reload} />}
        {state.step === "import" && <ImportHistory state={state} save={save} />}
        {state.step === "review" && (
          <>
            <p className="text-sm text-ink-600">A few quick questions about people, recurring payments, transfers and budgets. Each answer fixes your numbers.</p>
            <ReviewFlow onDone={() => save({ step: "finish" })} doneLabel="Continue" />
          </>
        )}
        {state.step === "finish" && <Finish state={state} done={() => leave("done")} />}
        {index > 0 && state.step !== "finish" && (
          <button onClick={() => save({ step: state.steps[index - 1] })} className="text-sm text-ink-400 hover:text-ink-700">← Back</button>
        )}
      </main>
    </div>
  );
}
