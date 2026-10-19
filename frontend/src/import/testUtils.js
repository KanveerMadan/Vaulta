// Test helpers (Node only): fixture files and the pdf.js legacy build.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";

const FIXTURES = new URL("../../../fixtures/statements/", import.meta.url);

pdfjs.GlobalWorkerOptions.workerSrc = fileURLToPath(
  new URL("../../node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs", import.meta.url),
);

export { pdfjs };

export function fixtureFile(name) {
  return new File([readFileSync(new URL(name, FIXTURES))], name);
}

export const expected = JSON.parse(readFileSync(new URL("expected.json", FIXTURES), "utf8"));

export const pick = (row, keys) => Object.fromEntries(keys.map((k) => [k, row[k]]));
