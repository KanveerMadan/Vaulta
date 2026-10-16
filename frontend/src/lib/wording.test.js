import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { LANDING_CLAIMS, TRUST } from "./trust";

// Claims that can't be verified (or aren't true) never appear anywhere in the frontend
const BANNED = [/bank[\s-]*grade/i, /100\s*%\s*secure/i, /military[\s-]*grade/i, /unhackable/i, /completely\s+secure/i, /fully\s+secure/i];
const ROOTS = ["src", "index.html", "public"];

function files(path) {
  if (statSync(path).isFile()) return [path];
  return readdirSync(path).flatMap((f) => (f === "ocr" ? [] : files(join(path, f))));
}

describe("wording", () => {
  it("never makes banned security claims", () => {
    const hits = ROOTS.flatMap(files)
      .filter((f) => /\.(jsx?|html|json|webmanifest|svg|css|md)$/.test(f) && !f.endsWith("wording.test.js"))
      .flatMap((f) => BANNED.filter((re) => re.test(readFileSync(f, "utf8"))).map((re) => `${f}: ${re}`));
    expect(hits).toEqual([]);
  });

  it("uses no em or en dashes in interface copy", () => {
    const hits = files("src")
      .filter((f) => /\.jsx$|trust\.js$/.test(f))
      .flatMap((f) => readFileSync(f, "utf8").split("\n").map((line, i) => [f, i + 1, line]))
      .filter(([, , line]) => /[\u2013\u2014]/.test(line) && !/^\s*(\/\/|\*|\/\*|\{\/\*)/.test(line))
      .map(([f, n]) => `${f}:${n}`);
    expect(hits).toEqual([]);
  });

  it("gives every claim an anchor, a how-it-works text and how it's checked", () => {
    const ids = TRUST.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const t of TRUST) {
      expect(t.id).toMatch(/^[a-z-]+$/);
      expect(t.claim.length).toBeGreaterThan(10);
      expect(t.how.length).toBeGreaterThan(80);
      expect(t.checked.length).toBeGreaterThan(20);
    }
  });

  it("names the AI provider and states what it receives", () => {
    const ai = TRUST.find((t) => t.id === "ai").how;
    expect(ai).toContain("Groq");
    expect(ai).toMatch(/merchant names, categories, amounts and dates/);
  });

  it("puts the core claims on the landing page, each pointing at its place on /security", () => {
    expect(LANDING_CLAIMS.map((t) => t.id)).toEqual(["on-device", "stripped", "encrypted", "isolated", "alert-emails", "ai", "your-data"]);
    for (const t of LANDING_CLAIMS) expect(TRUST[t.n - 1].id).toBe(t.id);
  });

  it("the security page links every claim to its how-it-works section", () => {
    const page = readFileSync("src/pages/Security.jsx", "utf8");
    expect(page).toContain("href={`#how-${t.id}`}");
    expect(page).toContain("id={`how-${t.id}`}");
    expect(page).toContain("id={`claim-${i + 1}`}");
  });
});
