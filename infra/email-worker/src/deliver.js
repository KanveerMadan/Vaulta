// POST one alert to the API, waiting out a cold start. The API sleeps when idle (no keep-awake) and takes up to about
// a minute to start, so a refused connection or a 502/503/504 is retried with backoff (2, 4, 8, 16, 30, 30… s) for
// up to ~2 minutes. If it still isn't up, deliver() throws and the worker run fails, which Email Routing reports
// as a failed delivery (whether the bank's mail server then retries is checked in go-live stage 7; the API being
// down for 2+ minutes is an outage either way). A 4xx is the API's real answer (bad secret, unknown address) and
// isn't retried.
export const DEADLINE_MS = 120_000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function deliver(payload, env, { fetchFn = fetch, pause = sleep, now = Date.now } = {}) {
  const url = `${env.API_URL.replace(/\/$/, "")}/internal/inbound-email`;
  const start = now();
  for (let delay = 2000; ; delay = Math.min(delay * 2, 30_000)) {
    let status;
    try {
      const res = await fetchFn(url, {
        method: "POST",
        headers: { "content-type": "application/json", "x-internal-secret": env.INTERNAL_SECRET },
        body: JSON.stringify(payload),
      });
      status = res.status;
      if (![502, 503, 504].includes(status) && status < 500) return status;
      if (status >= 500 && ![502, 503, 504].includes(status)) throw new Error(`Vaulta API ${status}`);   // a real error
    } catch (err) {
      if (status) throw err;                // the 500 above
    }
    if (now() - start >= DEADLINE_MS) throw new Error(`Vaulta API not reachable after ${DEADLINE_MS / 1000}s`);
    await pause(delay);
  }
}
