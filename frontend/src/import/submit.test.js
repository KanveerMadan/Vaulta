// Sending a Kotak Mahindra statement (prod incident, 21 Oct 2026): 218 rows went in 200-row batches under the 20 s
// default timeout, a slow batch timed out, was never resent, and the app said only "Import failed". The rows here are
// synthetic, in Kotak's CSV layout, and go through the real parse → PII strip → send path.
import { describe, expect, it } from "vitest";
import { parseStatement } from "./index.js";
import { sanitizeRows } from "./pii.js";
import { BATCH_SIZE, BATCH_TIMEOUT_MS, importErrorMessage, sendRows } from "./submit.js";

const MERCHANTS = ["ZEPTO MARKETPLACE", "SWIGGY", "ZOMATO LTD", "UBER INDIA", "AMAZON PAY", "BLINKIT", "BESCOM", "AIRTEL"];
const PEOPLE = ["SANJAY VERMA", "PRIYA NAIR", "AMIT SHAH"];

function kotakCsv(n) {
  const lines = ["Sl. No.,Transaction Date,Value Date,Description,Chq/Ref Number,Debit,Credit,Balance"];
  let balance = 250000;
  for (let i = 0; i < n; i++) {
    const day = new Date(Date.UTC(2026, 6, 1) + Math.floor((i * 92) / n) * 86400000);
    const d = `${String(day.getUTCDate()).padStart(2, "0")}-${String(day.getUTCMonth() + 1).padStart(2, "0")}-2026`;
    const utr = String(600000000000 + i * 7919);
    const amount = (i * 137) % 4000 + 49;
    const [desc, ref, debit, credit] = [
      [`NEFT/ACME PAYROLL/N${100000 + i}`, `NEFT-N${100000 + i}`, 0, 85000],
      [`UPI/${PEOPLE[i % 3]}/${utr}/split`, `UPI-${utr}`, amount, 0],
      [`IMPS/${PEOPLE[i % 3]}/${utr}`, `IMPS-${utr}`, 0, amount],
      [`ATM WDL/KOTAK ATM MUMBAI/${i}`, `ATM-${1000 + i}`, 2000, 0],
      ["NACH/LIC OF INDIA/POLICY 123456789", `NACH-0${i % 9}`, 5230, 0],
      [`POS/${MERCHANTS[i % 8]}/BANGALORE`, `POS-${utr.slice(0, 8)}`, amount, 0],
    ][i % 6] ?? [];
    balance += credit - debit;
    const money = (x) => (x ? `"${x.toLocaleString("en-IN", { minimumFractionDigits: 2 })}"` : "");
    lines.push([i + 1, d, d, desc, ref, money(debit), money(credit), money(balance)].join(","));
  }
  return lines.join("\n") + "\n";
}

async function kotakRows(n = 218) {
  const parsed = await parseStatement(new File([kotakCsv(n)], "kotak.csv", { type: "text/csv" }));
  expect(parsed.status).toBe("ok");
  expect(parsed.balance_check).toBe("pass");
  return sanitizeRows(parsed.rows).rows;
}

const timeout = () => Object.assign(new Error("timeout of 90000ms exceeded"), { code: "ECONNABORTED" });
const waking = () => Object.assign(new Error("Request failed with status code 503"), { response: { status: 503, data: {} } });

/** A server that answers each call with the next scripted outcome (an error to throw, or "ok"). */
function fakeApi(...script) {
  const calls = [];
  return {
    calls,
    post: async (url, body, config) => {
      calls.push({ url, body, config });
      const next = script.length ? script.shift() : "ok";
      if (next !== "ok") throw next();
      return { data: { imported: body.rows.length, duplicates_merged: 0, transfers_flagged: 0, rows_needing_review: 0, failed: 0 } };
    },
  };
}
const noPause = async () => {};

describe("sending a Kotak statement", () => {
  it("parses and strips 218 synthetic rows, then sends them in small batches with a long timeout", async () => {
    const rows = await kotakRows();
    expect(rows).toHaveLength(218);
    expect(rows.every((r) => r.source_label === "Kotak Mahindra Bank" && !/\d{9,}/.test(r.description_raw))).toBe(true);
    const api = fakeApi();
    const totals = await sendRows(api, rows, { pause: noPause });
    expect(totals.imported).toBe(218);
    expect(api.calls).toHaveLength(Math.ceil(218 / BATCH_SIZE));
    expect(Math.max(...api.calls.map((c) => c.body.rows.length))).toBeLessThanOrEqual(50);
    for (const { config } of api.calls) expect(config).toEqual({ timeout: BATCH_TIMEOUT_MS, idempotent: true });
  });

  it("sends a batch again after a timeout or a waking API, and finishes the import", async () => {
    const rows = await kotakRows();
    const api = fakeApi(timeout, waking);
    const totals = await sendRows(api, rows, { pause: noPause });
    expect(totals.imported).toBe(218);
    expect(api.calls).toHaveLength(Math.ceil(218 / BATCH_SIZE) + 2);
    expect(api.calls[1].body).toEqual(api.calls[0].body);            // the same rows, the same import id
  });

  it("gives up after three tries, saying how far it got and why", async () => {
    const rows = await kotakRows();
    const api = fakeApi("ok", "ok", timeout, timeout, timeout);
    const err = await sendRows(api, rows, { pause: noPause }).catch((e) => e);
    expect(api.calls).toHaveLength(5);
    expect(err.saved).toBe(100);
    expect(importErrorMessage(err, rows.length, true))
      .toBe("vaulta.in took too long to answer, even after retrying. The first 100 of 218 rows are saved; importing again skips them.");
  });

  it("doesn't resend what the server refused, and names the row", async () => {
    const rows = await kotakRows();
    const refused = () => Object.assign(new Error("422"), { response: { status: 422, data: { detail: [
      { loc: ["body", "rows", 6, "reference"], msg: "reference looks like an account number" }] } } });
    const api = fakeApi("ok", refused);
    const err = await sendRows(api, rows, { pause: noPause }).catch((e) => e);
    expect(api.calls).toHaveLength(2);
    expect(importErrorMessage(err, rows.length, true)).toBe(
      "Row 57 (reference): reference looks like an account number. The first 50 of 218 rows are saved; importing again skips them.");
  });
});

describe("importErrorMessage", () => {
  const msg = (err) => importErrorMessage(err, 218, true);
  it("gives the server's reason, or what kind of failure it was, never just Import failed", () => {
    expect(msg({ response: { status: 500, data: { detail: "Something went wrong.", request_id: "ab12cd34ef56ab78" } } }))
      .toBe("Something went wrong on our side (reference ab12cd34ef56ab78). Nothing is lost: try again and already-saved rows are skipped.");
    expect(msg({ response: { status: 429, data: { detail: "Too many requests. Try again in a little while." } } }))
      .toMatch(/^Too many requests\. Try again in a little while\. Nothing is lost/);
    expect(msg({ response: { status: 503, data: { detail: "Database is starting up. Please retry in a few seconds." } } }))
      .toMatch(/^vaulta\.in is starting up or busy/);
    expect(msg({ code: "ERR_NETWORK" })).toMatch(/^Couldn't reach vaulta\.in\./);
    expect(importErrorMessage({ code: "ERR_NETWORK" }, 218, false)).toMatch(/^You're offline\./);
  });
});
