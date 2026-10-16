import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { TRUST } from "./trust";

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

  it("states exactly the five trust claims", () => {
    expect(TRUST.map((t) => t.claim)).toEqual([
      "Statements are processed on your device and never uploaded.",
      "Account numbers, balances and passwords are never stored.",
      "Raw alert emails are never stored.",
      "The AI never sees bank narrations or UPI IDs.",
      "Delete everything, anytime.",
    ]);
  });
});
