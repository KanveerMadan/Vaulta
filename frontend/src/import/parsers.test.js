// Behaviour beyond the Python reference: credits, XLSX, bank PDF tables,
// PhonePe, Paytm, credit cards, column mapping. The PDFs are synthetic
// (fixtures/statements/make_fixtures.py) — real exports may differ.
import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { parseStatement } from "./index.js";
import { parseGooglePay, parseUpiBlocks } from "./upi.js";
import { extractPdf } from "./pdfExtract.js";
import { applyMapping, guessMapping, headerFingerprint } from "./mapping.js";
import { strptime } from "./strptime.js";
import { fixtureFile, pick, pdfjs } from "./testUtils.js";

const KEYS = ["date", "description_raw", "amount", "direction", "reference", "type"];
const rowsOf = async (name) => (await parseStatement(fixtureFile(name), { pdfjs })).rows.map((r) => pick(r, KEYS));

describe("strptime matches Python semantics", () => {
  it("handles 1-digit fields, %y pivot, case-insensitive %b, invalid dates", () => {
    expect(strptime("5/3/24", "%d/%m/%y")).toMatchObject({ year: 2024, month: 3, day: 5 });
    expect(strptime("01/01/69", "%d/%m/%y").year).toBe(1969);
    expect(strptime("05 MAR 2024", "%d %b %Y").month).toBe(3);
    expect(strptime("31/02/2024", "%d/%m/%Y")).toBeNull();
    expect(strptime("05-03-2024", "%d-%m-%yyyy")).toBeNull(); // Kotak's first format never matches, as in Python
    expect(strptime("05 Mar 2024 09:10 PM", "%d %b %Y %I:%M %p")).toMatchObject({ hour: 21, minute: 10 });
  });
});

describe("bank tables", () => {
  it("emits credits as well as debits", async () => {
    const rows = await rowsOf("hdfc.csv");
    expect(rows.find((r) => r.direction === "credit")).toEqual({
      date: "2024-03-07", description_raw: "NEFT CR-ACME CORP PAYROLL-50100123456789",
      amount: "85000.00", direction: "credit", reference: "N123456789", type: "transaction",
    });
  });

  it("reads XLSX with preamble rows and real date cells", async () => {
    const ws = XLSX.utils.aoa_to_sheet([
      ["Kotak Mahindra Bank"], ["Account No", "1234567890"], [],
      ["Sl. No.", "Transaction Date", "Value Date", "Description", "Chq/Ref Number", "Debit", "Credit", "Balance"],
      [1, new Date(Date.UTC(2024, 6, 5)), "", "UPI/ZEPTO/416511112222/Grocery", "UPI-1", 382, "", 20618],
      [2, new Date(Date.UTC(2024, 6, 6)), "", "UPI/SANJAY/416522223333/Split", "UPI-2", "", 450.5, 21068.5],
    ], { cellDates: true });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Statement");
    const file = new File([XLSX.write(wb, { type: "array", bookType: "xlsx" })], "kotak.xlsx");
    const result = await parseStatement(file);
    expect(result).toMatchObject({ status: "ok", source_label: "Kotak Mahindra Bank", format: "xlsx" });
    expect(result.rows.map((r) => pick(r, ["date", "amount", "direction"]))).toEqual([
      { date: "2024-07-05", amount: "382.00", direction: "debit" },
      { date: "2024-07-06", amount: "450.50", direction: "credit" },
    ]);
  });

  it("unknown CSV layout asks for column mapping, and the mapping parses it", async () => {
    const csv = "Statement for A/C XXXX1234\n\nPosting Date,Details,Amount,Ref\n03-02-2024,UPI/CHAI POINT,-60.00,R1\n04-02-2024,REFUND FLIPKART,250.00,R2\n";
    const result = await parseStatement(new File([csv], "other.csv"));
    expect(result.status).toBe("needs_mapping");
    expect(result.table.header).toEqual(["Posting Date", "Details", "Amount", "Ref"]);
    expect(result.fingerprint).toBe(await headerFingerprint([" posting date", "DETAILS", "Amount", "Ref "]));
    const mapping = guessMapping(result.table.header, result.table.rows);
    expect(mapping).toMatchObject({ date: 0, description: 1, amount: 2, reference: 3, debit: null, credit: null, date_format: "%d-%m-%Y" });
    const rows = applyMapping(result.table, mapping, { source_type: "bank_csv", source_label: "Other" });
    expect(rows.map((r) => pick(r, ["date", "amount", "direction", "reference"]))).toEqual([
      { date: "2024-02-03", amount: "60.00", direction: "debit", reference: "R1" },
      { date: "2024-02-04", amount: "250.00", direction: "credit", reference: "R2" },
    ]);
  });

  it("signed amounts: Dr/Cr suffix wins, else the chosen sign convention", () => {
    const table = { rows: [["01/01/2024", "A", "500 Dr"], ["01/01/2024", "B", "500 Cr"], ["01/01/2024", "C", "(75.10)"], ["01/01/2024", "D", "75"]] };
    const base = { date: 0, description: 1, amount: 2, debit: null, credit: null, reference: null, date_format: "%d/%m/%Y" };
    const dirs = (sign) => applyMapping(table, { ...base, amount_sign: sign }, {}).map((r) => r.direction);
    expect(dirs("negative_is_debit")).toEqual(["debit", "credit", "debit", "credit"]);
    expect(dirs("negative_is_credit")).toEqual(["debit", "credit", "credit", "debit"]);
  });

  it("bank PDF: rebuilds the table, joins wrapped narrations, drops header/footer", async () => {
    const result = await parseStatement(fixtureFile("bank_hdfc.pdf"), { pdfjs });
    expect(result).toMatchObject({ status: "needs_mapping", source_type: "bank_pdf" });
    expect(result.table.header).toEqual(["Date", "Narration", "Chq./Ref.No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]);
    expect(result.table.rows).toEqual([
      ["01/08/24", "UPI-BLINKIT-blinkit.payu@hdfcbank- HDFC0000499-421411112222-Order", "0000421411112222", "623.00", "", "48,377.00"],
      ["02/08/24", "NEFT CR-ACME CORP PAYROLL", "N214567890", "", "85,000.00", "1,33,377.00"],
      ["03/08/24", "UPI-SUNITA DEVI-9812345678@ybl- YESB0YBLUPI-421633334444-Milk", "0000421633334444", "1,050.00", "", "1,32,327.00"],
    ]);
    const mapping = guessMapping(result.table.header, result.table.rows);
    expect(mapping).toMatchObject({ date: 0, description: 1, reference: 2, debit: 3, credit: 4, date_format: "%d/%m/%y" });
    const rows = applyMapping(result.table, mapping, { source_type: "bank_pdf", source_label: "HDFC" });
    expect(rows.map((r) => [r.date, r.amount, r.direction])).toEqual([
      ["2024-08-01", "623.00", "debit"], ["2024-08-02", "85000.00", "credit"], ["2024-08-03", "1050.00", "debit"],
    ]);
  });
});

describe("UPI apps", () => {
  it("Google Pay: pdf.js block text satisfies the strict ported regex (no fallback)", async () => {
    const { text } = await extractPdf(await fixtureFile("gpay.pdf").arrayBuffer(), { pdfjs });
    expect(parseGooglePay(text)).toHaveLength(4);
  });

  it("PhonePe", async () => {
    expect(await rowsOf("phonepe.pdf")).toEqual([
      { date: "2024-06-03T08:15:00", description_raw: "Swiggy", amount: "348.00", direction: "debit", reference: "415512345678", type: "transaction" },
      { date: "2024-06-05T19:47:00", description_raw: "Neha Gupta", amount: "2000.00", direction: "credit", reference: "415712345678", type: "transaction" },
      { date: "2024-06-09T10:02:00", description_raw: "Raju Kirana Store", amount: "86.40", direction: "debit", reference: "416112345678", type: "transaction" },
    ]);
  });

  it("Paytm: year inferred from the statement period across a year boundary", async () => {
    expect(await rowsOf("paytm.pdf")).toEqual([
      { date: "2023-12-28T21:30:00", description_raw: "Zomato", amount: "512.00", direction: "debit", reference: "335912345678", type: "transaction" },
      { date: "2024-01-02T06:05:00", description_raw: "Amit Kumar", amount: "1250.50", direction: "credit", reference: "400212345678", type: "transaction" },
      { date: "2024-01-29T13:00:00", description_raw: "Kavya", amount: "300.00", direction: "debit", reference: "402912345678", type: "transaction" },
    ]);
  });
});

describe("credit card statements", () => {
  const brief = async (name) => (await rowsOf(name)).map((r) => [r.date, r.description_raw, r.amount, r.direction, r.type]);

  it("HDFC", async () => {
    expect(await brief("card_hdfc.pdf")).toEqual([
      ["2024-03-12", "SWIGGY BANGALORE", "450.00", "debit", "transaction"],
      ["2024-03-15", "AMAZON PAY INDIA", "2199.00", "debit", "transaction"],
      ["2024-03-18", "PAYMENT RECEIVED - THANK YOU", "15000.00", "credit", "transfer"],
      ["2024-03-20", "REFUND MYNTRA DESIGNS", "799.00", "credit", "transaction"],
    ]);
  });

  it("ICICI (serial number becomes the reference)", async () => {
    const rows = await rowsOf("card_icici.pdf");
    expect(rows.map((r) => [r.date, r.description_raw, r.amount, r.direction, r.type, r.reference])).toEqual([
      ["2024-04-02", "UBER INDIA SYSTEMS", "342.50", "debit", "transaction", "10203040506"],
      ["2024-04-05", "BBPS PAYMENT RECEIVED", "8000.00", "credit", "transfer", "10203040507"],
      ["2024-04-07", "BOOKMYSHOW MUMBAI", "1040.00", "debit", "transaction", "10203040508"],
    ]);
  });

  it("SBI Card", async () => {
    expect(await brief("card_sbi.pdf")).toEqual([
      ["2024-03-05", "ZOMATO GURGAON", "389.00", "debit", "transaction"],
      ["2024-03-09", "PAYMENT RECEIVED 000123456", "5000.00", "credit", "transfer"],
      ["2024-03-11", "IRCTC E-TICKETING", "1675.40", "debit", "transaction"],
    ]);
  });

  it("Axis", async () => {
    expect(await brief("card_axis.pdf")).toEqual([
      ["2024-05-01", "BIGBASKET BANGALORE GROCERY", "1234.00", "debit", "transaction"],
      ["2024-05-04", "AUTOPAY PAYMENT RECEIVED", "9876.00", "credit", "transfer"],
      ["2024-05-06", "SPOTIFY INDIA ENTERTAINMENT", "119.00", "debit", "transaction"],
    ]);
  });
});

describe("Google Pay block layout (pdf.js order)", () => {
  // made-up rows in the order pdf.js reads a real Google Pay statement
  const text = [
    "01 Jul, 2026", "10:30 AM", "Self transfer to Test Bank 1234", "UPI Transaction ID: 111122223333", "Paid by Other Bank 9876", "₹500",
    "02 Jul, 2026", "09:00 PM", "Paid to Chai Point", "UPI Transaction ID: 444455556666", "Paid by Test Bank 1234", "₹20",
  ].join("\n");
  it("keeps a self transfer a transfer", () => {
    const rows = parseUpiBlocks("google_pay", text);
    expect(rows.map((r) => [r.type, r.direction, r.amount, r.reference])).toEqual([
      ["transfer", "debit", "500.00", "111122223333"], ["transaction", "debit", "20.00", "444455556666"]]);
  });
});
