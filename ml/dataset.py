"""
Joins narrations with teacher labels and returns the splits. Ambiguous teacher labels are excluded everywhere.

  train, val       synthetic narrations of train / val merchants
  test             synthetic narrations of unseen catalogue merchants (main test set)
  test_local       synthetic narrations of local shops with name stems never seen in train or val
  real_test        stripped real narrations (data/private/, only when local-statements/ had files)

load_fresh() returns the fresh frozen test set (fresh.py), kept apart: evaluation only, never training or tuning.
"""

from __future__ import annotations

from common import DATA, PRIVATE, read_jsonl

SPLITS = ("train", "val", "test", "test_local", "real_test")


def load() -> dict[str, list[dict]]:
    labels = {r["merchant"]: r for r in read_jsonl(DATA / "labels.jsonl")}
    out = {s: [] for s in SPLITS}
    for r in read_jsonl(DATA / "narrations.jsonl"):
        lab = labels.get(r["merchant"])
        if lab and lab["label"] != "ambiguous":
            out[r["split"]].append({**r, "label": lab["label"]})
    for r in read_jsonl(PRIVATE / "real_labels.jsonl"):
        if r["label"] != "ambiguous":
            out["real_test"].append({"text": r["text"], "label": r["label"], "split": "real_test", "source": "real",
                                     "merchant": None, "kind": "real"})
    return out


FRESH_SPLITS = ("fresh_brands", "fresh_local")


def load_fresh() -> dict[str, list[dict]]:
    out = {s: [] for s in FRESH_SPLITS}
    for r in read_jsonl(DATA / "fresh_test.jsonl"):
        if r["label"] != "ambiguous":
            out["fresh_brands" if r["kind"] == "brand" else "fresh_local"].append({**r, "source": "synthetic", "split": "fresh"})
    return out
