// Parity with the Python reference parsers (backend/tests/reference/).
// fixtures/statements/expected.json is produced by those parsers from the
// same input files; backend/tests/test_reference_parsers.py checks the
// Python side against the same file.
import { describe, expect, it } from "vitest";
import { parseStatement } from "./index.js";
import { parseGooglePay } from "./upi.js";
import { fixtureFile, expected, pick, pdfjs } from "./testUtils.js";

describe("bank CSV parity with csv_parser.py", () => {
  for (const name of ["hdfc.csv", "icici.csv", "sbi.csv", "axis.csv", "kotak.csv"]) {
    it(name, async () => {
      const result = await parseStatement(fixtureFile(name));
      expect(result.status).toBe("ok");
      const debits = result.rows
        .filter((r) => r.direction === "debit")
        .map((r) => pick(r, ["date", "description_raw", "amount", "direction"]));
      expect(debits).toEqual(expected[name]);
    });
  }
});

describe("Google Pay parity with upi_statement_parser.py", () => {
  const keys = ["date", "description_raw", "amount", "direction", "reference", "type"];

  it("same rows from the same PDF", async () => {
    const result = await parseStatement(fixtureFile("gpay.pdf"), { pdfjs });
    expect(result).toMatchObject({ status: "ok", source_type: "upi_google_pay" });
    expect(result.rows.map((r) => pick(r, keys))).toEqual(expected["gpay.pdf"]);
  });

  it("same regex on pymupdf-style text", () => {
    const text = [
      "04 May, 2026", "05:23 AM", "Paid to ZEPTO MARKETPLACE PRIVATE LIMITED",
      "UPI Transaction ID: 612456562367", "Paid by IndusInd Bank 8250", "₹129",
    ].join("\n");
    expect(parseGooglePay(text).map((r) => pick(r, keys))).toEqual([expected["gpay.pdf"][0]]);
  });

  it("password-protected PDF is decrypted in memory", async () => {
    const file = fixtureFile("gpay_locked.pdf");
    expect(await parseStatement(file, { pdfjs })).toEqual({ status: "needs_password", incorrect: false });
    expect(await parseStatement(file, { pdfjs, password: "wrong" })).toEqual({ status: "needs_password", incorrect: true });
    const result = await parseStatement(file, { pdfjs, password: "RAHU0503" });
    expect(result.rows.map((r) => pick(r, keys))).toEqual(expected["gpay.pdf"]);
  });
});
