// The balance check (banks.js, go-live stage 2): running balances reconcile on the device, only pass/fail comes out.
import { describe, expect, it } from "vitest";
import { bankBalanceCheck, parseBalance, reconcileBalances } from "./banks.js";
import { mappedBalanceCheck } from "./mapping.js";

const HEADER = ["Tran Date", "Particulars", "Chq No", "Debit", "Credit", "Balance"];
const rows = [
  ["01-04-2024", "OPENING BALANCE", "", "", "", "10,000.00"],
  ["02-04-2024", "UPI/SWIGGY", "", "450.00", "", "9,550.00"],
  ["03-04-2024", "NEFT SALARY", "", "", "50,000.00", "59,550.00"],
  ["04-04-2024", "ATM WDL", "", "2,000.00", "", "57,550.00"],
];

describe("parseBalance", () => {
  it("reads Indian grouping, signs and Dr/Cr in paise", () => {
    expect(parseBalance("1,23,456.78")).toBe(12345678);
    expect(parseBalance("500.00 Dr")).toBe(-50000);
    expect(parseBalance("500.00Cr")).toBe(50000);
    expect(parseBalance("-12")).toBe(-1200);
    expect(parseBalance("")).toBeNull();
    expect(parseBalance("n/a")).toBeNull();
  });
});

describe("reconcileBalances", () => {
  it("passes oldest-first and newest-first, fails on a gap or a dropped row, and has nothing to say about one row", () => {
    const asc = [{ balance: 1000, delta: 0 }, { balance: 900, delta: -100 }, { balance: 1400, delta: 500 }];
    expect(reconcileBalances(asc)).toBe("pass");
    const desc = [{ balance: 1400, delta: 500 }, { balance: 900, delta: -100 }, { balance: 1000, delta: 0 }];
    expect(reconcileBalances(desc)).toBe("pass");
    expect(reconcileBalances([asc[0], asc[1], { balance: 1300, delta: 500 }])).toBe("fail");
    expect(reconcileBalances([asc[0], { balance: 900, delta: null }, asc[2]])).toBe("fail");
    expect(reconcileBalances([asc[0]])).toBeNull();
  });
});

describe("bankBalanceCheck", () => {
  it("passes a complete statement, with an opening-balance line that moves nothing", () => {
    expect(bankBalanceCheck("axis", HEADER, rows)).toBe("pass");
  });
  it("fails when a row with an amount can't be read (it would be missing from the import)", () => {
    const broken = rows.map((r, i) => (i === 2 ? ["32-04-2024", ...r.slice(1)] : r));
    expect(bankBalanceCheck("axis", HEADER, broken)).toBe("fail");
  });
  it("fails when an amount was misread", () => {
    expect(bankBalanceCheck("axis", HEADER, rows.map((r, i) => (i === 1 ? [...r.slice(0, 3), "45.00", ...r.slice(4)] : r)))).toBe("fail");
  });
  it("has nothing to say without a balance column", () => {
    expect(bankBalanceCheck("axis", HEADER.slice(0, 5), rows.map((r) => r.slice(0, 5)))).toBeNull();
  });
});

describe("mappedBalanceCheck", () => {
  const mapping = { date: 0, date_format: "%d-%m-%Y", description: 1, debit: 3, credit: 4 };
  it("checks a mapped table by its balance column, which is never mapped", () => {
    expect(mappedBalanceCheck({ header: HEADER, rows }, mapping)).toBe("pass");
    expect(mappedBalanceCheck({ header: HEADER, rows: rows.slice(0, 2).concat([rows[3]]) }, mapping)).toBe("fail");
  });
});
