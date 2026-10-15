// Bill / receipt photo → {amount, merchant, date, payment_method, category}.
// Runs on OCR'd lines in the browser; the image never leaves the device.
import { guessCategory } from "../lib/quickAdd.js";

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const AMOUNT = /(?:₹|rs\.?|inr)?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)/gi;

// Lines that name the total, strongest first; and lines that look like a total but aren't
const TOTAL_LABELS = [
  /grand\s*total/i,
  /net\s*(?:amount|payable|total)|amount\s*payable|total\s*payable|to\s*pay|bill\s*amount|amount\s*(?:paid|due)|total\s*amount/i,
  /\btotal\b/i,
];
const NOT_TOTAL = /sub\s*-?\s*total|total\s*(?:items?|qty|quantity|savings?|discount|tax|gst|cgst|sgst)|you\s*saved/i;
const NOT_MERCHANT = /tax\s*invoice|invoice|receipt|\bbill\b|gstin|\bgst\b|\bphone|\bph\s*[:.]|\btel\b|\bmob(?:ile)?\b|\bdate\b|cash\s*memo|welcome|thank|\border\b|\btable\b|\btoken\b|\bkot\b|www\.|@/i;

const RECEIPT_WORDS = new Set(["bill", "total", "tax", "invoice", "amount", "paid", "date", "gst", "cgst", "sgst", "no", "qty"]);

const toNumber = (s) => Number(s.replace(/,/g, ""));

function amountsIn(line) {
  return [...line.matchAll(AMOUNT)]
    .filter((m) => !/^\d{4,}$/.test(m[1]) || /\./.test(m[1]) || /₹|rs|inr/i.test(m[0]))   // bare long numbers are ids/phones
    .map((m) => toNumber(m[1]))
    .filter((n) => n > 0 && n < 1e7);
}

export function findTotal(lines) {
  for (const label of TOTAL_LABELS) {
    const hits = lines.filter((l) => label.test(l) && !NOT_TOTAL.test(l)).map((l) => Math.max(0, ...amountsIn(l)));
    const best = Math.max(0, ...hits);
    if (best > 0) return best;
  }
  // No labelled total: the largest amount written with a decimal or a currency sign
  const priced = lines.flatMap((l) => [...l.matchAll(AMOUNT)].filter((m) => /\.\d{2}$/.test(m[1]) || /₹|rs|inr/i.test(m[0])).map((m) => toNumber(m[1])));
  return priced.length ? Math.max(...priced) : null;
}

export function findMerchant(lines) {
  for (const line of lines.slice(0, 6)) {
    const clean = line.replace(/[^A-Za-z&'. -]/g, " ").replace(/\s+/g, " ").trim();
    if (clean.replace(/[^A-Za-z]/g, "").length >= 3 && !NOT_MERCHANT.test(line)) {
      return clean.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 60);
    }
  }
  return null;
}

const pad = (n) => String(n).padStart(2, "0");

function validDate(y, m, d) {
  const dt = new Date(y, m - 1, d);
  return dt.getMonth() === m - 1 && dt.getDate() === d ? `${y}-${pad(m)}-${pad(d)}` : null;
}

/** Day-first dates as printed on Indian receipts. */
export function findDate(lines) {
  const text = lines.join(" ");
  const year = (y) => (y.length === 2 ? 2000 + Number(y) : Number(y));
  let m = /\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b/.exec(text);
  if (m) return validDate(year(m[3]), Number(m[2]), Number(m[1]));
  m = new RegExp(`\\b(\\d{1,2})[\\s-]*(${MONTHS.join("|")})[a-z]*[\\s,-]*(\\d{2,4})\\b`, "i").exec(text);
  if (m) return validDate(year(m[3]), MONTHS.indexOf(m[2].toLowerCase()) + 1, Number(m[1]));
  m = new RegExp(`\\b(${MONTHS.join("|")})[a-z]*\\s+(\\d{1,2}),?\\s+(\\d{4})\\b`, "i").exec(text);
  if (m) return validDate(Number(m[3]), MONTHS.indexOf(m[1].toLowerCase()) + 1, Number(m[2]));
  return null;
}

export function findPaymentMethod(lines) {
  const text = lines.join(" ");
  if (/\b(upi|gpay|google\s*pay|phonepe|paytm|bhim)\b/i.test(text)) return "online";
  if (/\b(card|visa|master\s*card|rupay|amex|credit|debit)\b/i.test(text)) return "online";
  if (/\bcash\b/i.test(text)) return "cash";
  return null;
}

/** Everything the confirm card needs, from OCR'd lines (top to bottom). */
export function extractReceipt(lines) {
  const texts = lines.map((l) => (typeof l === "string" ? l : l.text)).filter((t) => t && t.trim());
  const total = findTotal(texts);
  const merchant = findMerchant(texts);
  const wordsOf = (t) => t.toLowerCase().split(/[^a-z]+/).filter((w) => w && !RECEIPT_WORDS.has(w));
  // the merchant's name says most; then the items (receipt boilerplate like "bill" excluded)
  const category = guessCategory(wordsOf(merchant || "")) || guessCategory(wordsOf(texts.join(" ")));
  return {
    amount: total ? (Number.isInteger(total) ? String(total) : total.toFixed(2)) : null,
    merchant,
    date: findDate(texts),
    payment_method: findPaymentMethod(texts),
    category,
  };
}
