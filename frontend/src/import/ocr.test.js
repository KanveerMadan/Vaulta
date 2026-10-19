// OCR path: real tesseract.js on the synthetic scans (fixtures/statements/
// bank_hdfc_photo.png and bank_hdfc_scanned.pdf, rendered from bank_hdfc.pdf).
// In the browser a scanned PDF page is rendered to a canvas; here the
// renderer is injected and returns the same page as a PNG.
import { Buffer } from "node:buffer";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createWorker } from "tesseract.js";
import { parseStatement } from "./index.js";
import { applyMapping, guessMapping } from "./mapping.js";
import { browserOcr, createOcr, LOW_CONFIDENCE, OCR_ASSETS } from "./ocr.js";
import { OCR_FILES } from "../../scripts/copy-ocr-assets.mjs";
import { ocrPagesResult } from "./pdfExtract.js";
import { reconstructTable } from "./table.js";
import { sanitizeRows } from "./pii.js";
import { extractReceipt } from "./receipt.js";
import { fixtureFile, pdfjs } from "./testUtils.js";

const LANG = fileURLToPath(new URL("../../node_modules/@tesseract.js-data/eng/4.0.0_best_int", import.meta.url));
const PHOTO = readFileSync(new URL("../../../fixtures/statements/bank_hdfc_photo.png", import.meta.url));
let engine;

beforeAll(async () => {
  const base = await createOcr(createWorker, { langPath: LANG, gzip: true, cacheMethod: "none" });
  engine = {
    recognize: async (image) => base.recognize(image instanceof Blob ? Buffer.from(await image.arrayBuffer()) : image),
    renderPage: async () => PHOTO,
    terminate: () => base.terminate(),
  };
}, 60000);
afterAll(() => engine?.terminate());

function expectBankTable(result) {
  expect(result).toMatchObject({ status: "needs_mapping", source_type: "bank_pdf", ocr: true });
  expect(result.table.header).toHaveLength(6);
  expect(result.table.rows).toHaveLength(3);
  expect(result.table.rowConfidence).toHaveLength(3);
  const rows = applyMapping(result.table, guessMapping(result.table.header, result.table.rows), { source_type: "bank_pdf", source_label: "HDFC" });
  expect(rows.map((r) => [r.date, r.amount, r.direction])).toEqual([
    ["2024-08-01", "623.00", "debit"], ["2024-08-02", "85000.00", "credit"], ["2024-08-03", "1050.00", "debit"],
  ]);
  // PII on the scan is stripped exactly as for text statements
  const sent = JSON.stringify(sanitizeRows(rows, { holderName: "Rahul Sharma" }).rows);
  for (const value of ["50100123456789", "HDFC0001234", "9812345678", "MG Road", "48,377.00"]) expect(sent).not.toContain(value);
}

describe("OCR", () => {
  it("photo of a statement → table for mapping", async () => {
    expectBankTable(await parseStatement(new File([PHOTO], "statement.png"), { ocr: engine }));
  }, 60000);

  it("image-only PDF → rendered, OCR'd, same table", async () => {
    expectBankTable(await parseStatement(fixtureFile("bank_hdfc_scanned.pdf"), { pdfjs, ocr: engine }));
  }, 60000);

  it("receipt photo → amount, merchant, date (web quick capture)", async () => {
    const photo = readFileSync(new URL("../../../fixtures/statements/receipt_photo.png", import.meta.url));
    const { lineTexts } = ocrPagesResult([await engine.recognize(photo)]);
    expect(extractReceipt(lineTexts)).toEqual({
      amount: "280.36", merchant: "Reliance Fresh", date: "2024-03-14", payment_method: "online", category: "Groceries",
    });
  }, 60000);

  it("text PDFs never touch OCR", async () => {
    const untouched = { recognize: () => { throw new Error("OCR used"); }, renderPage: () => { throw new Error("OCR used"); } };
    expect((await parseStatement(fixtureFile("gpay.pdf"), { pdfjs, ocr: untouched })).status).toBe("ok");
  });

  it("low-confidence words flag their row for review (never sent)", () => {
    const word = (str, x, y, conf = 95) => ({ str, x, y, w: str.length * 6, h: 10, conf });
    const items = [
      word("Date", 0, 100), word("Narration", 80, 100), word("Debit", 300, 100), word("Credit", 380, 100), word("Balance", 460, 100),
      word("01/08/24", 0, 80), word("SWIGGY", 80, 80), word("450.00", 300, 80), word("9,000.00", 460, 80),
      word("02/08/24", 0, 60), word("ZOMATO", 80, 60, LOW_CONFIDENCE - 1), word("3l2.00", 300, 60, 40), word("8,688.00", 460, 60),
    ];
    const table = reconstructTable(ocrPagesResult([items]).pages);
    const rows = applyMapping(table, guessMapping(table.header, table.rows), { source_type: "bank_pdf", source_label: "x" });
    expect(rows.map((r) => !!r.low_confidence)).toEqual([false]);   // "3l2.00" isn't an amount → row skipped
    const both = applyMapping({ ...table, rows: [table.rows[0], ["02/08/24", "ZOMATO", "312.00", "", "8,688.00"]] },
      guessMapping(table.header, table.rows), { source_type: "bank_pdf", source_label: "x" });
    expect(both.map((r) => !!r.low_confidence)).toEqual([false, true]);
    const { rows: wire, lowConfidence } = sanitizeRows(both);
    expect([...lowConfidence]).toEqual([1]);
    expect(Object.keys(wire[1])).not.toContain("low_confidence");
  });
});

describe("OCR assets are self-hosted", () => {
  const offOrigin = (v) => typeof v === "string" && /^(https?:)?\/\//i.test(v);

  it("tesseract is configured with same-origin paths only", async () => {
    let seen;
    await browserOcr(async (lang, oem, options) => {
      seen = { lang, oem, options };
      return { recognize: async () => ({ data: { blocks: [] } }), terminate: async () => {} };
    });
    expect(seen.options).toEqual(OCR_ASSETS);
    for (const key of ["workerPath", "corePath", "langPath"]) {
      expect(seen.options[key].startsWith("/")).toBe(true);
      expect(offOrigin(seen.options[key])).toBe(false);
    }
    expect(seen.options.workerBlobURL).toBe(false);
    expect(Object.values(seen.options).some(offOrigin)).toBe(false);
  });

  it("every asset tesseract will request is copied into public/ocr", () => {
    const served = Object.keys(OCR_FILES).map((f) => `/ocr/${f}`);
    expect(served).toContain(OCR_ASSETS.workerPath);
    expect(served).toContain(`${OCR_ASSETS.langPath}/eng.traineddata.gz`);
    // OEM 1 (LSTM) → the worker picks one of these two by SIMD support
    expect(served).toContain(`${OCR_ASSETS.corePath}/tesseract-core-lstm.wasm.js`);
    expect(served).toContain(`${OCR_ASSETS.corePath}/tesseract-core-simd-lstm.wasm.js`);
    for (const src of Object.values(OCR_FILES)) {
      expect(existsSync(new URL(`../../node_modules/${src}`, import.meta.url))).toBe(true);
    }
  });
});
