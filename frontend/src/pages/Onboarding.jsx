import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useApi } from "../lib/format";
import InboundCard from "../components/InboundCard";
import TelegramLink from "../components/TelegramLink";
import StatementUpload from "../components/StatementUpload";
import ReviewFlow from "../components/ReviewFlow";
import { Ring, CoverageParts } from "../components/CoverageRing";
import Wordmark from "../ui/Wordmark";

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
      <legend className="label mb-2">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {choices.map(({ value, name }) => (
          <button type="button" key={value} onClick={() => toggle(value)} aria-pressed={selected.includes(value)}
            className={`text-sm px-3.5 py-2 rounded-full border transition-colors duration-fast ${selected.includes(value) ? "bg-accent text-on-accent border-accent" : "bg-surface text-ink-2 border-line-strong hover:border-muted"}`}>
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
        <label className="label space-y-1.5 block">Monthly take-home income (optional)
          <input className="input" inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={form.income} placeholder="85000"
            onChange={(e) => setForm({ ...form, income: e.target.value })} />
        </label>
        <label className="label space-y-1.5 block">Payday
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
      <label className="label space-y-1.5 block">Time zone
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
      Waiting for your test… Send any email from your inbox to the address above (or set up the Gmail forward; its
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
        Import the last 3 to 6 months so Vaulta can spot your recurring payments, the people you pay and what's normal for you.
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
  const automatic = [
    (s.email.connected || state.test_received) && ["Every forwarded bank alert", "becomes a transaction within seconds."],
    ["Every morning", "a fresh safe-to-spend figure and the month's forecast."],
    ["When something needs you", "an alert: a budget at 80%, a duplicate charge, a failed payment, a renewal tomorrow."],
    ["Every week and month", "a short report, by email if you want it."],
    ["When Vaulta isn't sure", "one quick question, answered in a tap."],
  ].filter(Boolean);
  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <p className="text-ink-2">{setUp.length ? "Set up:" : "Nothing is connected yet. You can add sources any time from Connect."}</p>
        {setUp.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {setUp.map((x) => <li key={x} className="tag-positive text-sm px-3 py-1">{x}</li>)}
          </ul>
        )}
      </div>
      <section aria-labelledby="automatic">
        <h2 id="automatic" className="font-display text-2xl text-ink">What Vaulta does from here</h2>
        <ol className="mt-4 border-t border-line">
          {automatic.map(([when, what], i) => (
            <li key={when} className="finish-row border-b border-line py-4 grid sm:grid-cols-[13rem_1fr] gap-1 sm:gap-4" style={{ "--i": i }}>
              <span className="font-semibold text-ink">{when}</span>
              <span className="text-ink-2">{what}</span>
            </li>
          ))}
        </ol>
      </section>
      <button onClick={done} className="btn-primary h-12 px-6">Go to home</button>
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
    <div className="min-h-dvh bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <Wordmark to="/onboarding" />
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted hidden sm:inline">Step {Math.min(index + 1, 4)} of 4</span>
            {state.step !== "finish" && <button onClick={() => leave("skipped")} className="btn-quiet text-sm">Skip setup</button>}
          </div>
        </div>
      </header>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 lg:py-12 grid lg:grid-cols-[17rem_minmax(0,1fr)] gap-8 lg:gap-14">
        {/* the meter: central on desktop, compact on phones */}
        <aside className="lg:sticky lg:top-8 self-start">
          <div className="flex lg:flex-col items-center lg:items-start gap-5">
            <div className="hidden lg:block"><Ring percent={pct} /></div>
            <div className="lg:hidden"><Ring percent={pct} size={84} stroke={7} /></div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink" aria-live="polite">Tracking coverage {pct}%</p>
              <p className="text-micro text-muted mt-0.5 mb-3 hidden lg:block">How much of your money Vaulta can see. Each source you add fills it in.</p>
              <div className="hidden lg:block"><CoverageParts parts={state.coverage.parts} max={state.coverage.max} /></div>
            </div>
          </div>
          <ol className="mt-4 lg:mt-8 flex lg:flex-col gap-2 text-sm" aria-label="Steps">
            {state.steps.slice(0, 4).map((st, i) => (
              <li key={st} aria-current={st === state.step ? "step" : undefined}
                className={`flex items-center gap-2 ${st === state.step ? "text-ink font-semibold" : i < index ? "text-accent-text" : "text-muted"}`}>
                <span className={`h-1 lg:h-auto lg:w-1 rounded-full ${st === state.step ? "bg-accent" : i < index ? "bg-accent-line" : "bg-line"} w-8 lg:self-stretch`} />
                <span className="hidden lg:inline">{STEP_TITLES[st]}</span>
              </li>
            ))}
          </ol>
        </aside>
        <main className="min-w-0 space-y-6">
          <h1 className="font-display text-display-s text-ink">{state.step === "finish" ? "You're set up." : STEP_TITLES[state.step]}</h1>
          {saveError && <p className="text-sm text-danger" role="alert">{saveError}</p>}
          {state.step === "basics" && <Basics state={state} save={save} />}
          {state.step === "connect" && <Connect state={state} save={save} reload={reload} />}
          {state.step === "import" && <ImportHistory state={state} save={save} />}
          {state.step === "review" && (
            <>
              <p className="text-ink-2">A few quick questions about people, recurring payments, transfers and budgets. Each answer fixes your numbers.</p>
              <ReviewFlow onDone={() => save({ step: "finish" })} doneLabel="Continue" />
            </>
          )}
          {state.step === "finish" && <Finish state={state} done={() => leave("done")} />}
          {index > 0 && state.step !== "finish" && (
            <button onClick={() => save({ step: state.steps[index - 1] })} className="btn-quiet text-muted">← Back</button>
          )}
        </main>
      </div>
    </div>
  );
}
