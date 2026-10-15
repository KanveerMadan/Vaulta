import { describe, expect, it } from "vitest";
import { parseQuickAdd } from "./quickAdd.js";

const TODAY = new Date(2024, 2, 15); // Fri 15 Mar 2024

describe("parseQuickAdd", () => {
  it.each([
    ["150 auto cash", { amount: "150", merchant: "Auto", category: "Transport", date: "2024-03-15", payment_method: "cash", direction: "debit" }],
    ["2400 groceries dmart yesterday", { amount: "2400", merchant: "Dmart", category: "Groceries", date: "2024-03-14", payment_method: "cash", direction: "debit" }],
    ["₹1,250.50 swiggy dinner upi", { amount: "1250.50", merchant: "Swiggy", category: "Food & Dining", date: "2024-03-15", payment_method: "online", direction: "debit" }],
    ["2.4k rent", { amount: "2400", merchant: "Rent", category: "Rent & Housing", date: "2024-03-15", payment_method: "cash", direction: "debit" }],
    ["received 2000 from mom", { amount: "2000", merchant: "Mom", category: null, date: "2024-03-15", payment_method: "cash", direction: "credit" }],
    ["salary 85000 credited", { amount: "85000", merchant: "Salary Credited", category: null, date: "2024-03-15", payment_method: "cash", direction: "credit" }],
    ["60 chai day before yesterday", { amount: "60", merchant: "Chai", category: "Food & Dining", date: "2024-03-13", payment_method: "cash", direction: "debit" }],
    ["300 medicine monday", { amount: "300", merchant: "Medicine", category: "Health", date: "2024-03-11", payment_method: "cash", direction: "debit" }],
    ["500 petrol 12/3 card", { amount: "500", merchant: "Petrol", category: "Transport", date: "2024-03-12", payment_method: "online", direction: "debit" }],
    ["899 shoes 2 mar", { amount: "899", merchant: "Shoes", category: "Shopping", date: "2024-03-02", payment_method: "cash", direction: "debit" }],
    ["99 something 20 dec", { amount: "99", merchant: "Something", category: null, date: "2023-12-20", payment_method: "cash", direction: "debit" }],
    ["40", { amount: "40", merchant: "Cash spend", category: null, date: "2024-03-15", payment_method: "cash", direction: "debit" }],
  ])("%s", (text, expected) => {
    expect(parseQuickAdd(text, TODAY)).toEqual(expected);
  });

  it("needs an amount", () => {
    expect(parseQuickAdd("auto yesterday", TODAY)).toBeNull();
    expect(parseQuickAdd("0 auto", TODAY)).toBeNull();
  });
});
