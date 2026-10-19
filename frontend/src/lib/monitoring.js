// Error monitoring with Sentry (go-live stage 4): errors only, scrubbed in the browser before anything is sent.
// Off unless VITE_SENTRY_DSN is set, and then loaded after the page, so it costs nothing up front. No tracing, no
// session replay, no default PII. scrubEvent / scrubBreadcrumb keep the error type, the code's stack frames and the
// page's path, and remove request data, headers, query strings, the user and extras; from free text they remove emails
// and UPI IDs, amounts, long numbers and anything quoted. Click and console breadcrumbs lose their text entirely: a
// button's label can be a merchant or a person ("More for UPI-PRIYA…"). Mirrors backend/app/core/monitoring.py.

const TEXT = [
  [/[\w.+-]+@[\w-]+(?:\.[\w-]+)*/g, "[email-or-upi]"],
  [/(?:₹|\bINR|\bRs\.?)\s*-?[\d,]+(?:\.\d+)?/gi, "[amount]"],
  [/(?<![\w.])-?\d[\d,]*\.\d{1,2}(?!\d)/g, "[amount]"],
  [/\d{4,}/g, "[number]"],
  [/'[^']*'|"[^"]*"|`[^`]*`/g, "'[text]'"],
];

export function scrubText(text) {
  if (typeof text !== "string") return text;
  return TEXT.reduce((t, [re, to]) => t.replace(re, to), text);
}

function pathOnly(url) {
  if (typeof url !== "string") return undefined;
  try {
    const u = new URL(url, "https://x.invalid");
    return url.startsWith("/") ? u.pathname : `${u.origin}${u.pathname}`;
  } catch {
    return undefined;
  }
}

export function scrubBreadcrumb(crumb) {
  if (["console", "ui.click", "ui.input"].includes(crumb.category)) {
    return { category: crumb.category, level: crumb.level, timestamp: crumb.timestamp };
  }
  const d = crumb.data || {};
  const data = Object.fromEntries(Object.entries({ method: d.method, status_code: d.status_code, url: pathOnly(d.url),
    from: pathOnly(d.from), to: pathOnly(d.to) }).filter(([, v]) => v !== undefined));
  return { type: crumb.type, category: crumb.category, level: crumb.level, timestamp: crumb.timestamp,
    message: scrubText(crumb.message), data };
}

export function scrubEvent(event) {
  const out = { ...event };
  out.request = out.request?.url ? { url: pathOnly(out.request.url) } : undefined;
  delete out.user;
  delete out.extra;
  out.contexts = Object.fromEntries(Object.entries(out.contexts || {}).filter(([k]) => ["browser", "os", "device"].includes(k)));
  if (out.exception?.values) {
    out.exception = { values: out.exception.values.map((x) => ({ ...x, value: scrubText(x.value),
      stacktrace: x.stacktrace && { frames: (x.stacktrace.frames || []).map(({ vars, ...frame }) => frame) } })) };   // eslint-disable-line no-unused-vars
  }
  if (out.message) out.message = scrubText(out.message);
  if (out.breadcrumbs) out.breadcrumbs = out.breadcrumbs.map(scrubBreadcrumb);
  return out;
}

export function startMonitoring(dsn = import.meta.env.VITE_SENTRY_DSN) {
  if (!dsn) return false;
  const start = () => import("@sentry/browser").then((Sentry) => Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    integrations: (defaults) => defaults.filter((i) => !["BrowserTracing", "Replay", "ReplayCanvas", "Feedback", "BrowserSession"].includes(i.name)),
    beforeSend: scrubEvent,
    beforeBreadcrumb: scrubBreadcrumb,
  })).catch(() => {});
  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, { once: true });
  return true;
}
