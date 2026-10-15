// Rebuild a transaction table from a PDF's positioned lines (bank account
// statements). Columns come from the header row's cell positions; each later
// cell goes to the column whose centre is nearest. A line with nothing in the
// date column but text in the description column continues the previous
// row's narration (multi-line narrations are common). Everything else that
// isn't a dated row — preamble, totals, footers — is dropped.

const HEADER_GROUPS = {
  date: /\b(date|dt)\b/i,
  description: /narration|description|particulars|remarks|details/i,
  debit: /withdrawal|debit/i,
  credit: /deposit|credit/i,
  balance: /balance/i,
  amount: /amount/i,
};

function headerGroups(line) {
  const found = new Set();
  for (const cell of line.cells) {
    for (const [group, re] of Object.entries(HEADER_GROUPS)) if (re.test(cell.text)) found.add(group);
  }
  return found;
}

/** A bank transaction table needs a date, a description, and a balance or both debit and credit. */
export function isBankHeader(line) {
  const g = headerGroups(line);
  return g.has("date") && g.has("description") && (g.has("balance") || (g.has("debit") && g.has("credit")));
}

/** Looser check, for offering column mapping on unknown layouts. */
export function isAnyHeader(line) {
  return headerGroups(line).size >= 3;
}

export const looksLikeDate = (s) =>
  /^\d{1,2}[/\-. ](\d{1,2}|[A-Za-z]{3,9})[/\-. ,']*\d{2,4}\b/.test(s.trim()) || /^\d{4}-\d{2}-\d{2}/.test(s.trim());

function nearestColumn(centres, x) {
  let best = 0;
  centres.forEach((c, i) => { if (Math.abs(c - x) < Math.abs(centres[best] - x)) best = i; });
  return best;
}

/** pages: [{lines}] from extractPdf. Returns {header, rows} or null. */
export function reconstructTable(pages, isHeader = isBankHeader) {
  let header = null;
  let centres = null;
  const rows = [];
  for (const { lines } of pages) {
    let last = null;
    let lastY = null;
    for (const line of lines) {
      if (isHeader(line)) {
        if (!header) header = line.cells.map((c) => c.text);
        centres = line.cells.map((c) => (c.x0 + c.x1) / 2);
        last = null;
        continue;
      }
      if (!centres) continue;
      const cells = header.map(() => "");
      for (const cell of line.cells) {
        const i = nearestColumn(centres, (cell.x0 + cell.x1) / 2);
        cells[i] = cells[i] ? `${cells[i]} ${cell.text}` : cell.text;
      }
      const dateCol = header.findIndex((h) => HEADER_GROUPS.date.test(h));
      const descCol = header.findIndex((h) => HEADER_GROUPS.description.test(h));
      if (looksLikeDate(cells[dateCol] || "")) {
        last = cells;
        rows.push(cells);
        lastY = line.y;
      } else if (
        last && descCol >= 0 && cells[descCol] &&
        cells.every((c, i) => i === descCol || !c) &&
        lastY - line.y <= line.h * 2.5
      ) {
        last[descCol] = `${last[descCol]} ${cells[descCol]}`.trim();
        lastY = line.y;
      } else {
        last = null;
      }
    }
  }
  return header && rows.length ? { header, rows } : null;
}
