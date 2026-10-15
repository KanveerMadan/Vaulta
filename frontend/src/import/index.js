// Statement import: file → normalized rows, entirely in the browser.
// Every parser emits rows shaped:
//   {date, description_raw, amount, direction, reference, source_type, source_label, type}
// date: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS" (local time as printed)
// amount: positive decimal string "1234.50"; direction: "debit" | "credit"
// type: "transaction" | "transfer" (own-account movement, e.g. card bill payment)
import { decodeText, parseCsvText, readSpreadsheet, loadPdfjs } from "./readers.js";
import { findBankHeader, parseBankRows, BANKS } from "./banks.js";
import { parseUpiStatement, UPI_SOURCES } from "./upi.js";
import { detectCardIssuer, parseCardStatement, ISSUERS } from "./creditCard.js";
import { extractPdf, PdfPasswordError } from "./pdfExtract.js";
import { reconstructTable, isAnyHeader } from "./table.js";
import { headerFingerprint } from "./mapping.js";

export class ImportError extends Error {}

const MAX_FILE_BYTES = 20 * 1024 * 1024;

function guessHeaderRow(table) {
  const named = (row) => row.filter((c) => String(c).trim() && !/^[\d,.\s/-]+$/.test(c)).length;
  const i = table.slice(0, 40).findIndex((row) => named(row) >= 3);
  return i >= 0 ? i : 0;
}

async function needsMapping(header, rows, source_type, format) {
  const width = header.length;
  return {
    status: "needs_mapping",
    table: { header, rows: rows.filter((r) => r.some((c) => String(c).trim())).map((r) => r.slice(0, width)) },
    fingerprint: await headerFingerprint(header),
    source_type,
    format,
  };
}

async function fromTable(table, format) {
  if (!table.length) throw new ImportError("This file has no rows.");
  const found = findBankHeader(table);
  if (found) {
    const header = table[found.headerIndex];
    const rows = parseBankRows(found.bank, header, table.slice(found.headerIndex + 1), "bank_csv");
    if (rows.length) return { status: "ok", rows, source_type: "bank_csv", source_label: BANKS[found.bank].label, format };
    return needsMapping(header, table.slice(found.headerIndex + 1), "bank_csv", format);
  }
  const h = guessHeaderRow(table);
  return needsMapping(table[h], table.slice(h + 1), "bank_csv", format);
}

async function fromPdf(buffer, password, pdfjs) {
  let pdf;
  try {
    pdf = await extractPdf(buffer, { pdfjs: pdfjs || (await loadPdfjs()), password });
  } catch (e) {
    if (e instanceof PdfPasswordError) return { status: "needs_password", incorrect: e.incorrect };
    throw new ImportError("Couldn't read this PDF. Is it a valid statement?");
  }
  if (!pdf.text.trim()) {
    throw new ImportError("No text in this PDF. Scanned or image-only statements aren't supported; download the statement again as a text PDF, CSV or Excel file.");
  }

  const issuer = detectCardIssuer(pdf.text);
  if (issuer) {
    const rows = parseCardStatement(issuer, pdf.lineTexts);
    if (rows.length) return { status: "ok", rows, source_type: "credit_card", source_label: ISSUERS[issuer].label, format: "pdf" };
  }

  const bankTable = reconstructTable(pdf.pages);
  if (bankTable) {
    const found = findBankHeader([bankTable.header]);
    const rows = found ? parseBankRows(found.bank, bankTable.header, bankTable.rows, "bank_pdf") : [];
    if (rows.length) return { status: "ok", rows, source_type: "bank_pdf", source_label: BANKS[found.bank].label, format: "pdf" };
    return needsMapping(bankTable.header, bankTable.rows, "bank_pdf", "pdf");
  }

  const upi = parseUpiStatement(pdf.text);
  if (upi?.rows.length) {
    const src = UPI_SOURCES[upi.sourceKey];
    return { status: "ok", rows: upi.rows, source_type: src.source_type, source_label: src.label, format: "pdf" };
  }

  const loose = reconstructTable(pdf.pages, isAnyHeader);
  if (loose) return needsMapping(loose.header, loose.rows, "bank_pdf", "pdf");
  throw new ImportError("We couldn't find a transaction table in this PDF.");
}

/**
 * Parse a statement File. Returns one of:
 *   {status: "ok", rows, source_type, source_label, format}
 *   {status: "needs_mapping", table: {header, rows}, fingerprint, source_type, format}
 *   {status: "needs_password", incorrect}
 * Throws ImportError with a user-facing message otherwise.
 * `password` is used only to open the PDF in memory; it is never stored or sent.
 */
export async function parseStatement(file, { password, pdfjs } = {}) {
  if (file.size > MAX_FILE_BYTES) throw new ImportError("File is too large (max 20 MB).");
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const buffer = await file.arrayBuffer();
  if (ext === "csv" || ext === "txt") return fromTable(parseCsvText(decodeText(buffer)), "csv");
  if (ext === "xls" || ext === "xlsx") return fromTable(await readSpreadsheet(buffer), ext);
  if (ext === "pdf") return fromPdf(buffer, password, pdfjs);
  throw new ImportError("Unsupported file. Use a CSV, Excel (.xls/.xlsx) or PDF statement.");
}
