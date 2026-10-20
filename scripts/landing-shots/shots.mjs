// Landing-page images, captured from the read-only DEMO account (synthetic data). No real user's data can appear:
// the demo is its own account, entered with "Try the demo", never a sign-in. Run from frontend/:
//   node ../scripts/landing-shots/shots.mjs <out-dir>          (BASE_URL=https://vaulta.in by default)
//   python3 ../scripts/landing-shots/to_webp.py <out-dir> public/landing
// DIST=<a production build of this branch>: serve those files as https://vaulta.in (the real API still answers), so
// the shots show this branch's UI before it is deployed.
// The hero screen hides the demo banner, the ask/quick-add bar, the review cards and own-account transfers so the
// home screen fits one phone screen; nothing shown is edited. Cutouts are element screenshots of the real app.
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, existsSync } from "node:fs";
import { extname, join } from "node:path";

// Playwright is the frontend's dev dependency
const { chromium } = createRequire(new URL("../../frontend/package.json", import.meta.url))("@playwright/test");

const BASE = process.env.BASE_URL || "https://vaulta.in";
const OUT = process.argv[2] || "landing-shots-out";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
  colorScheme: "light", reducedMotion: "reduce", locale: "en-IN", timezoneId: "Asia/Kolkata", serviceWorkers: "block" });
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png",
  ".webp": "image/webp", ".woff2": "font/woff2", ".json": "application/json", ".webmanifest": "application/manifest+json", ".wasm": "application/wasm" };
if (process.env.DIST) {
  await ctx.route(`${BASE}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    const file = join(process.env.DIST, path);
    const hit = extname(path) && existsSync(file) ? file : join(process.env.DIST, "index.html");
    route.fulfill({ body: readFileSync(hit), contentType: TYPES[extname(hit)] || "application/octet-stream" });
  });
}
const page = await ctx.newPage();
const settle = async () => { await page.waitForLoadState("networkidle").catch(() => {}); await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(700); };
// hide through the CSSOM (the app's CSP allows that, not injected stylesheets)
const hide = async (locator) => { for (const el of await locator.elementHandles()) await el.evaluate((n) => { n.style.display = "none"; }); };
const banner = () => page.locator("div", { has: page.getByText("You're viewing a demo with sample data.") }).last();
const save = async (target, name) => { await settle(); await target.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" }); console.log("saved", name); };

await page.goto(`${BASE}/welcome`);
await page.getByRole("button", { name: /Try the demo|look around the demo/i }).first().click();
await page.getByText("Safe to spend today").waitFor({ timeout: 120_000 });
await page.keyboard.press("Escape").catch(() => {});
await settle();

// 1. hero: the home screen, one phone screen tall
await hide(banner());
await hide(page.locator("section[aria-label='Needs attention']"));
await hide(page.getByLabel("Quick add a transaction").locator("xpath=ancestor::div[contains(@class,'card')][1]"));
await hide(page.locator("form", { has: page.getByPlaceholder(/Ask anything/) }));
await hide(page.locator("section[aria-label='Recent transactions'] .divide-y > *", { hasText: "Own-account transfer" }));
await hide(page.getByRole("button", { name: "Ask the assistant" }));
await save(page, "home");
// 4a. feature cutouts from the same screen
await save(page.locator("[data-tour='safe']"), "cut-safe");
await save(page.locator("section[aria-label='Budgets']"), "cut-budgets");
await save(page.locator("section[aria-label='Coming up']"), "cut-coming-up");

// 2. transactions list
await page.goto(`${BASE}/transactions`); await page.getByRole("list", { name: "Transactions" }).waitFor();
await hide(banner()); await hide(page.getByRole("button", { name: "Ask the assistant" }));
await hide(page.getByRole("list", { name: "Transactions" }).getByRole("listitem").filter({ hasText: "Own-account transfer" }));
await save(page, "transactions");

// 4b. recurring: rent and a subscription (other active series hidden)
await page.goto(`${BASE}/recurring`); await settle(); await hide(banner()); await hide(page.getByRole("button", { name: "Ask the assistant" }));
const active = page.locator("section.card", { has: page.getByRole("heading", { name: /^Active/ }) });
await hide(active.locator(":scope > *").filter({ hasNotText: /Netflix|Rahul Sharma|^Active/ }));
await save(active, "cut-recurring");

// 3. how it works: the sample statement preview and a sample bank alert (/try, samples only, nothing imported)
await page.goto(`${BASE}/try`); await settle(); await hide(banner()); await hide(page.getByRole("button", { name: "Ask the assistant" }));
await page.getByRole("button", { name: "Send a sample alert" }).click();
await page.waitForTimeout(2500);
await save(page.locator("section, div.card", { hasText: "A bank alert email" }).last(), "cut-alert");
await page.getByRole("button", { name: "Open a sample statement" }).click();
const sheet = page.getByRole("dialog");
await sheet.getByText(/transactions from/i).first().waitFor({ timeout: 30_000 });
await save(sheet, "cut-statement");
await page.keyboard.press("Escape");

// 5. chat: the question and the start of the answer
await page.goto(`${BASE}/`); await page.getByText("Safe to spend today").waitFor();
await page.getByRole("button", { name: "Ask the assistant" }).click();
const chat = page.getByRole("complementary", { name: "AI Assistant" });
await chat.getByLabel("Ask the assistant").fill("How much did I spend on food this month?");
await chat.getByRole("button", { name: "Send" }).click();
await chat.getByLabel("Vaulta is answering").waitFor({ state: "detached", timeout: 90_000 }).catch(() => {});
await page.waitForTimeout(2500);
await chat.locator("[aria-live='polite']").evaluate((n) => { n.scrollTop = 0; });
await settle();
await page.screenshot({ path: `${OUT}/chat.png`, clip: { x: 0, y: 0, width: 390, height: 430 } }); console.log("saved chat");
// 6. the weekly email (rendered by report_email.py), at an email client's width
if (process.env.REPORT_HTML) {
  const mail = await browser.newPage({ viewport: { width: 600, height: 900 }, deviceScaleFactor: 2 });
  await mail.goto(`file://${process.env.REPORT_HTML}`); await mail.waitForTimeout(500);
  await mail.screenshot({ path: `${OUT}/email.png`, fullPage: true }); console.log("saved email");
}
await browser.close();
