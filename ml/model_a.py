"""
Model A: character n-gram (1–5) TF-IDF + multinomial logistic regression, compressed for the browser.

Training: fit on train, pick C on val (macro-F1). Compression: keep the n-grams that carry the most weight for some
class (KEEP_PER_CLASS per class), refit on that vocabulary, quantize weights to int8 (one scale), drop zeros.
Calibration: one temperature, fit on val (negative log-likelihood).

The exported dict is exactly what ships (artifacts/merchant_model.json), and `Exported` below is its inference;
evaluation uses `Exported`, so the numbers are for the shipped model, not the uncompressed one.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from common import SEED
from features import MAX_N, MIN_N, ngrams

C_GRID = (3.0, 10.0, 30.0)
KEEP_PER_CLASS = 400


def _vectorizer(vocabulary=None) -> TfidfVectorizer:
    return TfidfVectorizer(analyzer=ngrams, sublinear_tf=True, min_df=1 if vocabulary else 2, vocabulary=vocabulary,
                           dtype=np.float64)


def _fit(texts, y, C, vocabulary=None):
    vec = _vectorizer(vocabulary)
    X = vec.fit_transform(texts)
    clf = LogisticRegression(C=C, max_iter=3000, random_state=SEED)
    clf.fit(X, y)
    return vec, clf


def train(train_rows, val_rows) -> tuple[dict, dict]:
    tx, ty = [r["text"] for r in train_rows], [r["label"] for r in train_rows]
    vx, vy = [r["text"] for r in val_rows], [r["label"] for r in val_rows]
    report = {"c_grid": {}}
    best = None
    for C in C_GRID:
        vec, clf = _fit(tx, ty, C)
        f1 = f1_score(vy, clf.predict(vec.transform(vx)), average="macro")
        report["c_grid"][str(C)] = round(float(f1), 4)
        if best is None or f1 > best[0]:
            best = (f1, C, vec, clf)
    _, C, vec, clf = best
    report["C"], report["full_vocabulary"] = C, len(vec.vocabulary_)

    # compression: the n-grams with the largest weights for any class
    names = vec.get_feature_names_out()
    keep = set()
    for row in clf.coef_:
        keep.update(names[np.argsort(-np.abs(row))[:KEEP_PER_CLASS]])
    vec, clf = _fit(tx, ty, C, vocabulary=sorted(keep))
    report["kept_vocabulary"] = len(keep)

    scale = float(np.abs(clf.coef_).max()) / 127.0
    q = np.rint(clf.coef_ / scale).astype(np.int8)
    names = vec.get_feature_names_out()
    classes = list(clf.classes_)
    weights = {}
    for j, gram in enumerate(names):
        nz = np.nonzero(q[:, j])[0]
        if len(nz):
            weights[gram] = [int(x) for i in nz for x in (i, q[i, j])]       # flat: class, weight, class, weight…
    idf = {g: round(float(vec.idf_[vec.vocabulary_[g]]), 5) for g in weights}
    exported = {"kind": "char-ngram-tfidf-logreg", "ngram_range": [MIN_N, MAX_N], "labels": classes,
                "bias": [round(float(b), 5) for b in clf.intercept_], "scale": scale, "idf": idf, "weights": weights,
                "temperature": 1.0}
    report["nonzero_weights"] = sum(len(v) for v in weights.values()) // 2

    model = Exported(exported)
    exported["temperature"] = fit_temperature(model, vx, vy)
    report["temperature"] = exported["temperature"]
    return exported, report


def fit_temperature(model, texts, labels) -> float:
    logits = np.array([model.logits(t) for t in texts])
    idx = np.array([model.index[l] for l in labels])

    def nll(T):
        z = logits / T
        z = z - z.max(axis=1, keepdims=True)
        logp = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
        return -logp[np.arange(len(idx)), idx].mean()

    return round(float(minimize_scalar(nll, bounds=(0.05, 20), method="bounded").x), 4)


class Exported:
    """Inference over the exported dict (same arithmetic as backend/app/services/categorizer.py and merchantModel.js)."""

    def __init__(self, m: dict):
        self.m, self.labels = m, m["labels"]
        self.index = {l: i for i, l in enumerate(self.labels)}

    def logits(self, text: str) -> np.ndarray:
        m = self.m
        counts = Counter(g for g in ngrams(text) if g in m["idf"])
        vals = {g: (1.0 + math.log(c)) * m["idf"][g] for g, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vals.values())) or 1.0
        z = np.array(m["bias"], dtype=np.float64)
        z = list(z)
        for g, v in vals.items():
            w = m["weights"][g]
            x = v / norm * m["scale"]
            for k in range(0, len(w), 2):
                z[w[k]] += x * w[k + 1]
        z = np.array(z)
        return z

    def proba(self, text: str) -> np.ndarray:
        z = self.logits(text) / self.m["temperature"]
        z = np.exp(z - z.max())
        return z / z.sum()

    def predict(self, text: str) -> tuple[str, float]:
        p = self.proba(text)
        i = int(p.argmax())
        return self.labels[i], float(p[i])

