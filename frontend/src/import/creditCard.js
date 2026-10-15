// Credit card statement PDFs: HDFC, ICICI, SBI Card, Axis.
// Works on row-major text lines (pdfExtract.js `lines`). Each issuer prints a
// transaction as one line: date at the start, amount at the end, an optional
// credit marker after the amount. Bill payments to the card are flagged as
// type "transfer" so they don't count as income or spend.
import { parseDate, formatDate } from "./strptime.js";
import { toAmountString } from "./banks.js";

const AMOUNT = "([\\d,]+\\.\\d{2})";

export const ISSUERS = {
  hdfc: {
    label: "HDFC Bank Credit Card",
    name: /hdfc\s*bank/i,
    // 12/03/2024 [14:22:05] SWIGGY BANGALORE 450.00 [Cr]
    line: new RegExp(`^(\\d{2}/\\d{2}/\\d{4})(?:\\s+\\d{2}:\\d{2}(?::\\d{2})?)?\\s+(.+?)\\s+${AMOUNT}\\s*(Cr)?$`, "i"),
    formats: ["%d/%m/%Y"],
  },
  icici: {
    label: "ICICI Bank Credit Card",
    name: /icici\s*bank/i,
    // 12/03/2024 11223344556 SWIGGY BANGALORE IN 9 450.00 [CR]
    line: new RegExp(`^(\\d{2}/\\d{2}/\\d{4})\\s+(?:(\\d{8,})\\s+)?(.+?)\\s+(?:-?\\d+\\s+)?${AMOUNT}\\s*(CR)?$`, "i"),
    refGroup: 2,
    formats: ["%d/%m/%Y"],
  },
  sbi: {
    label: "SBI Card",
    name: /sbi\s*card/i,
    // 05 Mar 24 SWIGGY BANGALORE 450.00 D|C
    line: new RegExp(`^(\\d{2}\\s+[A-Za-z]{3}\\s+\\d{2,4})\\s+(.+?)\\s+${AMOUNT}\\s*([CD])$`, "i"),
    credit: (m) => m.toUpperCase() === "C",
    formats: ["%d %b %y", "%d %b %Y"],
  },
  axis: {
    label: "Axis Bank Credit Card",
    name: /axis\s*bank/i,
    // 12/03/2024 SWIGGY BANGALORE FOOD 450.00 Dr|Cr
    line: new RegExp(`^(\\d{2}/\\d{2}/\\d{4})\\s+(.+?)\\s+${AMOUNT}\\s*(Dr|Cr)$`, "i"),
    formats: ["%d/%m/%Y"],
  },
};

// Phrases only card statements print; "credit card" alone also appears in bank statements
const CARD_STATEMENT = /minimum\s*amount\s*due|total\s*amount\s*due|payment\s*due\s*date/i;

/** Issuer key if this looks like a credit card statement, else null. SBI Card first: its statements also mention "SBI". */
export function detectCardIssuer(fullText) {
  if (!CARD_STATEMENT.test(fullText)) return null;
  for (const key of ["sbi", "hdfc", "icici", "axis"]) {
    if (ISSUERS[key].name.test(fullText)) return key;
  }
  return null;
}

/** A credit on a card statement that is the user paying their bill (not a refund). */
export function isCardBillPayment(description) {
  return /payment|paymt|pymt|thank\s*you|bbps|autopay|auto\s*debit/i.test(description)
    && !/refund|reversal|cashback|chargeback/i.test(description);
}

export function parseCardStatement(issuerKey, lines) {
  const issuer = ISSUERS[issuerKey];
  const out = [];
  for (const text of lines) {
    const m = issuer.line.exec(text.trim().replace(/\s+/g, " "));
    if (!m) continue;
    const groups = m.slice(1);
    const marker = groups[groups.length - 1];
    const amountRaw = groups[groups.length - 2];
    const description = (issuer.refGroup ? groups[issuer.refGroup] : groups[1]).trim();
    const parsed = parseDate(groups[0], issuer.formats);
    const amount = toAmountString(amountRaw.replace(/,/g, ""));
    if (!parsed || !description || !(Number(amount) > 0)) continue;
    const credit = issuer.credit ? issuer.credit(marker || "") : /^cr$/i.test(marker || "");
    out.push({
      date: formatDate(parsed),
      description_raw: description,
      amount,
      direction: credit ? "credit" : "debit",
      reference: issuer.refGroup ? groups[issuer.refGroup - 1] || null : null,
      source_type: "credit_card",
      source_label: issuer.label,
      type: credit && isCardBillPayment(description) ? "transfer" : "transaction",
    });
  }
  return out;
}
