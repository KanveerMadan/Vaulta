// Copy tesseract.js's worker, wasm core and English model into public/ocr so
// OCR loads only from Vaulta's own origin (see OCR_ASSETS in src/import/ocr.js).
// Runs before `dev` and `build`; public/ocr is generated, not committed.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

export const OCR_FILES = {
  "worker.min.js": "tesseract.js/dist/worker.min.js",
  // OEM 1 (LSTM only) loads one of these, depending on SIMD support
  "core/tesseract-core-lstm.wasm.js": "tesseract.js-core/tesseract-core-lstm.wasm.js",
  "core/tesseract-core-simd-lstm.wasm.js": "tesseract.js-core/tesseract-core-simd-lstm.wasm.js",
  "lang/eng.traineddata.gz": "@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz",
};

const root = new URL("../", import.meta.url);
export function copyOcrAssets() {
  for (const [dest, src] of Object.entries(OCR_FILES)) {
    const to = fileURLToPath(new URL(`public/ocr/${dest}`, root));
    mkdirSync(dirname(to), { recursive: true });
    copyFileSync(fileURLToPath(new URL(`node_modules/${src}`, root)), to);
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) copyOcrAssets();
