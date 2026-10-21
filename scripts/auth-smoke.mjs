// Sign-in smoke test against a deployment: Firebase's sign-in pages are served from it (not the app, not through the
// service worker, not under our CSP), an email login answers instead of hanging, and the Google popup reaches Google.
// Creates no account. Usage (from frontend/, which has Playwright):
//   node ../scripts/auth-smoke.mjs https://vaulta.in [--browser chromium|webkit|firefox] [--device "iPhone 15 Pro"]
import { createRequire } from "node:module";

const pw = createRequire(new URL("../frontend/package.json", import.meta.url))("@playwright/test");
const args = process.argv.slice(2);
const origin = (args.find((a) => a.startsWith("https://")) || "https://vaulta.in").replace(/\/$/, "");
const opt = (name) => { const i = args.indexOf(name); return i > -1 ? args[i + 1] : undefined; };
const browserName = opt("--browser") || "chromium";
const device = opt("--device");

let failed = 0;
const check = (ok, what) => { console.log(`${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) failed++; };
const isFirebasePage = (html, script) => html.includes(`src="${script}"`) && !html.includes('id="root"');

// 1. Plain requests: Firebase's own pages, without our frame-blocking headers
for (const [path, script] of [["/__/auth/handler", "handler.js"], ["/__/auth/iframe", "iframe.js"]]) {
  const r = await fetch(origin + path, { redirect: "manual" });
  check(r.status === 200 && isFirebasePage(await r.text(), script), `${path}: Firebase's page (${r.status})`);
  check(!/frame-ancestors 'none'/.test(r.headers.get("content-security-policy") || "") && !r.headers.get("x-frame-options"),
    `${path}: no CSP or X-Frame-Options of ours`);
}

const browser = await pw[browserName].launch();
const ctx = await browser.newContext(device ? pw.devices[device] : {});
const page = await ctx.newPage();

// 2. With the service worker in control, /__/auth/handler still reaches Firebase
await page.goto(origin + "/welcome");
await page.waitForFunction(() => navigator.serviceWorker?.ready.then(() => true), null, { timeout: 30000 });
await page.reload();
check(await page.evaluate(() => !!navigator.serviceWorker.controller), "service worker controls the page");
const handler = await ctx.newPage();
await handler.goto(origin + "/__/auth/handler");
check(handler.url().startsWith(origin + "/__/auth/handler") && isFirebasePage(await handler.content(), "handler.js"),
  "with the service worker: /__/auth/handler is Firebase's page");
await handler.close();

// 3. Email login with an address that has no account: an answer, not "Please wait…" forever
await page.goto(origin + "/login");
await page.fill("#login-email", `smoke-${Date.now()}@example.invalid`);
await page.fill("#login-password", "not-a-real-password-1");
await page.getByRole("button", { name: "Log in", exact: true }).click();
check(await page.getByText("Incorrect email or password.").waitFor({ timeout: 20000 }).then(() => true, () => false),
  "email login answers (\"Incorrect email or password.\")");

// 4. Google: the popup goes to accounts.google.com and Google accepts the redirect URI
await page.goto(origin + "/welcome");
const [popup] = await Promise.all([ctx.waitForEvent("page", { timeout: 15000 }), page.locator("[data-cta=primary]").first().click()]);
const reached = await popup.waitForURL(/accounts\.google\.com/, { timeout: 30000 }).then(() => true, () => false);
check(reached, `Google popup reaches accounts.google.com (at ${new URL(popup.url()).host}${new URL(popup.url()).pathname})`);
if (reached) {
  await popup.waitForLoadState("domcontentloaded");
  check(!/redirect_uri_mismatch|invalid_request/i.test(await popup.content()), "Google accepts the redirect URI");
}

await browser.close();
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
