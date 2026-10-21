// Sends confirmed, sanitized rows to the server as JSON, in batches.
// This is the only network call in the import flow besides the column
// mapping template (indices + date format). No file or FormData is sent.

// The server accepts up to 500 rows a request, but each row costs it a dozen database round trips and a commit: on
// the free API a 200-row batch ran past the 20-second default timeout and the import failed (Oct 2026). 50 rows a
// request, each allowed 90 seconds, keeps every request far inside its limit.
export const BATCH_SIZE = 50;
export const BATCH_TIMEOUT_MS = 90_000;
const RETRY_DELAYS_MS = [2_000, 5_000]; // a batch is tried at most three times

const TOTAL_KEYS = ["imported", "duplicates_merged", "transfers_flagged", "rows_needing_review", "failed"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** No answer (timed out, connection dropped) or the API starting up or overloaded: worth sending the batch again. */
export function isTransient(err) {
  if (err?.code === "ERR_CANCELED") return false;
  return !err?.response || [502, 503, 504].includes(err.response.status);
}

/**
 * Re-sending after a failure is safe: the server derives an idempotency key
 * per row, so rows that already landed come back as duplicates_merged. So a
 * batch that timed out or met a waking API is sent again by itself (and by
 * lib/api.js after waking it: `idempotent`). A failure that remains carries
 * `saved` (rows saved before it) and `batchStart` (the failing batch's first row).
 * `importId` names this upload (one per file, the same on a retry) so it can be deleted on its own later.
 */
export async function sendRows(api, rows, { onProgress, importId = crypto.randomUUID(), pause = sleep } = {}) {
  const totals = Object.fromEntries(TOTAL_KEYS.map((k) => [k, 0]));
  for (let i = 0; i < rows.length; i += BATCH_SIZE) {
    const batch = rows.slice(i, i + BATCH_SIZE);
    const data = await sendBatch(api, { rows: batch, import_id: importId }, pause).catch((err) => {
      throw Object.assign(err ?? new Error("Import failed"), { saved: i, batchStart: i });
    });
    for (const k of TOTAL_KEYS) totals[k] += data[k] ?? 0;
    onProgress?.(i + batch.length, rows.length);
  }
  return totals;
}

async function sendBatch(api, body, pause) {
  for (let attempt = 0; ; attempt++) {
    try {
      const { data } = await api.post("/api/import/batch", body, { timeout: BATCH_TIMEOUT_MS, idempotent: true });
      return data;
    } catch (err) {
      if (!isTransient(err) || attempt >= RETRY_DELAYS_MS.length) throw err;
      await pause(RETRY_DELAYS_MS[attempt]);
    }
  }
}

/** What to tell the person when sendRows fails: the server's reason when there is one, never only "Import failed". */
export function importErrorMessage(err, total, online = typeof navigator === "undefined" || navigator.onLine) {
  const saved = err?.saved ?? 0;
  const after = saved > 0
    ? ` The first ${saved} of ${total} rows are saved; importing again skips them.`
    : " Nothing is lost: try again and already-saved rows are skipped.";
  const res = err?.response;
  const detail = res?.data?.detail;
  const ref = res?.data?.request_id ? ` (reference ${res.data.request_id})` : "";
  if (err?.code === "ERR_CANCELED") return `The import was interrupted.${after}`;
  if (!res && !online) return `You're offline.${after}`;
  if (!res && err?.code === "ECONNABORTED") return `vaulta.in took too long to answer, even after retrying.${after}`;
  if (!res) return `Couldn't reach vaulta.in.${after}`;
  if (Array.isArray(detail) && detail.length) {
    // 422 from the server's checks: loc is ["body", "rows", <index in the batch>, <field>]
    const [, , index, field] = detail[0].loc ?? [];
    const where = Number.isInteger(index) ? `Row ${(err.batchStart ?? 0) + index + 1}${field ? ` (${field})` : ""}: ` : "";
    return `${where}${detail[0].msg}.${after}`;
  }
  if ([502, 503, 504].includes(res.status)) return `vaulta.in is starting up or busy and didn't answer in time.${after}`;
  if (typeof detail === "string" && res.status < 500) return `${detail}${after}`;
  return `Something went wrong on our side${ref}.${after}`;
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
