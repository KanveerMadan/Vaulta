"""
Peak memory with the merchant model loaded, and how long a 12-month import takes (go-live stage 1). Opt-in, because
it times things: MEASURE_PERF=1 python -m pytest tests/test_model_performance.py -s (MEASURE_MODEL=0 for the same
import with the model off)

12 months × 200 transactions, in the API's largest batches (500 rows, as the browser sends them), through
/api/import/batch with the shipped model and no on-device predictions (the server predicts every row: the worst
case). Narrations come from the merchant model's fresh frozen test set (synthetic, stripped), mostly merchants the
model has never seen. Memory is this process's peak RSS, which includes pytest itself: an upper bound for the API.
"""

import gc
import json
import os
import resource
import sys
import time
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import categorizer
from tests.conftest import as_user

pytestmark = pytest.mark.skipif(os.environ.get("MEASURE_PERF") != "1", reason="set MEASURE_PERF=1 to measure")
ROOT = Path(__file__).resolve().parents[2]
ALICE = as_user("alice")
MONTHS, PER_MONTH, BATCH = 12, 200, 500


def peak_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)       # bytes on macOS, KiB on Linux


def rows() -> list[dict]:
    texts = [json.loads(l)["text"] for l in (ROOT / "ml" / "data" / "fresh_test.jsonl").read_text().splitlines()]
    out = []
    for i in range(MONTHS * PER_MONTH):
        month, day = 1 + i // PER_MONTH, 1 + i % 28
        out.append({"date": f"2025-{month:02d}-{day:02d}", "description_raw": texts[i % len(texts)][:200],
                    "amount": f"{100 + i % 900}.00", "direction": "debit", "reference": f"{410000000000 + i}",
                    "source_type": "bank_csv", "source_label": "HDFC Bank", "type": "transaction"})
    return out


def test_memory_and_twelve_month_import(client, monkeypatch):
    with_model = os.environ.get("MEASURE_MODEL", "1") == "1"            # MEASURE_MODEL=0: the same import without it
    monkeypatch.setattr(settings, "MERCHANT_MODEL_ENABLED", with_model)
    categorizer.model.cache_clear()
    categorizer._index.cache_clear()
    gc.collect()
    before = peak_mb()
    started = time.perf_counter()
    if with_model:
        assert categorizer.enabled()                   # loads the shipped model and index
        categorizer.predict("WARM UP")
        categorizer.resolve_merchant("WARM UP")
    load_s = time.perf_counter() - started
    after_load = peak_mb()

    data, timings = rows(), []
    for start in range(0, len(data), BATCH):
        t = time.perf_counter()
        res = client.post("/api/import/batch", json={"rows": data[start:start + BATCH]}, headers=ALICE)
        assert res.status_code == 200, res.text
        timings.append(time.perf_counter() - t)
    filed = sum(1 for t in client.get("/api/transactions?page_size=200", headers=ALICE).json()["items"] if t["category"])
    result = {"model": with_model, "rows": len(data), "batches": len(timings), "total_seconds": round(sum(timings), 2),
              "slowest_batch_seconds": round(max(timings), 2), "model_load_seconds": round(load_s, 2),
              "peak_rss_mb_before_model": before, "peak_rss_mb_after_model": after_load,
              "peak_rss_mb_after_import": peak_mb(), "categorised_in_first_200": filed}
    print("\nMODEL_PERF " + json.dumps(result))
    out = ROOT / "ml" / "artifacts" / "api_perf.json"                       # read by ml/report.py
    saved = json.loads(out.read_text()) if out.exists() else {}
    saved["with_model" if with_model else "without_model"] = {**result, "platform": sys.platform}
    out.write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")
