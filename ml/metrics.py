"""
Metrics, all measured against teacher labels (this is distillation; no human-verified labels exist):

  agreement        top-1 agreement with the teacher over all rows (an abstention counts as disagreement)
  macro_f1         macro-F1 over the subcategories present in the set; abstentions are a "none" prediction
  covered_agreement agreement over the rows the system categorised (not sent to review)
  review_rate      share of rows sent to review (the uncategorised rate)
  ece              expected calibration error of the confidence (15 equal-width bins), model only
"""

from __future__ import annotations

import sys
from collections import Counter

import numpy as np
from sklearn.metrics import f1_score

from common import ROOT

sys.path.insert(0, str(ROOT / "backend"))
from app.services.merchant_normalizer import normalize  # noqa: E402  (the current rule-based system)

NONE = "__none__"


def rules_predict(text: str):
    """What the app does today: a normalizer pattern ⇒ its subcategory (confidence ≥ 0.5), else review."""
    n = normalize(text)
    return (n.subcategory, n.confidence) if n.confidence >= 0.5 and n.subcategory else (None, 0.0)


def known_merchant(text: str):
    """The shipped order's known-merchant step: the same patterns, on the merchant's own words (resolver.merchant_text)."""
    from resolver import merchant_text
    n = normalize(merchant_text(text))
    return (n.subcategory, n.confidence) if n.confidence >= 0.5 and n.subcategory else (None, 0.0)


def score(y_true: list[str], y_pred: list) -> dict:
    if not y_true:
        return {"rows": 0, "agreement": None, "macro_f1": None, "covered_agreement": None, "review_rate": None,
                "per_class_f1": {}}
    pred = [p or NONE for p in y_pred]
    present = sorted(set(y_true))
    covered = [(t, p) for t, p in zip(y_true, y_pred) if p]
    per_class = f1_score(y_true, pred, labels=present, average=None, zero_division=0)
    return {
        "rows": len(y_true),
        "agreement": round(float(np.mean([t == p for t, p in zip(y_true, pred)])), 4) if y_true else None,
        "macro_f1": round(float(f1_score(y_true, pred, labels=present, average="macro", zero_division=0)), 4) if y_true else None,
        "covered_agreement": round(float(np.mean([t == p for t, p in covered])), 4) if covered else None,
        "review_rate": round(1 - len(covered) / len(y_true), 4) if y_true else None,
        "per_class_f1": {c: round(float(f), 4) for c, f in zip(present, per_class)},
    }


def ece(conf: list[float], correct: list[bool], bins: int = 15) -> float:
    conf, correct = np.array(conf), np.array(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return round(float(total), 4)


def system(texts, model_preds, threshold, use_rules=True):
    """The shipped order: a known merchant (on its own words) first, then the model above `threshold`, else review."""
    out = []
    for text, (label, conf) in zip(texts, model_preds):
        r, _ = known_merchant(text) if use_rules else (None, 0)
        out.append(r or (label if conf >= threshold else None))
    return out


def model_only_threshold(y_true, model_preds, target: float) -> float:
    """The lowest threshold at which the rows the model itself files agree with the teacher at least `target`."""
    for t in np.round(np.arange(0.0, 1.0001, 0.01), 2):
        kept = [(p, y) for (p, c), y in zip(model_preds, y_true) if c >= t]
        if kept and np.mean([p == y for p, y in kept]) >= target:
            return float(t)
    return 1.0


def curve(y_true, model_preds, texts, thresholds, use_rules) -> list[dict]:
    rows = []
    for t in thresholds:
        s = score(y_true, system(texts, model_preds, t, use_rules))
        rows.append({"threshold": round(float(t), 3), "coverage": round(1 - s["review_rate"], 4),
                     "covered_agreement": s["covered_agreement"], "macro_f1": s["macro_f1"]})
    return rows


def pick_threshold(y_true, model_preds, texts, target: float, use_rules=True) -> float:
    """The lowest threshold whose covered agreement on these (validation) rows is at least `target`."""
    for t in np.round(np.arange(0.0, 1.0001, 0.01), 2):
        s = score(y_true, system(texts, model_preds, t, use_rules))
        if s["covered_agreement"] is not None and s["covered_agreement"] >= target:
            return float(t)
    return 1.0


def label_counts(rows) -> dict:
    return dict(Counter(r["label"] for r in rows))
