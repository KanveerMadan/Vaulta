// Sends confirmed, sanitized rows to the server as JSON, in batches.
// This is the only network call in the import flow besides the column
// mapping template (indices + date format). No file or FormData is sent.

export const BATCH_SIZE = 200; // server accepts up to 500 per request

const TOTAL_KEYS = ["imported", "duplicates_merged", "transfers_flagged", "rows_needing_review", "failed"];

/**
 * Re-sending after a failure is safe: the server derives an idempotency key
 * per row, so rows that already landed come back as duplicates_merged.
 * `importId` names this upload (one per file, the same on a retry) so it can be deleted on its own later.
 */
export async function sendRows(api, rows, { onProgress, importId = crypto.randomUUID() } = {}) {
  const totals = Object.fromEntries(TOTAL_KEYS.map((k) => [k, 0]));
  for (let i = 0; i < rows.length; i += BATCH_SIZE) {
    const batch = rows.slice(i, i + BATCH_SIZE);
    const { data } = await api.post("/api/import/batch", { rows: batch, import_id: importId });
    for (const k of TOTAL_KEYS) totals[k] += data[k] ?? 0;
    onProgress?.(i + batch.length, rows.length);
  }
  return totals;
}

export async function loadTemplate(api, fingerprint) {
  try {
    const { data } = await api.get(`/api/import/templates/${fingerprint}`);
    return data;
  } catch (err) {
    if (err?.response?.status === 404) return null;
    throw err;
  }
}

export async function saveTemplate(api, fingerprint, { columnCount, sourceType, mapping }) {
  await api.put(`/api/import/templates/${fingerprint}`, {
    column_count: columnCount,
    source_type: sourceType,
    mapping,
  });
}
