// UPI app statement parsers (text extracted from the PDF).
// Google Pay is a port of backend/tests/reference/upi_statement_parser.py
// (same regex, same date formats, same direction rules). PhonePe and Paytm
// are new; see the block parser below.
import { parseDate, formatDate, strptime } from "./strptime.js";
import { toAmountString } from "./banks.js";

export const UPI_SOURCES = {
  google_pay: { source_type: "upi_google_pay", label: "Google Pay" },
  phonepe: { source_type: "upi_phonepe", label: "PhonePe" },
  paytm: { source_type: "upi_paytm", label: "Paytm" },
};

/**
 * Python `_detect_source`, same order, plus structural fallbacks for PhonePe
 * and Paytm (their exports may carry the brand only as a logo image).
 */
export function detectUpiSource(fullText) {
  const lower = fullText.toLowerCase();
  if (lower.includes("phonepe")) return "phonepe";
  if (lower.includes("paytm")) return "paytm";
  if (lower.includes("google pay") || lower.includes("googlepay")) return "google_pay";
  if (lower.includes("upi transaction id") && (lower.includes("paid to") || lower.includes("received from"))) {
    return "google_pay";
  }
  if (/transaction id/.test(lower) && /utr no/.test(lower) && /\b(debit|credit)\b/.test(lower)) return "phonepe";
  if (/upi ref no/.test(lower) && /(paid to|received from|money sent to)/.test(lower)) return "paytm";
  return null;
}

function upiAmount(raw) {
  const s = raw.replace(/,/g, "").replace(/₹/g, "").trim();
  if (!/^(\d+\.?\d*|\.\d+)$/.test(s)) return null;
  const a = toAmountString(s);
  return Number(a) > 0 ? a : null;
}

function row(sourceKey, { date, counterparty, amount, direction, reference }) {
  return {
    date,
    description_raw: counterparty,
    amount,
    direction: direction === "received" ? "credit" : "debit",
    reference: reference || null,
    source_type: UPI_SOURCES[sourceKey].source_type,
    source_label: UPI_SOURCES[sourceKey].label,
    type: direction === "self_transfer" ? "transfer" : "transaction",
  };
}

function directionOf(phrase) {
  const p = phrase.toLowerCase();
  if (p.includes("self transfer")) return "self_transfer";
  if (p.includes("paid to")) return "paid";
  return "received";
}

// ── Google Pay: direct port ────────────────────────────────────────────────
const GPAY_PATTERN = new RegExp(
  "(\\d{2}\\s+[A-Za-z]+,?\\s*\\d{4})\\n" +
  "(\\d{2}:\\d{2}\\s*[AP]M)\\n" +
  "(Paid to|Received from|Self transfer to)\\s+" +
  "(.+?)\\n" +
  "UPI Transaction ID:\\s*(\\d+)\\n" +
  "(?:Paid by|Paid to)\\s+(.+?)\\s+(\\d{3,4})\\n" +
  "₹([\\d,]+\\.?\\d*)",
  "g",
);

export function parseGooglePay(fullText) {
  const out = [];
  for (const m of fullText.matchAll(GPAY_PATTERN)) {
    const [, dateStr, timeStr, directionRaw, counterpartyRaw, utr, , , amountStr] = m;
    const amount = upiAmount(amountStr);
    if (!amount) continue;
    const dateClean = dateStr.trim().replace(/,+$/, "").replace(/\s+/g, " ");
    const timeClean = timeStr.trim().replace(/\s+/g, " ");
    const parsed = parseDate(`${dateClean} ${timeClean}`, ["%d %b %Y %I:%M %p", "%d %b, %Y %I:%M %p"]);
    if (!parsed) continue;
    out.push(row("google_pay", {
      date: formatDate(parsed, true),
      counterparty: counterpartyRaw.trim(),
      amount,
      direction: directionOf(directionRaw),
      reference: utr,
    }));
  }
  return out;
}

// ── Layout-tolerant block parser ───────────────────────────────────────────
// Splits the text at each transaction date and pulls fields out of each block
// by label, so it doesn't depend on the order the PDF emits its columns in.
// Used for PhonePe, Paytm, and as a fallback when the strict Google Pay regex
// finds nothing (e.g. pdf.js orders that layout differently from pymupdf).

const MONTH = "(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*";
const DIRECTION_RE = /(Self transfer to|Paid to|Received from|Money sent to|Money received from|Transfer(?:red)? to|Sent to|Bill paid -|Payment to)\s+([^\n]+)/i;
const TRAILING_NOISE = /\s+(?:DEBIT|CREDIT|[-+]?\s*(?:₹|INR|Rs\.?)\s*[\d,.]+).*$/i;

const LAYOUTS = {
  google_pay: {
    dateRe: new RegExp(`\\b(\\d{1,2}\\s+${MONTH},?\\s*\\d{4})\\b`, "gi"),
    dateFormats: ["%d %b %Y", "%d %b, %Y"],
    refRes: [/UPI Transaction ID:?\s*(\d+)/i],
  },
  phonepe: {
    dateRe: new RegExp(`\\b(${MONTH}\\s+\\d{1,2},?\\s*\\d{4})\\b`, "gi"),
    dateFormats: ["%b %d, %Y", "%b %d %Y"],
    refRes: [/UTR\s*No\.?\s*:?\s*(\d{6,})/i, /Transaction ID\s*:?\s*([A-Z0-9]{6,})/i],
  },
  paytm: {
    // "21 Feb" with the year coming from the statement period, or "21 Feb 2024"
    dateRe: new RegExp(`(?:^|\\n)\\s*(\\d{1,2}\\s+${MONTH}(?:,?\\s*\\d{4})?)\\b`, "gi"),
    dateFormats: ["%d %b %Y", "%d %b, %Y"],
    refRes: [/UPI Ref(?:erence)?\s*No\.?\s*:?\s*(\d{6,})/i, /Order ID\s*:?\s*([A-Z0-9]{6,})/i],
  },
};

function monthAbbr(s) {
  // strptime's %b takes 3-letter names; statements sometimes spell them out
  return s.replace(new RegExp(MONTH, "gi"), (m) => m.slice(0, 3));
}

/** Year range from a "period" line like "01 Jan 2024 - 31 Mar 2024" or "1 JAN'24 - 31 MAR'24". */
export function statementPeriod(text) {
  const re = new RegExp(`(\\d{1,2})\\s*(${MONTH})\\s*['’,]?\\s*(\\d{4}|\\d{2})\\b`, "gi");
  const found = [];
  for (const m of text.matchAll(re)) {
    const y = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
    const p = strptime(`${m[1]} ${m[2].slice(0, 3)} ${y}`, "%d %b %Y");
    if (p) found.push(p);
    if (found.length === 2) break;
  }
  return found.length === 2 ? found : null;
}

function inferYear(p, period, today) {
  const key = (y) => y * 10000 + p.month * 100 + p.day;
  if (period) {
    const [start, end] = period;
    const lo = start.year * 10000 + start.month * 100 + start.day;
    const hi = end.year * 10000 + end.month * 100 + end.day;
    for (let y = start.year; y <= end.year; y++) if (key(y) >= lo && key(y) <= hi) return y;
    return end.year;
  }
  // No period printed: assume the most recent occurrence not in the future
  const t = today.getFullYear() * 10000 + (today.getMonth() + 1) * 100 + today.getDate();
  return key(today.getFullYear()) <= t ? today.getFullYear() : today.getFullYear() - 1;
}

export function parseUpiBlocks(sourceKey, fullText, { today = new Date() } = {}) {
  const layout = LAYOUTS[sourceKey];
  const period = sourceKey === "paytm" ? statementPeriod(fullText) : null;
  const starts = [...fullText.matchAll(layout.dateRe)].map((m) => ({ index: m.index, date: m[1] }));
  const out = [];
  starts.forEach((s, i) => {
    const block = fullText.slice(s.index, i + 1 < starts.length ? starts[i + 1].index : undefined);
    const dirMatch = DIRECTION_RE.exec(block);
    if (!dirMatch) return;
    const amountMatch = /([-+])?\s*(?:₹|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)/i.exec(block);
    if (!amountMatch) return;
    const amount = upiAmount(amountMatch[2]);
    if (!amount) return;

    const yearless = !/\d{4}/.test(s.date);
    // Yearless dates are parsed against leap year 2000 so "29 Feb" validates
    const dateText = monthAbbr(s.date.replace(/\s+/g, " ")) + (yearless ? " 2000" : "");
    let parsed = parseDate(dateText, layout.dateFormats);
    if (!parsed) return;
    if (yearless) {
      parsed = strptime(`${parsed.day} ${dateText.split(" ")[1]} ${inferYear(parsed, period, today)}`, "%d %b %Y");
      if (!parsed) return;
    }
    const time = /\b(\d{1,2}:\d{2})\s*([ap]m)\b/i.exec(block);
    if (time) {
      const t = strptime(`${time[1]} ${time[2]}`, "%I:%M %p");
      if (t) Object.assign(parsed, { hour: t.hour, minute: t.minute });
    }

    let direction = directionOf(dirMatch[1]);
    if (direction !== "self_transfer" && /sent to|transfer(?:red)? to|bill paid|payment to/i.test(dirMatch[1])) direction = "paid";
    if (/money received/i.test(dirMatch[1])) direction = "received";
    const type = /\b(DEBIT|CREDIT)\b/.exec(block);
    if (type && direction !== "self_transfer") direction = type[1] === "CREDIT" ? "received" : "paid";
    if (amountMatch[1] && direction !== "self_transfer") direction = amountMatch[1] === "+" ? "received" : "paid";

    let reference = null;
    for (const re of layout.refRes) {
      const m = re.exec(block);
      if (m) { reference = m[1]; break; }
    }
    const counterparty = dirMatch[2].replace(TRAILING_NOISE, "").trim();
    if (!counterparty) return;
    out.push(row(sourceKey, {
      date: formatDate(parsed, Boolean(time)),
      counterparty,
      amount,
      direction,
      reference,
    }));
  });
  return out;
}

/** Parse a UPI statement's text. Returns {sourceKey, rows} or null if not a UPI statement. */
export function parseUpiStatement(fullText, opts) {
  const sourceKey = detectUpiSource(fullText);
  if (!sourceKey) return null;
  let rows = sourceKey === "google_pay" ? parseGooglePay(fullText) : [];
  if (!rows.length) rows = parseUpiBlocks(sourceKey, fullText, opts);
  return { sourceKey, rows };
}
