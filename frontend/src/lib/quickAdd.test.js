import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { guessCategory, parseQuickAdd } from "./quickAdd.js";

// Shared with the server port (backend/app/services/quick_add.py)
const shared = JSON.parse(readFileSync(new URL("../../../fixtures/quick_add_cases.json", import.meta.url), "utf8"));
const [y, m, d] = shared.today.split("-").map(Number);
const TODAY = new Date(y, m - 1, d);

describe("parseQuickAdd (shared cases)", () => {
  it.each(shared.cases)("%s", (text, expected) => {
    expect(parseQuickAdd(text, TODAY)).toEqual(expected);
  });
});

describe("guessCategory", () => {
  it("finds the first known keyword", () => {
    expect(guessCategory(["big", "bazaar", "groceries"])).toBe("Groceries");
    expect(guessCategory(["unknown"])).toBeNull();
  });
});
