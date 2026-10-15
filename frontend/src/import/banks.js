// Bank statement table parsers (CSV / XLS / XLSX / reconstructed PDF tables).
// Port of backend/tests/reference/csv_parser.py — header detection, column
// picks, date formats and amount rules are the same. Differences, on purpose:
//   - credits are emitted too (the Python version dropped them)
//   - header names are matched trimmed (Python's DictReader kept padding,
//     which silently dropped every row when a bank padded its headers)
//   - the header row may appear below preamble rows (XLS exports have them)
import { parseDate, formatDate } from "./strptime.js";
import { LOW_CONFIDENCE } from "./ocr.js";

/** Python `_parse_amount`: positive amount as "1234.50", or null. */
export function parseAmount(raw) {
  if (raw == null) return null;
  let s = String(raw).trim();
  if (!s) return null;
  s = s.replace(/[,\s₹$]/g, "").replace(/(Dr|Cr)$/i, "").trim();
  if (!/^[+-]?(\d+\.?\d*|\.\d+)$/.test(s)) return null;
  const amount = toAmountString(s.replace(/^\+/, ""));
  return amount && Number(amount) > 0 ? amount : null;
}

/** Normalize a non-negative decimal string to exactly 2 places. */
export function toAmountString(s) {
  if (s.startsWith("-")) return null;
  let [int, frac = ""] = s.split(".");
  int = int.replace(/^0+(?=\d)/, "") || "0";
  if (frac.length > 2) return Number(`${int}.${frac}`).toFixed(2); // ponytail: float rounding for >2dp, never seen in bank exports
  return `${int}.${frac.padEnd(2, "0")}`;
}

const lc = (h) => String(h ?? "").toLowerCase().trim();

export const BANKS = {
  hdfc: {
    label: "HDFC Bank",
    detect: ["narration", "debit amount", "credit amount", "closing balance"],
    date: "Date", description: "Narration", debit: "Debit Amount", credit: "Credit Amount",
    reference: "Chq/Ref Number",
    formats: ["%d/%m/%y", "%d/%m/%Y"],
  },
  icici: {
    label: "ICICI Bank",
    detect: ["transaction remarks", "withdrawal amount (inr )", "deposit amount (inr )"],
    date: "Transaction Date", dateFallback: "Value Date", description: "Transaction Remarks",
    debitContains: "withdrawal", creditContains: "deposit", reference: "Cheque Number",
    formats: ["%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"],
  },
  sbi: {
    label: "SBI",
    detect: ["txn date", "description", "ref no./cheque no.", "debit", "credit", "balance"],
    date: "Txn Date", description: "Description", debit: "Debit", credit: "Credit",
    reference: "Ref No./Cheque No.",
    formats: ["%d %b %Y", "%d/%m/%Y", "%d-%m-%Y"],
  },
  axis: {
    label: "Axis Bank",
    detect: ["tran date", "particulars", "debit", "credit", "balance"],
    date: "Tran Date", description: "Particulars", debit: "Debit", credit: "Credit",
    reference: "Chq No",
    formats: ["%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"],
  },
  kotak: {
    label: "Kotak Mahindra Bank",
    detect: ["transaction date", "description", "chq/ref number", "debit", "credit", "balance"],
    date: "Transaction Date", description: "Description", debit: "Debit", credit: "Credit",
    reference: "Chq/Ref Number",
    formats: ["%d-%m-%yyyy", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"],
  },
};

/** Python `_detect_bank`: same header subsets, same order. Returns a BANKS key or null. */
export function detectBank(headerRow) {
  const headers = new Set(headerRow.map(lc));
  for (const [key, bank] of Object.entries(BANKS)) {
    if (bank.detect.every((h) => headers.has(h))) return key;
  }
  return null;
}

/** First row (within the first 40) that a bank's header set matches. */
export function findBankHeader(table) {
  for (let i = 0; i < Math.min(table.length, 40); i++) {
    const bank = detectBank(table[i]);
    if (bank) return { bank, headerIndex: i };
  }
  return null;
}

/**
 * Parse data rows for a detected bank. `header` and `rows` are arrays of cells.
 * Rows that fail (no date, no description, unparseable date, no amount) are
 * skipped, like the Python per-row try/except.
 */
export function parseBankRows(bankKey, header, rows, sourceType = "bank_csv", rowConfidence = null) {
  const bank = BANKS[bankKey];
  const names = header.map((h) => String(h ?? "").trim());
  const out = [];
  for (const [i, cells] of rows.entries()) {
    const row = {};
    names.forEach((name, i) => { row[name] = cells[i] == null ? "" : String(cells[i]); });
    const get = (name) => (name in row ? row[name] : "");
    const findKey = (needle) => names.find((k) => k.toLowerCase().includes(needle));

    const dateStr = (bank.dateFallback && !(bank.date in row) ? get(bank.dateFallback) : get(bank.date)).trim();
    if (!dateStr) continue;
    const description = get(bank.description).trim();
    if (!description) continue;

    const debitKey = bank.debitContains ? findKey(bank.debitContains) : bank.debit;
    if (!debitKey) continue;
    const creditKey = bank.creditContains ? findKey(bank.creditContains) : bank.credit;

    const debit = parseAmount(get(debitKey));
    const credit = debit ? null : parseAmount(creditKey ? get(creditKey) : "");
    if (!debit && !credit) continue;

    const parsed = parseDate(dateStr, bank.formats);
    if (!parsed) continue;

    out.push({
      date: formatDate(parsed),
      description_raw: description,
      amount: debit || credit,
      direction: debit ? "debit" : "credit",
      reference: get(bank.reference).trim() || null,
      source_type: sourceType,
      source_label: bank.label,
      type: "transaction",
      ...((rowConfidence?.[i] ?? 100) < LOW_CONFIDENCE && { low_confidence: true }),
    });
  }
  return out;
}
