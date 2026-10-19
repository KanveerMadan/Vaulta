import { useState } from "react";
import api from "../lib/api";
import { useApi } from "../lib/format";

const KIND = {
  bank_csv: "bank statement", bank_pdf: "bank statement (PDF)", credit_card: "card statement", upi_google_pay: "Google Pay",
  upi_phonepe: "PhonePe", upi_paytm: "Paytm", email_alert: "alert emails", telegram: "Telegram", manual: "added by hand",
};
const day = (iso) => iso && new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** Settings → Imports: delete one upload, or everything from one account, after seeing what goes (services/imports.py). */
export default function ImportsSettings() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useApi("/api/import/uploads", refreshKey);
  const [pending, setPending] = useState(null);      // {scope, title, preview}
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  const ask = async (scope, title) => {
    setMessage(null);
    try {
      const { data: preview } = await api.post("/api/import/delete-preview", scope);
      setPending({ scope, title, preview });
    } catch {
      setMessage("Couldn't check that import. Try again.");
    }
  };
  const remove = async () => {
    setBusy(true);
    try {
      const { data: done } = await api.post("/api/import/delete", pending.scope);
      setMessage(`Deleted ${plural(done.transactions_deleted, "transaction")}` +
        (done.transactions_kept ? `; kept ${done.transactions_kept} that another statement also shows.` : "."));
      setPending(null);
      setRefreshKey((k) => k + 1);
    } catch {
      setMessage("Couldn't delete that import. Nothing was changed; try again.");
    } finally {
      setBusy(false);
    }
  };

  const uploads = data?.uploads ?? [];
  const sources = data?.sources ?? [];
  return (
    <section className="card p-5 space-y-3" aria-labelledby="imports-heading">
      <h2 id="imports-heading" className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Imports</h2>
      <p className="text-sm text-ink-600">
        Imported the wrong file, or the same account twice? Delete one upload, or everything from one account.
        Transactions another statement also shows stay.
      </p>
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      {data && !uploads.length && !sources.length && <p className="text-sm text-ink-500">Nothing imported yet.</p>}

      {uploads.length > 0 && (
        <ul className="divide-y divide-line" aria-label="Uploads">
          {uploads.map((u) => {
            const title = `${u.source_label || KIND[u.source_type]} · imported ${day(u.created_at)}`;
            return (
              <li key={u.id} className="py-2 flex items-center justify-between gap-3">
                <span className="text-sm text-ink-700">
                  {u.source_label || KIND[u.source_type]}
                  <span className="block text-xs text-ink-500">
                    {plural(u.rows, "row")}{u.first_date && ` · ${day(u.first_date)} – ${day(u.last_date)}`} · imported {day(u.created_at)}
                  </span>
                </span>
                <button className="btn-quiet h-9 text-[13px] text-danger" onClick={() => ask({ import_id: u.id }, title)}
                  aria-label={`Delete ${title}`}>Delete</button>
              </li>
            );
          })}
        </ul>
      )}

      {sources.length > 0 && (
        <details>
          <summary className="text-sm text-ink-600 cursor-pointer">Everything from one account</summary>
          <ul className="divide-y divide-line mt-2" aria-label="Accounts">
            {sources.map((s) => {
              const title = `everything from ${s.source_label || KIND[s.source_type]}`;
              return (
                <li key={`${s.source_type}|${s.source_label}`} className="py-2 flex items-center justify-between gap-3">
                  <span className="text-sm text-ink-700">{s.source_label || KIND[s.source_type]}
                    <span className="block text-xs text-ink-500">{KIND[s.source_type]} · {plural(s.rows, "row")}</span></span>
                  <button className="btn-quiet h-9 text-[13px] text-danger"
                    onClick={() => ask({ source_type: s.source_type, source_label: s.source_label }, title)}
                    aria-label={`Delete ${title}`}>Delete all</button>
                </li>
              );
            })}
          </ul>
        </details>
      )}

      {pending && (
        <div role="alertdialog" aria-labelledby="delete-import-title" className="rounded-md border border-danger/40 bg-danger/5 p-4 space-y-2">
          <p id="delete-import-title" className="text-sm font-semibold text-ink">Delete {pending.title}?</p>
          <p className="text-sm text-ink-600">
            {plural(pending.preview.transactions_deleted, "transaction")} will be deleted
            {pending.preview.transactions_kept > 0 && `, and ${pending.preview.transactions_kept} kept because another statement also shows them`}.
            Transfers, recurring payments and people are worked out again afterwards. This can't be undone, but you can
            import the file again.
          </p>
          <div className="flex gap-2">
            <button className="btn-danger h-9 px-3 text-[13px]" onClick={remove} disabled={busy}>
              {busy ? "Deleting…" : `Delete ${plural(pending.preview.transactions_deleted, "transaction")}`}
            </button>
            <button className="btn-quiet h-9 text-[13px]" onClick={() => setPending(null)} disabled={busy}>Cancel</button>
          </div>
        </div>
      )}
      {message && <p className="text-sm text-ink-600" role="status">{message}</p>}
    </section>
  );
}
