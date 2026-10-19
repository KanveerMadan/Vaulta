// Column mapping for statements no parser recognizes. The user maps columns
// once; the mapping (column indices + date format, no transaction data) is
// saved server-side under a fingerprint of the header row and reused.
import { parseDate, formatDate } from "./strptime.js";
import { parseAmount, parseBalance, reconcileBalances } from "./banks.js";
import { LOW_CONFIDENCE } from "./ocr.js";

export const MAPPING_FIELDS = ["date", "description", "debit", "credit", "amount", "reference"];

export const DATE_FORMATS = [
  "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y",
  "%d %b %Y", "%d-%b-%Y", "%d %b %y", "%d-%b-%y", "%d %b, %Y",
  "%Y-%m-%d", "%m/%d/%Y",
];

const normHeader = (h) => String(h ?? "").trim().toLowerCase().replace(/\s+/g, " ");

/** SHA-256 hex of the normalized header row. */
export async function headerFingerprint(header) {
  const bytes = new TextEncoder().encode(header.map(normHeader).join("|"));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const GUESSES = {
  date: /\b(txn |tran |transaction |value )?date\b|\bdt\b/i,
  description: /narration|description|particulars|remarks|details/i,
  debit: /withdrawal|debit|\bdr\b/i,
  credit: /deposit|credit|\bcr\b/i,
  amount: /amount|amt/i,
  reference: /ref|chq|cheque|utr/i,
};

/** Best-guess mapping from header names, for pre-filling the mapping UI. */
export function guessMapping(header, sampleRows = []) {
  const names = header.map(normHeader);
  const taken = new Set();
  const mapping = {};
  for (const field of ["date", "description", "debit", "credit", "reference", "amount"]) {
    const i = names.findIndex((n, idx) => !taken.has(idx) && GUESSES[field].test(n) && !/balance/.test(n));
    mapping[field] = i >= 0 ? i : null;
    if (i >= 0) taken.add(i);
  }
  if (mapping.debit != null || mapping.credit != null) mapping.amount = null;
  mapping.date_format = guessDateFormat(sampleRows.map((r) => r[mapping.date] ?? ""));
  mapping.amount_sign = "negative_is_debit";
  return mapping;
}

/** First format that parses every non-empty sample. */
export function guessDateFormat(samples) {
  const vals = samples.map((s) => String(s).trim()).filter(Boolean).slice(0, 30);
  return DATE_FORMATS.find((f) => vals.length && vals.every((v) => parseDate(v, [f]))) || DATE_FORMATS[0];
}

/**
 * Single signed amount column. Explicit Dr/Cr suffix wins; otherwise the sign
 * decides: "negative_is_debit" (bank style: -500 is money out, 500 is money in)
 * or "negative_is_credit" (card style: 500 is a charge, -500 a refund/payment).
 */
function signedAmount(raw, amountSign) {
  const s = String(raw ?? "").trim();
  const dr = /dr\.?$/i.test(s);
  const cr = /cr\.?$/i.test(s);
  const unsuffixed = s.replace(/\s*(dr|cr)\.?$/i, "");
  const negative = /^-|-$|^\(.*\)$/.test(unsuffixed);
  const amount = parseAmount(unsuffixed.replace(/[()]/g, "").replace(/^-|-$/g, ""));
  if (!amount) return null;
  let debit;
  if (dr) debit = true;
  else if (cr) debit = false;
  else debit = amountSign === "negative_is_credit" ? !negative : negative;
  return { amount, direction: debit ? "debit" : "credit" };
}

/**
 * Apply a mapping to table rows → normalized rows. Rows without a parseable
 * date or amount are skipped. OCR'd rows below LOW_CONFIDENCE get
 * low_confidence: true (preview-only; never sent).
 */
function mapRow(r, i, rowConfidence, mapping, { source_type, source_label }) {
  const cell = (row, col) => (col == null ? "" : String(row[col] ?? "").trim());
  const parsed = parseDate(cell(r, mapping.date), [mapping.date_format]);
  const description = cell(r, mapping.description);
  if (!parsed || !description) return null;
  let value = null;
  if (mapping.debit != null || mapping.credit != null) {
    const debit = parseAmount(cell(r, mapping.debit));
    const credit = debit ? null : parseAmount(cell(r, mapping.credit));
    if (debit || credit) value = { amount: debit || credit, direction: debit ? "debit" : "credit" };
  } else if (mapping.amount != null) {
    value = signedAmount(cell(r, mapping.amount), mapping.amount_sign);
  }
  if (!value) return null;
  return {
    date: formatDate(parsed),
    description_raw: description,
    ...value,
    reference: cell(r, mapping.reference) || null,
    source_type,
    source_label,
    type: "transaction",
    ...((rowConfidence?.[i] ?? 100) < LOW_CONFIDENCE && { low_confidence: true }),
  };
}

export function applyMapping({ rows, rowConfidence }, mapping, labels) {
  return rows.map((r, i) => mapRow(r, i, rowConfidence, mapping, labels)).filter(Boolean);
}

/** The balance check (banks.js) for a mapped table, when its header has a balance column; the balance is never mapped. */
export function mappedBalanceCheck({ header, rows }, mapping) {
  const col = header.findIndex((h) => /balance/i.test(String(h ?? "")));
  if (col < 0) return null;
  const amountCols = [mapping.debit, mapping.credit, mapping.amount].filter((c) => c != null);
  return reconcileBalances(rows.map((r, i) => {
    const row = mapRow(r, i, null, mapping, {});
    const delta = row ? (row.direction === "credit" ? 1 : -1) * Math.round(Number(row.amount) * 100)
      : amountCols.some((c) => parseAmount(String(r[c] ?? "").replace(/^-/, ""))) ? null : 0;
    return { balance: parseBalance(r[col]), delta };
  }));
}
