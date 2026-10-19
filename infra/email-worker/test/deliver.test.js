import { test } from "node:test";
import assert from "node:assert/strict";
import { deliver, DEADLINE_MS } from "../src/deliver.js";

const ENV = { API_URL: "https://api.example.in/", INTERNAL_SECRET: "s" };
function clock() { let t = 0; return { now: () => t, pause: async (ms) => { t += ms; } }; }
const replies = (...rs) => { let i = 0; const calls = []; const fn = async (url, init) => {
  calls.push(url); const r = rs[Math.min(i++, rs.length - 1)]; if (r === "refused") throw new TypeError("fetch failed"); return { status: r };
}; fn.calls = calls; return fn; };

test("delivers straight away when the API is up", async () => {
  const fetchFn = replies(200);
  assert.equal(await deliver({}, ENV, { fetchFn, ...clock() }), 200);
  assert.deepEqual(fetchFn.calls, ["https://api.example.in/internal/inbound-email"]);
});

test("waits out a cold start: refused connections and 502/503 are retried", async () => {
  const fetchFn = replies("refused", 503, 502, "refused", 200);
  assert.equal(await deliver({}, ENV, { fetchFn, ...clock() }), 200);
  assert.equal(fetchFn.calls.length, 5);
});

test("a real answer isn't retried: 4xx returns, 500 throws", async () => {
  const f4 = replies(403);
  assert.equal(await deliver({}, ENV, { fetchFn: f4, ...clock() }), 403);
  assert.equal(f4.calls.length, 1);
  const f5 = replies(500);
  await assert.rejects(deliver({}, ENV, { fetchFn: f5, ...clock() }), /500/);
  assert.equal(f5.calls.length, 1);
});

test("gives up after about two minutes so the sending server retries later", async () => {
  const c = clock();
  const fetchFn = replies("refused");
  await assert.rejects(deliver({}, ENV, { fetchFn, ...c }), /not reachable/);
  assert.ok(c.now() >= DEADLINE_MS && c.now() < DEADLINE_MS + 31_000);
  assert.ok(fetchFn.calls.length < 12);
});
