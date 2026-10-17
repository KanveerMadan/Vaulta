// The browser's merchant model gives the same answers as the training code and the server: fixtures/
// merchant_model_parity.json is written by ml/export.py with the model, and backend/tests/test_categorizer.py checks
// the server against the same file.
import { existsSync, readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { ngrams, normalize, predict } from "./merchantModel.js";

const MODEL = new URL("../../public/models/merchant-model.json.gz", import.meta.url);
const PARITY = new URL("../../../fixtures/merchant_model_parity.json", import.meta.url);

describe("merchant model features", () => {
  it("normalizes like ml/features.py", () => {
    expect(normalize("UPI/412345/SWIGGY*Order@ybl - Pay")).toBe("upi 000000 swiggy order@ybl pay");
    expect(normalize("  ")).toBe("");
  });
  it("makes word-bounded character n-grams", () => {
    expect(ngrams("ab", 1, 3)).toEqual([" ", "a", "b", " ", " a", "ab", "b ", " ab", "ab "]);
  });
  it("predicts from a tiny model", () => {
    const tiny = { ngram_range: [1, 5], scale: 1, temperature: 1, bias: [0, 0], labels: ["food.cafe", "groceries.kirana"],
      idf: { kiran: 1 }, weights: { kiran: [1, 9] } };
    const p = predict(tiny, "RAJU KIRANA");
    expect(p.subcategory).toBe("groceries.kirana");
    expect(p.confidence).toBeCloseTo(1 / (1 + Math.exp(-9)), 12);
    expect(predict(tiny, "ZZZ")).toBeNull();
  });
});

describe("parity with ml/ and the server", () => {
  it("gives the recorded answers for the shipped model", () => {
    if (!existsSync(MODEL)) {
      expect(existsSync(PARITY)).toBe(false);   // no model shipped, so no fixture either
      return;
    }
    const model = JSON.parse(gunzipSync(readFileSync(MODEL)).toString("utf8"));
    const cases = JSON.parse(readFileSync(PARITY, "utf8"));
    expect(cases.length).toBeGreaterThanOrEqual(200);
    for (const c of cases) {
      const p = predict(model, c.text);
      expect(p?.subcategory, c.text).toBe(c.subcategory);
      expect(Math.abs(p.confidence - c.confidence)).toBeLessThan(1e-9);
    }
  });
  it("ships the same bytes as the server", () => {
    const server = new URL("../../../backend/app/data/merchant_model.json.gz", import.meta.url);
    expect(existsSync(MODEL)).toBe(existsSync(server));
    if (existsSync(MODEL)) expect(readFileSync(MODEL).equals(readFileSync(server))).toBe(true);
  });
});
