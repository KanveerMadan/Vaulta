"""
Retrains Model A with consented user corrections (data/private/corrections.jsonl, from
backend/scripts/export_training_corrections.py) and keeps the new model only if it is at least as good on the frozen
test sets (the same unseen-merchant, unseen-local-shop and real test sets the shipped model was judged on, rebuilt
deterministically by `make data`).

A fifth of the corrections (by a hash of the text) never trains: it is a test set of labels people chose themselves,
the one human-verified signal available, reported as "agreement with user corrections".

    python retrain.py            # writes artifacts/retrain_report.json; on success also artifacts/merchant_model.json
                                 # and artifacts/metrics.json, then run `make export` to ship it
"""

from __future__ import annotations

import json

import dataset
import metrics as M
import model_a
from common import ARTIFACTS, PRIVATE, read_jsonl, stable_hash
from train import evaluate_split

TOLERANCE = 0.005      # the new model may not lose more than half a macro-F1 point on any frozen test set


def main() -> None:
    corrections = [r for r in read_jsonl(PRIVATE / "corrections.jsonl") if r.get("label")]
    if not corrections:
        print("No consented corrections in data/private/corrections.jsonl: nothing to retrain with.")
        return
    held = [r for r in corrections if stable_hash(r["text"].lower()) % 5 == 0]
    used = [r for r in corrections if stable_hash(r["text"].lower()) % 5 != 0]
    data = dataset.load()
    current = json.loads((ARTIFACTS / "metrics.json").read_text())
    old = model_a.Exported(json.loads((ARTIFACTS / "merchant_model.json").read_text()))

    exported, report = model_a.train(data["train"] + used, data["val"])
    exported["threshold"] = current["model_a"]["threshold"]           # same bar as the shipped model
    new = model_a.Exported(exported)

    def judge(model):
        out = {}
        for split in ("test", "test_local", "real_test"):
            rows = data[split]
            out[split] = evaluate_split(rows, [model.predict(r["text"]) for r in rows], exported["threshold"])["rules_then_model"]
        y = [r["label"] for r in held]
        out["user_corrections"] = M.score(y, [model.predict(r["text"])[0] for r in held]) if held else None
        return out

    before, after = judge(old), judge(new)
    worse = [s for s in ("test", "test_local", "real_test")
             if before[s]["macro_f1"] is not None and after[s]["macro_f1"] < before[s]["macro_f1"] - TOLERANCE]
    if held and after["user_corrections"]["agreement"] < before["user_corrections"]["agreement"]:
        worse.append("user_corrections")
    keep = not worse
    summary = {"corrections_used": len(used), "corrections_held_out": len(held), "keep": keep, "worse_on": worse,
               "before": {k: v and {m: v[m] for m in ("agreement", "macro_f1", "review_rate")} for k, v in before.items()},
               "after": {k: v and {m: v[m] for m in ("agreement", "macro_f1", "review_rate")} for k, v in after.items()},
               "training": report}
    (ARTIFACTS / "retrain_report.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    if keep:
        (ARTIFACTS / "merchant_model.json").write_text(json.dumps(exported, separators=(",", ":"), sort_keys=True))
        current["retrained_with_corrections"] = summary
        (ARTIFACTS / "metrics.json").write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: summary[k] for k in ("corrections_used", "corrections_held_out", "keep", "worse_on")}))


if __name__ == "__main__":
    main()
