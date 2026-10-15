// Build the JSON Vaulta's API receives for one email. Pure, so it's testable
// without the Workers runtime. Attachments are dropped; the whole payload is
// kept under MAX_BYTES by trimming the HTML first, then the text.

export const MAX_BYTES = 256 * 1024;

const size = (obj) => new TextEncoder().encode(JSON.stringify(obj)).length;

export function buildPayload({ to, from, subject, text, html, authResults }) {
  const payload = {
    to: to || "",
    from: from || "",
    subject: (subject || "").slice(0, 1000),
    text: text || null,
    html: html || null,
    auth_results: (authResults || "").slice(0, 8000),
  };
  for (const field of ["html", "text"]) {
    while (payload[field] && size(payload) > MAX_BYTES) {
      const over = size(payload) - MAX_BYTES;
      payload[field] = payload[field].slice(0, Math.max(0, payload[field].length - over - 1024)) || null;
    }
  }
  return size(payload) > MAX_BYTES ? null : payload;
}
