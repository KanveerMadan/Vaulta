// Search metadata: robots.txt, sitemap.xml and the page list agree; share tags point at vaulta.in.
// Titles and canonical URLs are checked in a real browser (e2e/public.spec.js).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { PUBLIC_PAGES, SITE } from "./pageMeta.js";

const read = (p) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");
const robots = read("public/robots.txt");
const sitemap = read("public/sitemap.xml");
const app = read("src/App.jsx");
const html = read("index.html");

describe("search metadata", () => {
  it("sitemap lists exactly the public pages, on vaulta.in", () => {
    const locs = [...sitemap.matchAll(/<loc>(.*?)<\/loc>/g)].map((m) => m[1]);
    expect(locs).toEqual(Object.keys(PUBLIC_PAGES).map((p) => SITE + p));
  });

  it("robots allows the public pages, disallows every signed-in route, and names the sitemap", () => {
    const allowed = [...robots.matchAll(/^Allow: (\S+)/gm)].map((m) => m[1]);
    const disallowed = [...robots.matchAll(/^Disallow: (\S+)/gm)].map((m) => m[1]);
    for (const p of Object.keys(PUBLIC_PAGES)) expect(allowed).toContain(p);
    const routes = [...app.matchAll(/<Route path="(\/[a-z-]+)/g)].map((m) => m[1]).filter((p) => !(p in PUBLIC_PAGES));
    expect(routes.length).toBeGreaterThan(10);
    for (const r of routes) expect(disallowed, r).toContain(r);
    expect(robots).toContain(`Sitemap: ${SITE}/sitemap.xml`);
  });

  it("share tags are absolute vaulta.in URLs, never a default host", () => {
    for (const k of ["og:url", "og:image", "twitter:image"]) {
      expect(html).toMatch(new RegExp(`(property|name)="${k}" content="https://vaulta\\.in/`));
    }
    expect(html + robots + sitemap).not.toMatch(/vercel\.app|onrender\.com|firebaseapp\.com/);
    const png = readFileSync(new URL("../../public/og.png", import.meta.url));
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630]);
  });

});
