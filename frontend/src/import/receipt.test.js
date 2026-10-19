import { describe, expect, it } from "vitest";
import { extractReceipt, findDate, findMerchant, findTotal } from "./receipt.js";

describe("receipt rules", () => {
  it("prefers grand total over sub total and tax lines", () => {
    expect(findTotal(["Sub Total 267.00", "CGST 2.5% 6.68", "Grand Total 280.36", "Total Items 3"])).toBe(280.36);
    expect(findTotal(["Total Savings 50.00", "Net Amount 1,180.00", "Total 1,230.00"])).toBe(1180);
    expect(findTotal(["Item A 40.00", "Item B 60.00", "TOTAL 100.00"])).toBe(100);
  });
  it("falls back to the largest priced amount; ignores bill numbers and phones", () => {
    expect(findTotal(["Bill No 4471", "Ph 9876543210", "Chai 20.00", "Samosa ₹30", "Amount 50.00"])).toBe(50);
    expect(findTotal(["no prices here"])).toBeNull();
  });
  it("merchant is the first real name near the top", () => {
    expect(findMerchant(["TAX INVOICE", "GSTIN 29ABCDE1234F1Z5", "Hotel Saravana Bhavan", "Chennai"])).toBe("Hotel Saravana Bhavan");
    expect(findMerchant(["12345", "Bill No 7"])).toBeNull();
  });
  it("dates are day-first", () => {
    expect(findDate(["Date: 14/03/2024 18:42"])).toBe("2024-03-14");
    expect(findDate(["Dt 05-11-24"])).toBe("2024-11-05");
    expect(findDate(["14 Mar 2024"])).toBe("2024-03-14");
    expect(findDate(["Mar 14, 2024"])).toBe("2024-03-14");
    expect(findDate(["31/02/2024"])).toBeNull();
  });
  it("puts it together", () => {
    expect(extractReceipt(["DMART AVENUE", "Date 02/03/2024", "Groceries", "Grand Total 1,845.25", "Paid by Card"])).toEqual({
      amount: "1845.25", merchant: "Dmart Avenue", date: "2024-03-02", payment_method: "online", category: "Groceries",
    });
  });
});
