// PDF text extraction with pdf.js, entirely in the browser.
// pdf.js gives positioned text items; we rebuild two views from them:
//   lines     — row-major: items on the same baseline, split into cells at
//               column gaps. Used for tables and card statements.
//   blockText — column blocks (vertically adjacent cells sharing a left edge),
//               ordered top-to-bottom then left-to-right. This reproduces the
//               order pymupdf's get_text() emits, which the Google Pay regex
//               (ported from the Python parser) depends on.

export class PdfPasswordError extends Error {
  constructor(incorrect) {
    super(incorrect ? "Incorrect password" : "Password required");
    this.incorrect = incorrect;
  }
}

/** Group positioned items ({str, x, y, w, h}) into lines of cells. y grows upward (PDF space). */
export function buildLines(items) {
  const sorted = items
    .filter((it) => it.str.trim())
    .sort((a, b) => b.y - a.y || a.x - b.x);
  const lines = [];
  for (const it of sorted) {
    const line = lines[lines.length - 1];
    if (line && Math.abs(line.y - it.y) <= Math.max(2, it.h * 0.5)) line.items.push(it);
    else lines.push({ y: it.y, h: it.h, items: [it] });
  }
  return lines.map(({ y, h, items: lineItems }) => {
    lineItems.sort((a, b) => a.x - b.x);
    const cells = [];
    for (const it of lineItems) {
      const cell = cells[cells.length - 1];
      const gap = cell ? it.x - cell.x1 : Infinity;
      if (cell && gap <= Math.max(it.h, 4) * 0.8) {
        cell.text += gap > it.h * 0.15 ? ` ${it.str}` : it.str;
        cell.x1 = Math.max(cell.x1, it.x + it.w);
      } else {
        cells.push({ x0: it.x, x1: it.x + it.w, text: it.str });
      }
    }
    cells.forEach((c) => { c.text = c.text.replace(/\s+/g, " ").trim(); });
    return { y, h, cells, text: cells.map((c) => c.text).join(" ") };
  });
}

/** pymupdf-like block ordering for one page's lines. */
export function blockText(lines) {
  const blocks = [];
  for (const line of lines) {
    for (const cell of line.cells) {
      const block = blocks.find((b) =>
        Math.abs(b.x0 - cell.x0) <= Math.max(line.h, 4) &&
        b.lastY - line.y <= line.h * 1.8 &&
        b.lastY > line.y);
      if (block) {
        block.texts.push(cell.text);
        block.lastY = line.y;
      } else {
        blocks.push({ x0: cell.x0, top: line.y, lastY: line.y, texts: [cell.text] });
      }
    }
  }
  blocks.sort((a, b) => b.top - a.top);
  const ordered = [];
  for (let i = 0; i < blocks.length;) {
    let j = i;
    while (j < blocks.length && blocks[i].top - blocks[j].top <= 3) j++;
    ordered.push(...blocks.slice(i, j).sort((a, b) => a.x0 - b.x0));
    i = j;
  }
  return ordered.map((b) => b.texts.join("\n")).join("\n");
}

function toItems(content) {
  return content.items
    .filter((it) => typeof it.str === "string")
    .map((it) => ({
      str: it.str,
      x: it.transform[4],
      y: it.transform[5],
      w: it.width,
      h: Math.hypot(it.transform[2], it.transform[3]) || it.height || 10,
    }));
}

/**
 * Extract text from PDF bytes. `pdfjs` is the pdfjs-dist module (browser or
 * legacy build). The password is used only to open the document here.
 * Returns {pages: [{lines}], text, lineTexts}.
 */
export async function extractPdf(data, { pdfjs, password } = {}) {
  let doc;
  try {
    doc = await pdfjs.getDocument({
      data: data instanceof Uint8Array ? data : new Uint8Array(data),
      password,
      isEvalSupported: false,
      disableFontFace: true,
    }).promise;
  } catch (e) {
    if (e?.name === "PasswordException") {
      throw new PdfPasswordError(e.code === pdfjs.PasswordResponses.INCORRECT_PASSWORD);
    }
    throw e;
  }
  const pages = [];
  try {
    for (let n = 1; n <= doc.numPages; n++) {
      const page = await doc.getPage(n);
      pages.push({ lines: buildLines(toItems(await page.getTextContent())) });
    }
  } finally {
    await doc.destroy();
  }
  return {
    pages,
    text: pages.map((p) => blockText(p.lines)).join("\n"),
    lineTexts: pages.flatMap((p) => p.lines.map((l) => l.text)),
  };
}
