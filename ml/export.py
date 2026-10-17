"""
Ships the trained model, if (and only if) artifacts/metrics.json says it met the ship criteria:

  backend/app/data/merchant_model.json.gz      server inference (services/categorizer.py)
  frontend/public/models/merchant-model.json.gz browser inference (src/lib/merchantModel.js), the same bytes
  backend/app/data/merchant_index.json          merchant resolution
  fixtures/merchant_model_parity.json           strings + the answers ml/ gives, which the backend and browser tests
                                                must reproduce (tests/test_categorizer.py, merchantModel.test.js)

If the model doesn't ship, the shipped copies are removed, so the app keeps the rule-based categories.
"""

from __future__ import annotations

import gzip
import json

from common import ARTIFACTS, ROOT, read_jsonl, DATA
import metrics as M
import resolver
from model_a import Exported

BACKEND = ROOT / "backend" / "app" / "data"
FRONTEND = ROOT / "frontend" / "public" / "models"
PARITY = ROOT / "fixtures" / "merchant_model_parity.json"
PARITY_CASES = 250


def main() -> None:
    metrics = json.loads((ARTIFACTS / "metrics.json").read_text())
    targets = [BACKEND / "merchant_model.json.gz", FRONTEND / "merchant-model.json.gz", BACKEND / "merchant_index.json", PARITY]
    if not metrics["ships"] or metrics["choice"] != "model_a":
        for t in targets:
            t.unlink(missing_ok=True)
        print(f"Not shipping ({metrics['choice']}, ships={metrics['ships']}): shipped copies removed; the rules stay.")
        return
    raw = (ARTIFACTS / "merchant_model.json").read_text()
    blob = gzip.compress(raw.encode(), compresslevel=9, mtime=0)
    FRONTEND.mkdir(parents=True, exist_ok=True)
    for t in targets[:2]:
        t.write_bytes(blob)
    (BACKEND / "merchant_index.json").write_text((ARTIFACTS / "merchant_index.json").read_text())

    model = Exported(json.loads(raw))
    index_data = json.loads((ARTIFACTS / "merchant_index.json").read_text())
    index = resolver.Index(index_data["names"])
    rows = [r for r in read_jsonl(DATA / "narrations.jsonl") if r["split"] in ("test", "test_local")]
    step = max(1, len(rows) // PARITY_CASES)
    cases = []
    for r in rows[::step][:PARITY_CASES]:
        label, conf = model.predict(r["text"])
        name, score = index.resolve(r["text"])
        cases.append({"text": r["text"], "subcategory": label, "confidence": conf,
                      "known_merchant": M.known_merchant(r["text"])[0],
                      "resolved": name if score >= index_data["threshold"] else None})
    PARITY.write_text(json.dumps(cases, indent=0) + "\n")
    print(f"Shipped Model A ({len(blob) / 1e6:.2f} MB gzipped) and {len(cases)} parity cases.")


if __name__ == "__main__":
    main()
