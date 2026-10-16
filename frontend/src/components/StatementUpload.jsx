import Sheet from "../ui/Sheet";
import { useState, useRef, useMemo } from "react";
import api from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { parseStatement, ImportError } from "../import";
import { applyMapping, guessMapping } from "../import/mapping";
import { sanitizeRows } from "../import/pii";
import RemovedPanel from "./RemovedPanel";
import { sendRows, loadTemplate, saveTemplate } from "../import/submit";
import ColumnMapping from "./ColumnMapping";

const MAX_FILE_SIZE_MB = 20;
const ACCEPT = ".csv,.xls,.xlsx,.pdf,.png,.jpg,.jpeg,.webp,text/csv,application/pdf,image/*,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const VALID = { date: /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$/, amount: /^\d{1,10}\.\d{2}$/, description_raw: /\S/ };

export const ON_DEVICE_NOTICE =
  "Your statement is processed on your device and never uploaded. Only the rows shown here are sent.";

// Common password formats for e-statements. Banks change these; the email
// that delivered the statement states the current rule.
const PASSWORD_HINTS = [
  ["HDFC Bank account", "Customer ID"],
  ["HDFC credit card", "First 4 letters of your name in CAPS + DDMM of birth"],
  ["ICICI Bank", "First 4 letters of your name in lowercase + DDMM of birth"],
  ["SBI account", "Last 5 digits of registered mobile + DOB as DDMMYY"],
  ["SBI Card", "DOB as DDMMYYYY + last 4 digits of the card"],
  ["Axis Bank", "First 4 letters of your name in CAPS + DDMM of birth"],
  ["Kotak", "CRN (customer relationship number)"],
];

function Notice() {
  return (
    <div className="flex items-start gap-2 bg-forest-50 border border-forest-200 rounded-xl px-3 py-2.5">
      <svg className="w-4 h-4 text-forest-600 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
      <p className="text-sm text-forest-800">{ON_DEVICE_NOTICE}</p>
    </div>
  );
}

function ErrorBox({ message }) {
  return (
    <div className="bg-danger/5 border border-danger/20 rounded-xl px-4 py-3">
      <p className="text-sm text-danger">{message}</p>
    </div>
  );
}

const fmtDate = (d) => new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

function EditCell({ value, field, onEdit, label }) {
  const bad = !VALID[field].test(value);
  return (
    <input value={value} onChange={(e) => onEdit(field, e.target.value)} aria-label={label} aria-invalid={bad}
      className={`w-full min-w-[5rem] border rounded px-1 py-0.5 bg-surface ${bad ? "border-danger" : "border-gold"}`} />
  );
}

function Preview({ parsed, rawRows, onConfirm, onBack, sending, progress, onEdit }) {
  const { rows, removed, lowConfidence } = parsed;
  const invalid = [...lowConfidence].some((i) => Object.entries(VALID).some(([f, re]) => !re.test(rows[i][f])));
  const [excluded, setExcluded] = useState(() => new Set());
  const toggle = (i) => setExcluded((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; });
  const included = rows.filter((_, i) => !excluded.has(i));
  const dates = rows.map((r) => r.date).sort();

  return (
    <div className="space-y-4">
      <Notice />
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <p className="text-sm text-ink-700">
          <span className="font-semibold text-ink-900">{rows.length}</span> transactions from {parsed.source_label},{" "}
          {fmtDate(dates[0])} to {fmtDate(dates[dates.length - 1])}
        </p>
      </div>

      {lowConfidence.size > 0 && (
        <div className="bg-gold/10 border border-gold/30 rounded-xl px-3 py-2.5 text-sm text-ink-700">
          {lowConfidence.size} row{lowConfidence.size === 1 ? " was" : "s were"} read from a scan or photo with low confidence.
          Check the highlighted rows and fix anything misread before importing.
        </div>
      )}

      <RemovedPanel rawRows={rawRows} cleanRows={rows} removed={removed} />

      <div className="max-h-80 overflow-auto border border-sage-100 rounded-xl">
        <table className="w-full text-xs stack-table">
          <thead className="bg-sage-50 sticky top-0">
            <tr className="text-left text-ink-500">
              <th className="px-2 py-1.5 w-6"><span className="sr-only">Include</span></th>
              <th className="px-2 py-1.5">Date</th>
              <th className="px-2 py-1.5">Merchant</th>
              <th className="px-2 py-1.5 text-right">Amount</th>
              <th className="px-2 py-1.5">Type</th>
              <th className="px-2 py-1.5">Reference</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={`border-t border-sage-50 ${excluded.has(i) ? "opacity-40" : ""} ${lowConfidence.has(i) ? "bg-gold/10" : ""}`}>
                <td className="px-2 py-1" data-label="Include">
                  <label className="inline-flex items-center justify-center">
                    <input type="checkbox" checked={!excluded.has(i)} onChange={() => toggle(i)}
                      aria-label={`Include ${r.description_raw} on ${r.date}`} />
                  </label>
                </td>
                {lowConfidence.has(i) ? (
                  <>
                    <td className="px-2 py-1" data-label="Date"><EditCell value={r.date} field="date" label="Date" onEdit={(f, v) => onEdit(i, f, v)} /></td>
                    <td className="px-2 py-1" data-label="Merchant"><EditCell value={r.description_raw} field="description_raw" label="Merchant" onEdit={(f, v) => onEdit(i, f, v)} /></td>
                    <td className="px-2 py-1" data-label="Amount"><EditCell value={r.amount} field="amount" label="Amount" onEdit={(f, v) => onEdit(i, f, v)} /></td>
                  </>
                ) : (
                  <>
                    <td className="px-2 py-1 whitespace-nowrap text-ink-600" data-label="Date">{r.date.slice(0, 10)}</td>
                    <td className="px-2 py-1 text-ink-800 max-w-[14rem] truncate" title={r.description_raw} data-label="Merchant">{r.description_raw}</td>
                    <td className="px-2 py-1 text-right font-mono whitespace-nowrap" data-label="Amount">₹{Number(r.amount).toLocaleString("en-IN")}</td>
                  </>
                )}
                <td data-label="Type" className={`px-2 py-1 whitespace-nowrap ${r.direction === "credit" ? "text-safe" : "text-ink-600"}`}>
                  {r.type === "transfer" ? "Transfer" : r.direction === "credit" ? "Credit" : "Debit"}
                </td>
                <td className="px-2 py-1 font-mono text-ink-400 whitespace-nowrap" data-label="Reference">{r.reference || <span className="sr-only">none</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex gap-3">
        <button onClick={onBack} disabled={sending} className="btn-ghost flex-1 text-sm py-2">Choose another file</button>
        <button
          onClick={() => onConfirm(included)}
          disabled={!included.length || sending || invalid}
          className="btn-primary flex-1 text-sm py-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {sending ? `Sending ${progress?.[0] ?? 0}/${progress?.[1] ?? included.length}…` : `Import ${included.length} transactions`}
        </button>
      </div>
    </div>
  );
}

function Result({ result, onAnother, onClose }) {
  const stats = [
    ["Added", result.imported],
    ["Already had", result.duplicates_merged],
    ["Transfers", result.transfers_flagged],
    ["Need a category", result.rows_needing_review],
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        {stats.map(([label, value]) => (
          <div key={label} className="bg-surface rounded-lg p-2.5 border border-sage-100">
            <p className="font-mono text-lg font-semibold text-ink-900">{value}</p>
            <p className="text-xs text-ink-400 mt-0.5 leading-tight">{label}</p>
          </div>
        ))}
      </div>
      {result.transfers_flagged > 0 && (
        <p className="text-xs text-ink-500">Transfers (card bill payments, self transfers) are kept out of your spending and income.</p>
      )}
      {result.failed > 0 && <ErrorBox message={`${result.failed} rows couldn't be saved. Importing the file again retries just those.`} />}
      <div className="flex gap-3">
        <button onClick={onAnother} className="btn-ghost flex-1 text-sm py-2">Import another</button>
        <button onClick={() => { onClose?.(); window.location.href = "/"; }} className="btn-primary flex-1 text-sm py-2">
          View dashboard
        </button>
      </div>
    </div>
  );
}

export default function StatementUpload({ onSuccess, onClose }) {
  // Used in memory to replace the holder's own name in narrations with "SELF"
  const holderName = useAuthStore((s) => s.user?.displayName);
  const [step, setStep] = useState("pick"); // pick | password | mapping | preview | done
  const [file, setFile] = useState(null);
  const [password, setPassword] = useState("");
  const [passwordWrong, setPasswordWrong] = useState(false);
  const [mappingState, setMappingState] = useState(null);
  const [rawResult, setRawResult] = useState(null); // {rows, source_type, source_label}
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  const preview = useMemo(() => {
    if (!rawResult) return null;
    const { rows, removed, lowConfidence } = sanitizeRows(rawResult.rows, { holderName });
    return { ...rawResult, rows, removed, lowConfidence };
  }, [rawResult, holderName]);

  const reset = () => {
    setStep("pick"); setFile(null); setPassword(""); setPasswordWrong(false); setMappingState(null);
    setRawResult(null); setError(null); setResult(null); setProgress(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const showRows = (rows, source_type, source_label) => {
    if (!rows.length) {
      setError("No transactions found in this file.");
      setStep("pick");
      return;
    }
    setRawResult({ rows, source_type, source_label });
    setStep("preview");
  };

  const run = async (f, pw) => {
    setBusy(true);
    setError(null);
    try {
      const parsed = await parseStatement(f, { password: pw || undefined });
      if (parsed.status === "needs_password") {
        setPasswordWrong(parsed.incorrect);
        setStep("password");
        return;
      }
      setPassword(""); // never kept beyond opening the file
      if (parsed.status === "ok") {
        showRows(parsed.rows, parsed.source_type, parsed.source_label);
        return;
      }
      // needs_mapping: reuse a saved mapping for this header layout if there is one
      const label = parsed.format === "pdf" ? "Bank statement (PDF)" : "Bank statement";
      const template = await loadTemplate(api, parsed.fingerprint).catch(() => null);
      if (template && template.column_count === parsed.table.header.length) {
        const rows = applyMapping(parsed.table, template.mapping, { source_type: parsed.source_type, source_label: label });
        if (rows.length) {
          showRows(rows, parsed.source_type, label);
          return;
        }
      }
      setMappingState({ ...parsed, label, initial: guessMapping(parsed.table.header, parsed.table.rows) });
      setStep("mapping");
    } catch (e) {
      setError(e instanceof ImportError ? e.message : "Couldn't read this file. Check that it's a statement export.");
      setStep("pick");
    } finally {
      setBusy(false);
    }
  };

  const handleFile = (f) => {
    if (!f) return;
    if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setError(`File is too large (max ${MAX_FILE_SIZE_MB} MB).`);
      return;
    }
    setFile(f);
    run(f);
  };

  const onMappingConfirm = async (mapping, rows) => {
    const { fingerprint, table, source_type, label } = mappingState;
    saveTemplate(api, fingerprint, { columnCount: table.header.length, sourceType: source_type, mapping })
      .catch(() => {}); // remembering the layout is a convenience; import continues without it
    showRows(rows, source_type, label);
  };

  const confirm = async (rows) => {
    setBusy(true);
    setError(null);
    try {
      const totals = await sendRows(api, rows, { onProgress: (done, total) => setProgress([done, total]) });
      setResult(totals);
      setStep("done");
      onSuccess?.();
    } catch (err) {
      setError(err?.response?.data?.detail?.[0]?.msg || err?.response?.data?.detail || "Import failed. Nothing is lost: try again and already-saved rows are skipped.");
    } finally {
      setBusy(false);
      setProgress(null);
    }
  };

  return (
    <Sheet title="Import statement" onClose={onClose} wide={step === "preview" || step === "mapping"}>
      <div>
        <p className="text-sm text-muted -mt-1 mb-4">Bank CSV, Excel or PDF, credit card PDF, Google Pay, PhonePe or Paytm</p>

        <div className="space-y-5">
          {error && <ErrorBox message={typeof error === "string" ? error : "Import failed."} />}

          {step === "pick" && (
            <>
              <Notice />
              <div
                onDrop={(e) => { e.preventDefault(); setDragActive(false); handleFile(e.dataTransfer.files?.[0]); }}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onClick={() => !busy && inputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer
                  ${dragActive ? "border-forest-500 bg-forest-50" : "border-sage-300 hover:border-forest-400 hover:bg-sage-50"}`}
              >
                <input ref={inputRef} type="file" accept={ACCEPT} className="hidden"
                  onChange={(e) => handleFile(e.target.files?.[0])} />
                {busy ? (
                  <p className="text-sm text-ink-600">
                    Reading {file?.name} on your device…
                    {/\.(png|jpe?g|webp)$/i.test(file?.name || "") && " Recognising text in the image can take a minute."}
                  </p>
                ) : (
                  <>
                    <p className="text-sm text-ink-600">
                      Drop your statement here, or <span className="text-forest-600 font-medium">browse</span>
                    </p>
                    <p className="text-xs text-ink-400 mt-1">CSV, Excel, PDF or a photo of a statement, up to {MAX_FILE_SIZE_MB} MB. Bank or app is detected automatically.</p>
                  </>
                )}
              </div>
            </>
          )}

          {step === "password" && (
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(file, password); }}>
              <Notice />
              <div>
                <p className="font-medium text-ink-900">{file?.name} is password-protected</p>
                <p className="text-sm text-ink-500 mt-0.5">The password is used on this device to open the file. It isn't sent or saved.</p>
              </div>
              <input
                type="password" autoFocus autoComplete="off" value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-sage-200 rounded-lg px-3 py-2 text-sm" placeholder="Statement password"
                aria-invalid={passwordWrong}
              />
              {passwordWrong && <p className="text-sm text-danger">That password didn't open the file.</p>}
              <details className="text-xs text-ink-500">
                <summary className="cursor-pointer text-forest-600 font-medium">Common password formats</summary>
                <ul className="mt-2 space-y-1">
                  {PASSWORD_HINTS.map(([bank, hint]) => <li key={bank}><span className="text-ink-700">{bank}:</span> {hint}</li>)}
                </ul>
                <p className="mt-2">Banks change these. The email your statement came with states the current format.</p>
              </details>
              <div className="flex gap-3">
                <button type="button" onClick={reset} className="btn-ghost flex-1 text-sm py-2">Cancel</button>
                <button type="submit" disabled={!password || busy} className="btn-primary flex-1 text-sm py-2 disabled:opacity-50">
                  {busy ? "Opening…" : "Open"}
                </button>
              </div>
            </form>
          )}

          {step === "mapping" && mappingState && (
            <ColumnMapping
              table={mappingState.table}
              initialMapping={mappingState.initial}
              sourceType={mappingState.source_type}
              onConfirm={onMappingConfirm}
              onCancel={reset}
            />
          )}

          {step === "preview" && preview && (
            <Preview parsed={preview} rawRows={rawResult.rows} onConfirm={confirm} onBack={reset} sending={busy} progress={progress}
              onEdit={(i, field, value) => setRawResult((r) => ({
                ...r, rows: r.rows.map((row, j) => (j === i ? { ...row, [field]: value } : row)),
              }))} />
          )}

          {step === "done" && result && <Result result={result} onAnother={reset} onClose={onClose} />}
        </div>
      </div>
    </Sheet>
  );
}
