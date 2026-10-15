import { describe, expect, it } from "vitest";
import { cleanReference, sanitizeDescription, sanitizeRows } from "./pii.js";
import { parseStatement } from "./index.js";
import { applyMapping, guessMapping } from "./mapping.js";
import { fixtureFile, pdfjs } from "./testUtils.js";

describe("sanitizeDescription", () => {
  const cases = [
    // personal UPI ID masked, merchant words kept
    ["UPI-RAHUL SHARMA-rahul.s@okaxis-HDFC0001234-412398765432-Sent", "UPI-RAHUL SHARMA-R***@okaxis-XXXX-Sent"],
    // merchant VPA kept (gateway token), IFSC removed, UTR digits removed
    ["UPI-SWIGGY-swiggy.rzp@axisbank-UTIB0000100-412345678901-Payment", "UPI-SWIGGY-swiggy.rzp@axisbank-XXXX-Payment"],
    // phone-number VPA is personal
    ["UPI/412300002222/Paid to Priya/9123456789@ybl/Yes Bank", "UPI/XXXX/Paid to Priya/X***@ybl/Yes Bank"],
    // merchant QR VPA kept, but its long digit run is not
    ["UPI/paytmqr2810050501011xyz@paytm/Tea stall", "UPI/paytmqrXXXXxyz@paytm/Tea stall"],
    // bare phone number: last 2 digits kept
    ["IMPS/P2A/415333330000/9988776655/MOM", "IMPS/P2A/XXXX/XXXXXXXX55/MOM"],
    ["Recharge for +91 98765 43210", "Recharge for +91 98765 43210"], // spaced numbers aren't 9+ digit runs or phones
    ["Recharge for +91-9876543210", "Recharge for XXXXXXXX10"],
    // account numbers
    ["NEFT CR-ACME CORP PAYROLL-50100123456789", "NEFT CR-ACME CORP PAYROLL-XXXX"],
    ["NACH/LIC OF INDIA/POLICY 123456789", "NACH/LIC OF INDIA/POLICY XXXX"],
    // already-masked card numbers are left alone
    ["POS 512345XXXXXX6789 DMART AVENUE", "POS 512345XXXXXX6789 DMART AVENUE"],
    ["Paid to amit.k@oksbi", "Paid to A***@oksbi"],
  ];
  it.each(cases)("%s", (input, output) => {
    expect(sanitizeDescription(input)).toBe(output);
  });

  it("counts what it removed", () => {
    const counts = {};
    sanitizeDescription("UPI-A-a.b@okaxis-HDFC0001234-412398765432-9876543210", counts);
    expect(counts).toEqual({ upi_ids: 1, phone_numbers: 1, ifsc_codes: 1, account_numbers: 1 });
  });
});

describe("cleanReference", () => {
  it.each([
    ["0000412345678901", "412345678901"], // zero-padded RRN → UTR
    ["UPI-416511112222", "416511112222"],
    ["612456562367", "612456562367"],
    ["T2406030815123456789", "T2406030815123456789"],
    ["N123456789", "N123456789"],
    ["123456", "123456"],
    ["4897691162091", null], // 13 digits: possible account number
    ["50100123456789", null],
    ["TRANSFER TO 4897691162091", null],
    ["", null],
  ])("%s → %s", (input, output) => expect(cleanReference(input)).toBe(output));
});

describe("no fixture PII survives sanitizing", () => {
  const PII = [
    "50100123456789", "4897691162091", "4897691162092", "9876543210", "9123456789", "9988776655", "9812345678",
    "9876501234", "rahul.s@okaxis", "amitk@oksbi", "kavya.r@okhdfcbank", "HDFC0001234", "UTIB0000100",
    "MR RAHUL SHARMA", "MG Road", "Bengaluru 560001", "1,23,456.78", "48,377.00", "4321 XXXX XXXX 9876",
  ];
  const files = [
    "hdfc.csv", "icici.csv", "sbi.csv", "axis.csv", "kotak.csv", "gpay.pdf", "phonepe.pdf", "paytm.pdf",
    "card_hdfc.pdf", "card_icici.pdf", "card_sbi.pdf", "card_axis.pdf", "bank_hdfc.pdf",
  ];
  it.each(files)("%s", async (name) => {
    const parsed = await parseStatement(fixtureFile(name), { pdfjs });
    const rows = parsed.status === "ok"
      ? parsed.rows
      : applyMapping(parsed.table, guessMapping(parsed.table.header, parsed.table.rows), { source_type: "bank_pdf", source_label: "x" });
    expect(rows.length).toBeGreaterThan(0);
    const { rows: clean } = sanitizeRows(rows);
    const sent = JSON.stringify(clean);
    for (const value of PII) expect(sent).not.toContain(value);
    for (const r of clean) {
      expect(Object.keys(r).sort()).toEqual(
        ["amount", "date", "description_raw", "direction", "reference", "source_label", "source_type", "type"],
      );
      expect(r.description_raw).not.toMatch(/\d{9,}/);
    }
  });

  it("moves the UTR out of a UPI narration into reference", () => {
    const { rows } = sanitizeRows([{
      date: "2024-03-05", description_raw: "UPI-SWIGGY-swiggy.rzp@axisbank-UTIB0000100-412345678901-Payment",
      amount: "450.00", direction: "debit", reference: null, source_type: "bank_csv", source_label: "HDFC Bank", type: "transaction",
    }]);
    expect(rows[0].reference).toBe("412345678901");
  });
});
