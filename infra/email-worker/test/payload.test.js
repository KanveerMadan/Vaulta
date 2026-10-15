import { test } from "node:test";
import assert from "node:assert/strict";
import PostalMime from "postal-mime";
import { buildPayload, MAX_BYTES } from "../src/payload.js";

const MIME = [
  "From: HDFC Bank InstaAlerts <alerts@hdfcbank.net>",
  "To: abcde12345@in.example.in",
  "Subject: You have done a UPI txn. Check details!",
  "MIME-Version: 1.0",
  'Content-Type: multipart/mixed; boundary="b1"',
  "",
  "--b1",
  "Content-Type: text/plain; charset=utf-8",
  "",
  "Dear Customer, Rs.450.00 has been debited from account **1234 to VPA swiggy@icici SWIGGY on 05-03-24.",
  "--b1",
  "Content-Type: application/pdf; name=statement.pdf",
  "Content-Disposition: attachment; filename=statement.pdf",
  "Content-Transfer-Encoding: base64",
  "",
  "JVBERi0xLjQKJcfsj6IK",
  "--b1--",
  "",
].join("\r\n");

test("parses the email and drops attachments", async () => {
  const parsed = await PostalMime.parse(MIME);
  assert.equal(parsed.attachments.length, 1);
  const payload = buildPayload({ to: "abcde12345@in.example.in", from: "HDFC Bank InstaAlerts <alerts@hdfcbank.net>",
    subject: parsed.subject, text: parsed.text, html: parsed.html, authResults: "mx.cloudflare.net; dkim=pass header.d=hdfcbank.net" });
  assert.deepEqual(Object.keys(payload), ["to", "from", "subject", "text", "html", "auth_results"]);
  assert.match(payload.text, /Rs\.450\.00 has been debited/);
  assert.doesNotMatch(JSON.stringify(payload), /JVBERi0x|statement\.pdf/);
});

test("stays under the size limit by trimming html, then text", () => {
  const big = "x".repeat(MAX_BYTES * 2);
  const payload = buildPayload({ to: "a@b", from: "c@d", subject: "s", text: "Rs 1 debited", html: big, authResults: "" });
  assert.ok(new TextEncoder().encode(JSON.stringify(payload)).length <= MAX_BYTES);
  assert.equal(payload.text, "Rs 1 debited");
});
