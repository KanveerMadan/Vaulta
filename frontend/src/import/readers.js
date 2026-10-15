// File → cells, in the browser. Nothing here touches the network.
import Papa from "papaparse";

/** UTF-8 (BOM stripped), falling back to Windows-1252 like the Python parser. */
export function decodeText(buffer) {
  const bytes = new Uint8Array(buffer);
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/^\uFEFF/, "");
  } catch {
    return new TextDecoder("windows-1252").decode(bytes);
  }
}

export function parseCsvText(text) {
  return Papa.parse(text, { skipEmptyLines: "greedy" }).data;
}

const pad = (n) => String(n).padStart(2, "0");

/** First sheet as rows of strings. Date cells become DD/MM/YYYY; numbers stay raw. */
export async function readSpreadsheet(buffer) {
  const XLSX = await import("xlsx");
  const wb = XLSX.read(new Uint8Array(buffer), { type: "array", cellNF: true });
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!ws || !ws["!ref"]) return [];
  const range = XLSX.utils.decode_range(ws["!ref"]);
  const rows = [];
  for (let r = range.s.r; r <= range.e.r; r++) {
    const row = [];
    for (let c = range.s.c; c <= range.e.c; c++) {
      const cell = ws[XLSX.utils.encode_cell({ r, c })];
      if (!cell) row.push("");
      else if (cell.t === "n" && cell.z && XLSX.SSF.is_date(cell.z)) {
        const d = XLSX.SSF.parse_date_code(cell.v);
        row.push(`${pad(d.d)}/${pad(d.m)}/${d.y}`);
      } else if (cell.t === "n") row.push(String(cell.v));
      else row.push(cell.w ?? String(cell.v ?? ""));
    }
    if (row.some((v) => String(v).trim())) rows.push(row);
  }
  return rows;
}

/** pdf.js for the browser, loaded on demand so it isn't in the main bundle. */
export async function loadPdfjs() {
  const pdfjs = await import("pdfjs-dist");
  const { default: workerUrl } = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
  return pdfjs;
}
