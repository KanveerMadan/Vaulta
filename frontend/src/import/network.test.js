// "Network panel" check for the import flow: drive the same functions
// StatementUpload.jsx calls (parseStatement → sanitizeRows → sendRows) with a
// recording transport, and assert that only JSON rows leave the device.
import { readFileSync, readdirSync } from "node:fs";
import { parseCsvText } from "./readers.js";
import { describe, expect, it } from "vitest";
import { parseStatement } from "./index.js";
import { sanitizeRows } from "./pii.js";
import { sendRows, saveTemplate, BATCH_SIZE } from "./submit.js";
import { applyMapping, guessMapping } from "./mapping.js";
import { fixtureFile, pdfjs } from "./testUtils.js";

const ROW_KEYS = ["amount", "date", "description_raw", "direction", "reference", "source_label", "source_type", "type"];

function recordingApi() {
  const calls = [];
  const record = (method) => async (url, body) => {
    calls.push({ method, url, body });
    return { data: { imported: body?.rows?.length ?? 0, duplicates_merged: 0, transfers_flagged: 0, rows_needing_review: 0, failed: 0 } };
  };
  return { calls, post: record("POST"), put: record("PUT"), get: record("GET") };
}

const isBinary = (v) =>
  v instanceof Blob || v instanceof ArrayBuffer || ArrayBuffer.isView(v) ||
  (typeof FormData !== "undefined" && v instanceof FormData);

function assertPlainJson(value) {
  expect(isBinary(value)).toBe(false);
  if (value && typeof value === "object") Object.values(value).forEach(assertPlainJson);
}

describe("import flow sends only JSON rows", () => {
  for (const name of ["hdfc.csv", "sbi.csv", "gpay_locked.pdf", "card_hdfc.pdf", "paytm.pdf"]) {
    it(name, async () => {
      const file = fixtureFile(name);
      const parsed = await parseStatement(file, { pdfjs, password: name === "gpay_locked.pdf" ? "RAHU0503" : undefined });
      const { rows } = sanitizeRows(parsed.rows);
      const api = recordingApi();
      await sendRows(api, rows);

      expect(api.calls.length).toBe(Math.ceil(rows.length / BATCH_SIZE));
      for (const call of api.calls) {
        expect(call).toMatchObject({ method: "POST", url: "/api/import/batch" });
        assertPlainJson(call.body);
        // rows, and a random id naming this upload (the same in every batch of the file) so it can be deleted later
        expect(Object.keys(call.body)).toEqual(["rows", "import_id"]);
        expect(call.body.import_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
        expect(call.body.import_id).toBe(api.calls[0].body.import_id);
        for (const r of call.body.rows) expect(Object.keys(r).sort()).toEqual(ROW_KEYS);
        // the body round-trips through JSON unchanged: nothing non-serializable
        expect(JSON.parse(JSON.stringify(call.body))).toEqual(call.body);
        const wire = JSON.stringify(call.body);
        expect(wire).not.toContain("Closing Balance");
        expect(wire).not.toContain("RAHU0503");
      }
    });
  }

  it("no balance ever leaves the device: only rows go, and no row carries a balance or a balance figure", async () => {
    for (const name of ["hdfc.csv", "sbi.csv", "axis.csv", "icici.csv", "kotak.csv"]) {
      const text = await fixtureFile(name).text();
      const table = parseCsvText(text);
      const header = table.find((r) => r.some((c) => /balance/i.test(c)));
      const col = header.findIndex((c) => /balance/i.test(c));
      const parsed = await parseStatement(fixtureFile(name), { pdfjs });
      expect(parsed.balance_check, name).toMatch(/^(pass|fail)$/);             // checked on the device
      const { rows } = sanitizeRows(parsed.rows);
      const api = recordingApi();
      await sendRows(api, rows);
      const wire = JSON.stringify(api.calls.map((c) => c.body));
      expect(wire).not.toMatch(/balance/i);
      const amounts = new Set(rows.map((r) => Number(r.amount).toFixed(2)));
      const balances = table.slice(table.indexOf(header) + 1).map((r) => String(r[col] ?? "").trim()).filter(Boolean)
        .filter((b) => !amounts.has(Number(b.replace(/[,\s]|Dr|Cr/gi, "")).toFixed(2)));   // unless it equals an amount
      for (const b of balances) {
        expect(wire, `${name}: ${b}`).not.toContain(b);
        expect(wire, `${name}: ${b}`).not.toContain(Number(b.replace(/[,\s]|Dr|Cr/gi, "")).toFixed(2));
      }
    }
  });

  it("password never leaves parseStatement", async () => {
    const parsed = await parseStatement(fixtureFile("gpay_locked.pdf"), { pdfjs, password: "RAHU0503" });
    expect(JSON.stringify(parsed)).not.toContain("RAHU0503");
  });

  it("column-mapping template carries indices and a date format only", async () => {
    const parsed = await parseStatement(fixtureFile("bank_hdfc.pdf"), { pdfjs });
    const mapping = guessMapping(parsed.table.header, parsed.table.rows);
    const api = recordingApi();
    await saveTemplate(api, parsed.fingerprint, { columnCount: parsed.table.header.length, sourceType: parsed.source_type, mapping });
    const [call] = api.calls;
    expect(call.url).toBe(`/api/import/templates/${parsed.fingerprint}`);
    const wire = JSON.stringify(call.body);
    for (const cell of [...parsed.table.header, ...parsed.table.rows.flat()].filter((c) => c.length > 2)) {
      expect(wire).not.toContain(cell);
    }
    expect(applyMapping(parsed.table, mapping, {}).length).toBe(3);
  });

  it("no source file in the app builds FormData or posts a file", () => {
    const src = new URL("../", import.meta.url);
    const files = readdirSync(src, { recursive: true }).filter((f) => /\.(js|jsx)$/.test(f) && !/\.test\.js$/.test(f));
    for (const f of files) {
      const code = readFileSync(new URL(f, src), "utf8");
      expect(code, f).not.toMatch(/new FormData|multipart\/form-data|statements\/upload/);
    }
  });
});
