// Error monitoring in the browser (lib/monitoring.js): off without a DSN, and nothing personal survives the scrubber.
import { describe, expect, it } from "vitest";
import { scrubBreadcrumb, scrubEvent, scrubText, startMonitoring } from "./monitoring.js";

const SECRETS = ["UPI-RAHUL SHARMA", "rahul.s@okaxis", "priya@example.com", "1,234.50", "4210.50", "Swiggy Bangalore",
  "sessiontoken123", "Bearer eyJhbGciOi", "searchterm-netflix", "412345678901"];

describe("monitoring", () => {
  it("is off without a DSN", () => {
    expect(startMonitoring("")).toBe(false);
    expect(startMonitoring(undefined)).toBe(false);
  });

  it("scrubs events and breadcrumbs, keeping what finds the bug", () => {
    const event = {
      request: { url: "https://vaulta.in/transactions?q=searchterm-netflix&t=sessiontoken123",
        headers: { Authorization: "Bearer eyJhbGciOi", Referer: "https://vaulta.in/?q=searchterm-netflix" } },
      user: { email: "priya@example.com" }, extra: { row: "Swiggy Bangalore" },
      contexts: { browser: { name: "Safari" }, state: { amount: "4210.50" } },
      exception: { values: [{ type: "TypeError", value: "Cannot read 'UPI-RAHUL SHARMA' (rahul.s@okaxis) 1,234.50 ref 412345678901",
        stacktrace: { frames: [{ filename: "/assets/index.js", function: "render", vars: { row: "Swiggy Bangalore" } }] } }] },
      message: "paid priya@example.com ₹4210.50",
      breadcrumbs: [
        { category: "ui.click", message: "button[aria-label=\"More for UPI-RAHUL SHARMA\"]" },
        { category: "console", message: "row Swiggy Bangalore 4210.50" },
        { category: "fetch", type: "http", data: { method: "GET", url: "https://api.vaulta.in/api/transactions?q=searchterm-netflix", status_code: 500 } },
        { category: "navigation", data: { from: "/transactions?q=searchterm-netflix", to: "/budgets" } },
      ],
    };
    const out = JSON.stringify(scrubEvent(event));
    expect(SECRETS.filter((s) => out.includes(s))).toEqual([]);
    for (const kept of ['"TypeError"', '"render"', "/assets/index.js", "https://vaulta.in/transactions", "/api/transactions", "Safari", "/budgets", "500"]) {
      expect(out).toContain(kept);
    }
  });

  it("free text loses emails, UPI IDs, amounts, long numbers and quoted values", () => {
    expect(scrubText("x 'Swiggy' rahul@okaxis ₹1,200 99.50 412345678901")).toBe("x '[text]' [email-or-upi] [amount] [amount] [number]");
    expect(scrubBreadcrumb({ category: "ui.click", message: "Rahul" })).not.toHaveProperty("message");
  });
});
