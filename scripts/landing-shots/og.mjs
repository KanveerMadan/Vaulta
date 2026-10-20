// The 1200x630 share image (frontend/public/og.png): the hero's line and the real home screen (public/landing/home@2x.webp).
//   cd frontend && node ../scripts/landing-shots/og.mjs
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const { chromium } = createRequire(new URL("../../frontend/package.json", import.meta.url))("@playwright/test");
const f = (p) => fileURLToPath(new URL(`../../frontend/${p}`, import.meta.url));
const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:B;src:url(file://${f("node_modules/@fontsource-variable/bricolage-grotesque/files/bricolage-grotesque-latin-wght-normal.woff2")})}
@font-face{font-family:G;src:url(file://${f("node_modules/@fontsource-variable/geist/files/geist-latin-wght-normal.woff2")})}
html,body{margin:0;width:1200px;height:630px;background:#F4F6F3;color:#101511;font-family:G;overflow:hidden}
.wrap{position:relative;height:630px;box-sizing:border-box;padding:72px 88px}
.brand{font-family:B;font-weight:600;font-size:38px;letter-spacing:-.02em;border-bottom:3px solid #17643F;display:inline-block;padding-bottom:2px}
h1{font-family:B;font-weight:600;font-size:118px;line-height:.92;letter-spacing:-.045em;margin:70px 0 0;max-width:7ch}
h1 span{color:#17643F} p{font-size:30px;line-height:1.3;color:#3C463F;margin:28px 0 0;max-width:23ch}
.phone{position:absolute;right:96px;top:56px;width:300px;border-radius:44px;background:#101511;padding:11px;box-shadow:0 24px 60px rgba(16,32,22,.25)}
.phone img{display:block;width:100%;border-radius:34px}
.glow{position:absolute;right:60px;top:120px;width:380px;height:480px;border-radius:60px;background:#E3F0E8;filter:blur(30px)}
</style></head><body><div class="wrap"><span class="brand">Vaulta</span>
<h1>Kahan gaye <span>paise?</span></h1><p>Vaulta knows. No bank login, no SMS, no typing.</p>
<div class="glow"></div><div class="phone"><img src="file://${f("public/landing/home@2x.webp")}"></div></div></body></html>`;
const b = await chromium.launch(); const page = await b.newPage({ viewport: { width: 1200, height: 630 } });
// a file page, so it may load the local fonts and screenshot
const file = join(mkdtempSync(join(tmpdir(), "og-")), "og.html"); writeFileSync(file, html);
await page.goto(`file://${file}`, { waitUntil: "load" }); await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: f("public/og.png") }); await b.close(); console.log("og.png written");
