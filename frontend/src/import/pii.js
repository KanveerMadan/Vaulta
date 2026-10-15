// PII stripping, in the browser, before anything is sent.
//
// Parsers already emit only the eight row fields, so account numbers in
// headers, customer name, address, running balance and header/footer rows
// are never read into a row. What remains is personal data embedded in the
// description and reference text, handled here:
//   - personal UPI IDs  → "R***@okaxis"
//   - phone numbers     → "XXXXXXXX10" (last 2 digits kept)
//   - IFSC codes        → removed
//   - 9+ digit runs     → "XXXX" (account / card / long reference numbers)
//   - references        → kept only if they look like a transaction id
//   - the account holder's own name, as a whole name only → "SELF"
//     (display name from Firebase, passed in memory only; never stored)
//
// Merchant (business) VPAs are kept, minus long digit runs: the dedup engine
// (backend dedup_matcher.py) never receives a VPA from any import path; it
// matches on UTR (sent as `reference`) and on alphabetic counterparty tokens,
// so merchant words like "swiggy" in "swiggy.rzp@axisbank" are what matter.

const BUSINESS_VPA_TOKENS = [
  // payment gateways / merchant QR
  "paytmqr", "bharatpe", "razorpay", "rzp", "cashfree", "payu", "billdesk", "pinelabs", "mswipe",
  "instamojo", "ccavenue", "juspay", "easebuzz", "merchant", "phonepemerchant", "gpaymerchant",
  // large merchants that collect on their own VPA
  "swiggy", "zomato", "zepto", "blinkit", "bigbasket", "amazon", "amazonpay", "flipkart", "myntra",
  "irctc", "uber", "ola", "rapido", "airtel", "jio", "netflix", "spotify", "bookmyshow", "dmart",
  "nykaa", "meesho", "dunzo", "tataplay", "bescom", "lic",
];

// "-" is excluded from the local part: it is the field separator in bank narrations
const VPA = /([a-zA-Z0-9._]{2,256})@([a-zA-Z][a-zA-Z0-9.]{1,64})/g;
const PHONE = /(?<![\dX])(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)/g;
const IFSC = /\b[A-Z]{4}0[A-Z0-9]{6}\b/g;
const LONG_DIGITS = /\d{9,}/g;
const UTR_IN_UPI = /(?<!\d)(\d{12})(?!\d)/;

export function isBusinessVpa(vpa) {
  const tokens = vpa.toLowerCase().split(/[.\-_@]/);
  return tokens.some((t) => BUSINESS_VPA_TOKENS.some((b) => t === b || (b.length >= 5 && t.startsWith(b))));
}

export function maskVpa(local, handle) {
  const first = /[a-z]/i.test(local[0]) ? local[0].toUpperCase() : "X";
  return `${first}***@${handle}`;
}

/** Keep a reference only if it looks like a transaction id, not an account number. */
export function cleanReference(ref) {
  if (!ref) return null;
  const s = String(ref).trim();
  if (!/^[A-Za-z0-9/-]{3,40}$/.test(s)) return null; // free text like "TRANSFER TO 4897…"
  const numeric = /^(?:[A-Za-z]{2,5}[-/]?)?0*(\d+)$/.exec(s); // "0000412…", "UPI-4165…", "123456"
  if (!numeric) return s; // alphanumeric transaction ids: T2406…, N1234…
  const digits = numeric[1];
  if (digits.length === 12) return digits; // UTR / RRN (banks zero-pad or prefix it)
  if (digits.length <= 8) return s; // cheque / short serial
  return /[A-Za-z]/.test(s) ? s : null; // bare 9–11 or 13+ digits could be an account number
}

/**
 * Regex for the holder's own name, matched only as a whole name, never a
 * first or last name on its own (a payee who shares your first name is
 * someone else):
 *   - first + last, either order, optional middle names/initials between
 *     ("RAHUL SHARMA", "SHARMA RAHUL", "RAHUL K SHARMA", "RAHUL KUMAR SHARMA")
 *   - first initial + last, either order ("R SHARMA", "R. SHARMA", "SHARMA R")
 * Single-word display names match nothing.
 */
export function holderNamePattern(displayName) {
  const tokens = String(displayName || "").split(/\s+/).filter((t) => /^\p{L}{2,}$/u.test(t));
  if (tokens.length < 2) return null;
  const first = tokens[0];
  const last = tokens[tokens.length - 1];
  const initial = first[0];
  const between = "(?:\\s+\\p{L}+\\.?){0,2}\\s+";   // up to two middle names or initials
  const alternatives = [
    `${first}${between}${last}`,
    `${last}${between}${first}`,
    `${first}\\s+${last}`,
    `${last}\\s+${first}`,
    `${initial}(?:\\.\\s*|\\s+)${last}`,
    `${last}\\s+${initial}\\.?`,
  ];
  return new RegExp(`(?<!\\p{L})(?:${alternatives.join("|")})(?!\\p{L})`, "giu");
}

export function sanitizeDescription(text, counts = {}, namePattern = null) {
  const bump = (k) => { counts[k] = (counts[k] || 0) + 1; };
  let s = String(text ?? "");
  if (namePattern) {
    const before = s;
    s = s.replace(namePattern, "SELF").replace(/\bSELF(?:\s+SELF)+\b/g, "SELF");
    if (s !== before) bump("holder_name");
  }
  s = s.replace(VPA, (m, local, handle) => {
    if (isBusinessVpa(m)) return m;
    bump("upi_ids");
    return maskVpa(local, handle);
  });
  s = s.replace(PHONE, (m, number) => { bump("phone_numbers"); return `XXXXXXXX${number.slice(-2)}`; });
  s = s.replace(IFSC, () => { bump("ifsc_codes"); return ""; });
  s = s.replace(LONG_DIGITS, () => { bump("account_numbers"); return "XXXX"; });
  return s.replace(/[-/][\s/-]*(?=[-/])/g, "").replace(/\s+/g, " ").trim().slice(0, 200);
}

/**
 * Sanitize parsed rows. Returns {rows, removed, lowConfidence}: rows contain
 * exactly the fields sent to the server; removed counts what was masked or
 * dropped; lowConfidence holds indices of OCR'd rows the user should check.
 */
export function sanitizeRows(rows, { holderName } = {}) {
  const removed = {};
  const namePattern = holderNamePattern(holderName);
  const out = rows.map((r) => {
    let reference = cleanReference(r.reference);
    if (r.reference && !reference) removed.references = (removed.references || 0) + 1;
    if (!reference && /\bUPI\b|UPI[/-]/i.test(r.description_raw)) {
      reference = UTR_IN_UPI.exec(r.description_raw)?.[1] ?? null;
    }
    return {
      date: r.date,
      description_raw: sanitizeDescription(r.description_raw, removed, namePattern) || "Unknown",
      amount: r.amount,
      direction: r.direction,
      reference,
      source_type: r.source_type,
      source_label: r.source_label,
      type: r.type,
    };
  });
  const lowConfidence = new Set(rows.flatMap((r, i) => (r.low_confidence ? [i] : [])));
  return { rows: out, removed, lowConfidence };
}

/** Labels for the "Show what was removed" toggle. */
export const NEVER_READ = [
  "Account number and customer ID",
  "Account holder name and address",
  "IFSC and branch details from the statement header",
  "Running balance column",
  "Statement header, summary and footer rows",
];

export const REMOVED_LABELS = {
  holder_name: "Your own name replaced with SELF",
  upi_ids: "Personal UPI IDs masked",
  phone_numbers: "Phone numbers masked",
  ifsc_codes: "IFSC codes removed from descriptions",
  account_numbers: "Account / card numbers removed from descriptions",
  references: "Reference fields dropped (looked like account numbers or free text)",
};
