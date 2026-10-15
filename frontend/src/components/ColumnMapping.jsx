import { useMemo, useState } from "react";
import { applyMapping, DATE_FORMATS } from "../import/mapping";

const FIELDS = [
  { key: "date", label: "Date", required: true },
  { key: "description", label: "Description", required: true },
  { key: "debit", label: "Debit (money out)" },
  { key: "credit", label: "Credit (money in)" },
  { key: "amount", label: "Single amount column" },
  { key: "reference", label: "Reference / UTR" },
];

const FORMAT_EXAMPLES = {
  "%d/%m/%Y": "31/01/2024", "%d/%m/%y": "31/01/24", "%d-%m-%Y": "31-01-2024", "%d-%m-%y": "31-01-24",
  "%d.%m.%Y": "31.01.2024", "%d %b %Y": "31 Jan 2024", "%d-%b-%Y": "31-Jan-2024", "%d %b %y": "31 Jan 24",
  "%d-%b-%y": "31-Jan-24", "%d %b, %Y": "31 Jan, 2024", "%Y-%m-%d": "2024-01-31", "%m/%d/%Y": "01/31/2024",
};

/**
 * Map columns of an unrecognized statement table. Everything here runs on the
 * table already in memory; onConfirm receives the mapping (column indices and
 * a date format only) and the rows it produces.
 */
export default function ColumnMapping({ table, initialMapping, sourceType, onConfirm, onCancel }) {
  const [mapping, setMapping] = useState(initialMapping);
  const set = (key, value) => setMapping((m) => ({ ...m, [key]: value }));

  const parsed = useMemo(
    () => applyMapping(table, mapping, { source_type: sourceType, source_label: "Custom layout" }),
    [table, mapping, sourceType],
  );
  const hasAmount = mapping.debit != null || mapping.credit != null || mapping.amount != null;
  const valid = mapping.date != null && mapping.description != null && hasAmount && parsed.length > 0;

  return (
    <div className="space-y-4">
      <div>
        <p className="font-medium text-ink-900">We didn't recognise this layout</p>
        <p className="text-sm text-ink-500 mt-0.5">
          Tell us which column is which. We'll remember it for statements with the same columns.
        </p>
      </div>

      <div className="overflow-x-auto border border-sage-100 rounded-xl">
        <table className="text-xs w-full stack-table">
          <thead className="bg-sage-50">
            <tr>
              {table.header.map((h, i) => (
                <th key={i} className="px-2 py-1.5 text-left font-medium text-ink-600 whitespace-nowrap">
                  <span className="text-ink-300 mr-1">{i + 1}</span>{h || "—"}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.slice(0, 5).map((r, ri) => (
              <tr key={ri} className="border-t border-sage-50">
                {table.header.map((_, ci) => (
                  <td key={ci} data-label={table.header[ci] || `Column ${ci + 1}`} className="px-2 py-1 text-ink-700 whitespace-nowrap max-w-[12rem] truncate">{r[ci]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {FIELDS.map(({ key, label, required }) => (
          <label key={key} className="text-sm text-ink-700 flex flex-col gap-1">
            <span>{label}{required && <span className="text-danger"> *</span>}</span>
            <select
              className="border border-sage-200 rounded-lg px-2 py-1.5 bg-surface"
              value={mapping[key] ?? ""}
              onChange={(e) => set(key, e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">— not in this file —</option>
              {table.header.map((h, i) => (
                <option key={i} value={i}>{i + 1}. {h || `Column ${i + 1}`}</option>
              ))}
            </select>
          </label>
        ))}
        <label className="text-sm text-ink-700 flex flex-col gap-1">
          <span>Date format</span>
          <select
            className="border border-sage-200 rounded-lg px-2 py-1.5 bg-surface"
            value={mapping.date_format}
            onChange={(e) => set("date_format", e.target.value)}
          >
            {DATE_FORMATS.map((f) => <option key={f} value={f}>{FORMAT_EXAMPLES[f]}</option>)}
          </select>
        </label>
        {mapping.amount != null && (
          <label className="text-sm text-ink-700 flex flex-col gap-1">
            <span>Amount sign</span>
            <select
              className="border border-sage-200 rounded-lg px-2 py-1.5 bg-surface"
              value={mapping.amount_sign}
              onChange={(e) => set("amount_sign", e.target.value)}
            >
              <option value="negative_is_debit">Negative = money out (bank)</option>
              <option value="negative_is_credit">Negative = money in (credit card)</option>
            </select>
          </label>
        )}
      </div>

      <p className="text-xs text-ink-500">
        {parsed.length} of {table.rows.length} rows read with this mapping.
      </p>

      <div className="flex gap-3">
        <button onClick={onCancel} className="btn-ghost flex-1 text-sm py-2">Cancel</button>
        <button
          onClick={() => onConfirm(mapping, parsed)}
          disabled={!valid}
          className="btn-primary flex-1 text-sm py-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Use this mapping
        </button>
      </div>
    </div>
  );
}
