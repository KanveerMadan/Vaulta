// OCR for scanned PDFs and photos, in the browser (tesseract.js). The image
// never leaves the device. OCR words become the same positioned items
// pdf.js produces, so table reconstruction and column mapping are reused.
//
// The worker, wasm core and English model are served from Vaulta's own
// origin (copied into public/ocr by scripts/copy-ocr-assets.mjs); tesseract
// is configured to load nothing from anywhere else.

export const OCR_ASSETS = {
  workerPath: "/ocr/worker.min.js",
  corePath: "/ocr/core",
  langPath: "/ocr/lang",
  workerBlobURL: false,   // load the worker script directly from our origin
  gzip: true,
};

// Rows containing a word below this confidence are flagged for the user to
// check in the preview (listed in the Phase 2 report as a tunable threshold).
export const LOW_CONFIDENCE = 70;

/** tesseract words → items for buildLines (y grows upward, so negate the image y). */
export function wordsToItems(words) {
  return words
    .filter((w) => w.text && w.text.trim())
    .map((w) => ({
      str: w.text,
      x: w.bbox.x0,
      y: -w.bbox.y1,
      w: w.bbox.x1 - w.bbox.x0,
      h: w.bbox.y1 - w.bbox.y0,
      conf: w.confidence,
    }));
}

/** An OCR engine: {recognize(image) → items, terminate()}. */
export async function createOcr(createWorker, workerOptions = {}) {
  const worker = await createWorker("eng", 1, workerOptions);
  return {
    async recognize(image) {
      const { data } = await worker.recognize(image, {}, { blocks: true });
      const words = (data.blocks || []).flatMap((b) => b.paragraphs.flatMap((p) => p.lines.flatMap((l) => l.words)));
      return wordsToItems(words);
    },
    terminate: () => worker.terminate(),
  };
}

export async function browserOcr(createWorker = null) {
  const create = createWorker || (await import("tesseract.js")).createWorker;
  return createOcr(create, OCR_ASSETS);
}

/** Render a pdf.js page to a canvas for OCR (browser only). */
export async function renderPageToCanvas(page, scale = 2) {
  const viewport = page.getViewport({ scale });
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  return canvas;
}
