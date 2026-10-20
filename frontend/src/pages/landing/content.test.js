// The landing page's FAQ names exactly what the code supports, and its images are local files with both sizes.
import { readFileSync, existsSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { BANKS } from "../../import/banks.js";
import { ISSUERS } from "../../import/creditCard.js";
import { UPI_SOURCES } from "../../import/upi.js";
import { ALERT_SENDERS, CARD_ISSUERS, CHIPS, FAQ, FEATURES, STATEMENT_BANKS, STEPS, TILES, UPI_APPS } from "./content.js";
import { SHOTS } from "./shots.js";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

describe("landing content", () => {
  it("the FAQ's banks are exactly the ones the importers and the alert allowlist know", () => {
    expect(new Set(STATEMENT_BANKS)).toEqual(new Set(Object.values(BANKS).map((b) => b.label)));
    expect(CARD_ISSUERS).toEqual(Object.values(ISSUERS).map((i) => i.label));
    expect(UPI_APPS).toEqual(Object.values(UPI_SOURCES).map((u) => u.label));
    const senders = [...read("../../../../backend/app/core/alert_senders.py").matchAll(/"name": "([^"]+)"/g)].map((m) => m[1]);
    expect(ALERT_SENDERS).toEqual(senders);
    const answer = FAQ.find((f) => f.q === "Which banks work?").a.join(" ");
    for (const b of [...STATEMENT_BANKS, ...UPI_APPS, ...ALERT_SENDERS]) expect(answer).toContain(b);
  });

  it("every image is a local WebP at 1x and 2x with its size known; no external image hosts", () => {
    for (const name of [...STEPS, ...FEATURES].map((s) => s.shot).concat("home")) {
      expect(SHOTS[name], name).toBeTruthy();
      for (const f of [`${name}.webp`, `${name}@2x.webp`]) expect(existsSync(new URL(`../../../public/landing/${f}`, import.meta.url)), f).toBe(true);
    }
    for (const file of ["Landing.jsx", "Shot.jsx"]) expect(read(`./${file}`)).not.toMatch(/<img[^>]+src=["'{`]*https?:/);
    for (const s of [...STEPS, ...FEATURES]) expect(s.alt.length, s.shot).toBeGreaterThan(30);
  });

  it("says open source only because the repository has an open-source licence", () => {
    expect(read("../../../../LICENSE")).toMatch(/^MIT License\n\nCopyright \(c\) 2026 Kanveer Madan/);
    expect(CHIPS).toContain("Open source");
    expect(TILES.find((t) => t.icon === "code").body).toMatch(/^Open source: .*MIT licence/);
  });
});
