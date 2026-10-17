import { useState } from "react";
import { Link } from "react-router-dom";
import { ChatCircleText, EnvelopeSimple, FileText } from "@phosphor-icons/react";
import api from "../lib/api";
import { useAuthStore } from "../store/authStore";
import StatementUpload from "../components/StatementUpload";
import TransactionRow from "../components/TransactionRow";

// "Try it" (Phase 8): Vaulta's pipelines on sample input, before connecting anything real. Sample rows are labelled,
// never counted anywhere and go by themselves within an hour (backend core/samples.py). In the demo nothing is saved.

const BANKS = [["hdfc", "HDFC Bank (UPI)"], ["icici", "ICICI Bank credit card"], ["sbi", "SBI Card"], ["axis", "Axis Bank (UPI)"]];

function Card({ icon: Icon, title, children }) {
  return (
    <section className="card p-5 space-y-3" aria-label={title}>
      <h2 className="flex items-center gap-2 font-display text-lg text-ink"><Icon size={20} aria-hidden className="text-accent-text" />{title}</h2>
      {children}
    </section>
  );
}

function errorText(e) {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : "That didn't work. Try again in a moment.";
}

function AlertSimulation({ demo }) {
  const [bank, setBank] = useState("hdfc");
  const [state, setState] = useState(null);
  const run = async () => {
    setState({ busy: true });
    try { setState({ result: (await api.post("/api/simulations/bank-alert", { bank })).data }); }
    catch (e) { setState({ error: errorText(e) }); }
  };
  const r = state?.result;
  return (
    <Card icon={EnvelopeSimple} title="A bank alert email">
      <p className="text-sm text-ink-2">
        Vaulta reads the alert emails your bank already sends you. Send a sample one through the same steps a forwarded
        alert goes through: check the sender, find the transaction, mask personal details, categorise.
      </p>
      <div className="flex flex-wrap gap-2">
        <select value={bank} onChange={(e) => setBank(e.target.value)} aria-label="Bank" className="input sm:w-60">
          {BANKS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button onClick={run} disabled={state?.busy} className="btn-primary">Send a sample alert</button>
      </div>
      {state?.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
      {r && (
        <div className="space-y-3" aria-live="polite">
          <figure className="rounded-md border border-line bg-sunken p-3 text-sm">
            <figcaption className="text-micro text-muted">From {r.email.from} · {r.email.subject}</figcaption>
            <p className="mt-1 text-ink-2">{r.email.text}</p>
          </figure>
          <p className="text-sm text-ink">What Vaulta made of it:</p>
          <div className="rounded-md border border-line px-3"><TransactionRow txn={{ ...r.transaction, id: r.transaction.id || "preview", tags: [], splits: [], kind: r.transaction.kind || "spend", is_sample: true }} compact /></div>
          <p className="text-sm text-ink-2">{r.saved ? "Saved as a sample: it's in your transactions, labelled, and isn't counted." : "In the demo nothing is saved."}</p>
          {!demo && <Link to="/connect#forwarding" className="btn-secondary">Forward your real alerts</Link>}
        </div>
      )}
    </Card>
  );
}

function StatementSimulation() {
  const [file, setFile] = useState(null);
  const open = async () => {
    const res = await fetch("/samples/sample-statement.csv");
    setFile(new File([await res.blob()], "sample-statement.csv", { type: "text/csv" }));
  };
  return (
    <Card icon={FileText} title="A bank statement">
      <p className="text-sm text-ink-2">
        Open a sample HDFC Bank statement. It's read here in your browser, exactly as your own would be, and you'll see
        what's removed before anything could be sent. This is a sample: nothing is imported.
      </p>
      <button onClick={open} className="btn-primary">Open a sample statement</button>
      {file && <StatementUpload sample={file} onClose={() => setFile(null)} />}
    </Card>
  );
}

function QuickAddSimulation({ demo }) {
  const [text, setText] = useState("150 auto cash");
  const [state, setState] = useState(null);
  const send = async (save) => {
    setState((s) => ({ ...s, busy: true, error: null }));
    try { setState({ result: (await api.post("/api/simulations/quick-add", { text, save })).data }); }
    catch (e) { setState({ error: errorText(e) }); }
  };
  const r = state?.result;
  return (
    <Card icon={ChatCircleText} title="Quick add and Telegram">
      <p className="text-sm text-ink-2">Type an expense the way you'd text it. This is what the Telegram bot and the quick-add bar make of it.</p>
      <form onSubmit={(e) => { e.preventDefault(); send(false); }} className="flex flex-wrap gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={120} aria-label="Expense, like 150 auto cash" className="input flex-1 min-w-[12rem]" />
        <button disabled={!text.trim() || state?.busy} className="btn-primary">Try it</button>
      </form>
      {state?.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
      {r && (
        <div className="space-y-3" aria-live="polite">
          <div className="max-w-sm space-y-2">
            <p className="ml-auto w-fit rounded-md rounded-br-none bg-accent px-3 py-2 text-sm text-on-accent">{text}</p>
            <div className="w-fit rounded-md rounded-bl-none bg-sunken px-3 py-2 text-sm text-ink">
              <p>{r.reply.text}</p>
              <p className="mt-1 text-micro text-muted">{r.reply.buttons.join("   ")}</p>
            </div>
          </div>
          {r.saved ? <p className="text-sm text-ink-2">Saved as a sample cash entry: it's in your transactions, labelled, and isn't counted.</p>
            : demo ? <p className="text-sm text-ink-2">In the demo nothing is saved.</p>
              : <button onClick={() => send(true)} className="btn-secondary">Save it as a sample</button>}
          {!demo && (
            <div className="flex flex-wrap gap-2">
              <Link to="/settings#telegram" className="btn-secondary">Link Telegram</Link>
              <Link to="/" className="btn-quiet">Use quick add on your home page</Link>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default function Try() {
  const demo = useAuthStore((s) => s.demoToken);
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="font-display text-display-s text-ink">Try it with samples</h1>
        <p className="text-sm text-ink-2 mt-1">
          See what Vaulta does with each kind of input before connecting anything real. Samples are labelled, never counted
          in your numbers, and go by themselves within an hour.
        </p>
      </div>
      <AlertSimulation demo={Boolean(demo)} />
      <StatementSimulation />
      <QuickAddSimulation demo={Boolean(demo)} />
    </div>
  );
}
