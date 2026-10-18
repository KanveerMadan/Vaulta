// Statement import: file → normalized rows, entirely in the browser.
// Every parser emits rows shaped:
//   {date, description_raw, amount, direction, reference, source_type, source_label, type}
// date: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS" (local time as printed)
// amount: positive decimal string "1234.50"; direction: "debit" | "credit"
// type: "transaction" | "transfer" (own-account movement, e.g. card bill payment)
import { decodeText, parseCsvText, readSpreadsheet, loadPdfjs } from "./readers.js";
import { findBankHeader, parseBankRows, bankBalanceCheck, BANKS } from "./banks.js";
import { parseUpiStatement, UPI_SOURCES } from "./upi.js";
import { detectCardIssuer, parseCardStatement, ISSUERS } from "./creditCard.js";
import { extractPdf, ocrPagesResult, PdfPasswordError } from "./pdfExtract.js";
import { browserOcr, renderPageToCanvas } from "./ocr.js";
import { reconstructTable, isAnyHeader } from "./table.js";
import { headerFingerprint } from "./mapping.js";

export class ImportError extends Error {}

const MAX_FILE_BYTES = 20 * 1024 * 1024;
const IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"];

function guessHeaderRow(table) {
  const named = (row) => row.filter((c) => String(c).trim() && !/^[\d,.\s/-]+$/.test(c)).length;
  const i = table.slice(0, 40).findIndex((row) => named(row) >= 3);
  return i >= 0 ? i : 0;
}

async function needsMapping(header, rows, source_type, format, rowConfidence = null) {
  const width = header.length;
  const keep = rows.map((r) => r.some((c) => String(c).trim()));
  return {
    status: "needs_mapping",
    table: {
      header,
      rows: rows.filter((_, i) => keep[i]).map((r) => r.slice(0, width)),
      ...(rowConfidence && { rowConfidence: rowConfidence.filter((_, i) => keep[i]) }),
    },
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
    const body = table.slice(found.headerIndex + 1);
    const rows = parseBankRows(found.bank, header, body, "bank_csv");
    if (rows.length) {
      return { status: "ok", rows, source_type: "bank_csv", source_label: BANKS[found.bank].label, format,
               balance_check: bankBalanceCheck(found.bank, header, body) };
    }
    return needsMapping(header, table.slice(found.headerIndex + 1), "bank_csv", format);
  }
  const h = guessHeaderRow(table);
  return needsMapping(table[h], table.slice(h + 1), "bank_csv", format);
}

/** Lazily started OCR engine shared by a parse; `engine` may be injected (tests). */
function lazyOcr(engine) {
  let started = engine || null;
  const get = async () => (started ??= await browserOcr());
  return {
    renderPage: engine?.renderPage || renderPageToCanvas,
    recognize: async (image) => (await get()).recognize(image),
    terminate: async () => { if (started && !engine) await started.terminate(); },
  };
}

async function fromPdf(buffer, password, pdfjs, ocr) {
  let pdf;
  try {
    pdf = await extractPdf(buffer, { pdfjs: pdfjs || (await loadPdfjs()), password, ocr });
  } catch (e) {
    if (e instanceof PdfPasswordError) return { status: "needs_password", incorrect: e.incorrect };
    throw new ImportError("Couldn't read this PDF. Is it a valid statement?");
  }
  if (!pdf.text.trim()) {
    throw new ImportError("No text found in this PDF, even with text recognition. Try a clearer scan, or download the statement as a text PDF, CSV or Excel file.");
  }
  return fromExtracted(pdf, "pdf");
}

/** Text (from a PDF text layer or OCR) → rows or a table for mapping. */
async function fromExtracted(pdf, format) {
  const lineConf = pdf.ocr ? pdf.lineConfidence : null;
  const issuer = detectCardIssuer(pdf.text);
  if (issuer) {
    const rows = parseCardStatement(issuer, pdf.lineTexts, lineConf);
    if (rows.length) return { status: "ok", rows, source_type: "credit_card", source_label: ISSUERS[issuer].label, format, ocr: !!pdf.ocr };
  }

  const bankTable = reconstructTable(pdf.pages);
  if (bankTable) {
    const conf = pdf.ocr ? bankTable.rowConfidence : null;
    const found = findBankHeader([bankTable.header]);
    const rows = found ? parseBankRows(found.bank, bankTable.header, bankTable.rows, "bank_pdf", conf) : [];
    if (rows.length) return { status: "ok", rows, source_type: "bank_pdf", source_label: BANKS[found.bank].label, format, ocr: !!pdf.ocr };
    return { ...(await needsMapping(bankTable.header, bankTable.rows, "bank_pdf", format, conf)), ocr: !!pdf.ocr };
  }

  const upi = parseUpiStatement(pdf.text);
  if (upi?.rows.length) {
    const src = UPI_SOURCES[upi.sourceKey];
    return { status: "ok", rows: upi.rows, source_type: src.source_type, source_label: src.label, format, ocr: !!pdf.ocr };
  }

  const loose = reconstructTable(pdf.pages, isAnyHeader);
  if (loose) return { ...(await needsMapping(loose.header, loose.rows, "bank_pdf", format, pdf.ocr ? loose.rowConfidence : null)), ocr: !!pdf.ocr };
  throw new ImportError("We couldn't find a transaction table in this file.");
}

async function fromImage(file, ocr) {
  const items = await ocr.recognize(file);
  const result = { ...ocrPagesResult([items]), ocr: true };
  if (!result.text.trim()) throw new ImportError("No text found in this image. Try a sharper, well-lit photo of the statement.");
  return fromExtracted(result, "image");
}

/**
 * Parse a statement File. Returns one of:
 *   {status: "ok", rows, source_type, source_label, format}
 *   {status: "needs_mapping", table: {header, rows}, fingerprint, source_type, format}
 *   {status: "needs_password", incorrect}
 * Throws ImportError with a user-facing message otherwise.
 * `password` is used only to open the PDF in memory; it is never stored or sent.
 * Scanned PDFs and photos are OCR'd on the device (`ocr` injects an engine
 * {recognize, renderPage} for tests); results then carry ocr: true and rows
 * read with low confidence carry low_confidence: true.
 */
export async function parseStatement(file, { password, pdfjs, ocr: engine } = {}) {
  if (file.size > MAX_FILE_BYTES) throw new ImportError("File is too large (max 20 MB).");
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (ext === "csv" || ext === "txt") return fromTable(parseCsvText(decodeText(await file.arrayBuffer())), "csv");
  if (ext === "xls" || ext === "xlsx") return fromTable(await readSpreadsheet(await file.arrayBuffer()), ext);
  if (ext !== "pdf" && !IMAGE_TYPES.includes(ext)) {
    throw new ImportError("Unsupported file. Use a CSV, Excel (.xls/.xlsx), PDF, or a photo (JPG/PNG) of a statement.");
  }
  const ocr = lazyOcr(engine);
  try {
    return ext === "pdf" ? await fromPdf(await file.arrayBuffer(), password, pdfjs, ocr) : await fromImage(file, ocr);
  } finally {
    await ocr.terminate();
  }
}
