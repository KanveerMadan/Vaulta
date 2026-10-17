// The merchant model, run in the browser (docs/ml/model-card.md). The same arithmetic as
// backend/app/services/categorizer.py and ml/model_a.py: character 1–5-gram TF-IDF + logistic regression with a
// temperature. backend/tests/test_categorizer.py and merchantModel.test.js check all three agree on the same strings.
// The model file is served from this site (public/models/), never a third party, and kept by the service worker.

const MODEL_URL = "/models/merchant-model.json.gz";

export function normalize(text) {
  return String(text || "").toLowerCase().replace(/[0-9]/g, "0").replace(/[^a-z0@&]+/g, " ").trim().split(/\s+/).filter(Boolean).join(" ");
}

export function ngrams(text, low = 1, high = 5) {
  const out = [];
  for (const word of normalize(text).split(" ")) {
    if (!word) continue;
    const w = ` ${word} `;
    for (let n = low; n <= high; n++) {
      if (n > w.length) break;
      for (let i = 0; i + n <= w.length; i++) out.push(w.slice(i, i + n));
    }
  }
  return out;
}

/** {subcategory, confidence, alternatives: [[id, p], …]} or null when no n-gram is known. */
export function predict(model, text) {
  const { idf, weights, scale, bias, labels, temperature } = model;
  const counts = new Map();
  for (const g of ngrams(text, model.ngram_range[0], model.ngram_range[1])) {
    if (Object.prototype.hasOwnProperty.call(idf, g)) counts.set(g, (counts.get(g) || 0) + 1);
  }
  if (!counts.size) return null;
  const vals = new Map();
  let sq = 0;
  for (const [g, c] of counts) {
    const v = (1 + Math.log(c)) * idf[g];
    vals.set(g, v);
    sq += v * v;
  }
  const norm = Math.sqrt(sq) || 1;
  const z = bias.slice();
  for (const [g, v] of vals) {
    const w = weights[g];
    const x = (v / norm) * scale;
    for (let k = 0; k < w.length; k += 2) z[w[k]] += x * w[k + 1];
  }
  const top = Math.max(...z);
  const e = z.map((v) => Math.exp((v - top) / temperature));
  const total = e.reduce((a, b) => a + b, 0);
  const ranked = e.map((p, i) => [p / total, i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  return {
    subcategory: labels[ranked[0][1]],
    confidence: ranked[0][0],
    alternatives: ranked.slice(0, 3).map(([p, i]) => [labels[i], p]),
  };
}

let loading = null;

/** The model, fetched once per page load (the service worker caches the file); null if it isn't available. */
export function loadModel() {
  if (!loading) {
    loading = (async () => {
      try {
        const res = await fetch(MODEL_URL);
        if (!res.ok || typeof DecompressionStream === "undefined") return null;
        const text = await new Response(res.body.pipeThrough(new DecompressionStream("gzip"))).text();
        return JSON.parse(text);
      } catch {
        return null;            // no model: the server categorises with its own copy, or the rules alone
      }
    })();
  }
  return loading;
}
