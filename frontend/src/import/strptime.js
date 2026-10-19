// Subset of Python's datetime.strptime, so the ported parsers can reuse the
// exact format strings from the Python reference (backend/tests/reference/).
// Same directive regexes as CPython's _strptime, whitespace in the format
// matches \s+, case-insensitive, whole string must match.

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

const DIRECTIVES = {
  d: "(?<d>3[01]|[12]\\d|0[1-9]|[1-9]| [1-9])",
  m: "(?<m>1[0-2]|0[1-9]|[1-9])",
  y: "(?<y>\\d\\d)",
  Y: "(?<Y>\\d\\d\\d\\d)",
  H: "(?<H>2[0-3]|[0-1]\\d|\\d)",
  I: "(?<I>1[0-2]|0[1-9]|[1-9])",
  M: "(?<M>[0-5]\\d|\\d)",
  S: "(?<S>6[0-1]|[0-5]\\d|\\d)",
  p: "(?<p>am|pm)",
  b: `(?<b>${MONTHS.join("|")})`,
};

const cache = new Map();

function compile(format) {
  if (cache.has(format)) return cache.get(format);
  let src = "";
  for (let i = 0; i < format.length; i++) {
    const ch = format[i];
    if (ch === "%" && i + 1 < format.length) {
      const key = format[++i];
      if (!DIRECTIVES[key]) throw new Error(`Unsupported strptime directive %${key}`);
      src += DIRECTIVES[key];
    } else if (/\s/.test(ch)) {
      while (i + 1 < format.length && /\s/.test(format[i + 1])) i++;
      src += "\\s+";
    } else {
      src += ch.replace(/[.*+?^${}()|[\]\\/-]/g, "\\$&");
    }
  }
  // every literal character is escaped above
  // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
  const re = new RegExp(`^${src}$`, "i");
  cache.set(format, re);
  return re;
}

/** Returns {year, month, day, hour, minute, second} or null if `raw` doesn't match `format`. */
export function strptime(raw, format) {
  const m = compile(format).exec(raw);
  if (!m) return null;
  const g = m.groups;
  let year = 1900;
  if (g.Y) year = Number(g.Y);
  else if (g.y) year = Number(g.y) < 69 ? 2000 + Number(g.y) : 1900 + Number(g.y);
  const month = g.m ? Number(g.m) : g.b ? MONTHS.indexOf(g.b.toLowerCase()) + 1 : 1;
  const day = g.d ? Number(g.d.trim()) : 1;
  let hour = g.H ? Number(g.H) : 0;
  if (g.I) {
    hour = Number(g.I) % 12;
    if (g.p && g.p.toLowerCase() === "pm") hour += 12;
  }
  const minute = g.M ? Number(g.M) : 0;
  const second = g.S ? Number(g.S) : 0;
  // Reject impossible dates (31/02) like datetime() does
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) return null;
  return { year, month, day, hour, minute, second };
}

/** Try each format in order (Python `_parse_date`). */
export function parseDate(raw, formats) {
  const s = raw.trim();
  for (const f of formats) {
    const parsed = strptime(s, f);
    if (parsed) return parsed;
  }
  return null;
}

const pad = (n, w = 2) => String(n).padStart(w, "0");

/** "YYYY-MM-DD", or "YYYY-MM-DDTHH:MM:SS" when withTime. */
export function formatDate(p, withTime = false) {
  const d = `${pad(p.year, 4)}-${pad(p.month)}-${pad(p.day)}`;
  return withTime ? `${d}T${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}` : d;
}
