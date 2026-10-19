"""
Model B: a small multilingual embedding + logistic-regression head.

No off-the-shelf multilingual sentence encoder fits the ~25 MB browser budget (the MiniLM/e5 ONNX models are
≥ 118 MB even quantized). sentence-transformers/static-similarity-mrl-multilingual-v1 (Apache-2.0) is a *static*
embedding model (a token table, mean-pooled) trained with Matryoshka loss, so its vectors can be truncated: the first
DIMS dimensions, int8 with one scale per token, are ≈ 105k × 128 bytes ≈ 13.6 MB plus a 2.6 MB tokenizer.
Inference is tokenize → average the token rows → L2-normalise → logistic regression → temperature.

The model files are downloaded to a cache outside the repo (MODEL_B_DIR, default ~/.cache/vaulta-ml/static-mrl);
nothing of it is committed unless Model B ships.
"""

from __future__ import annotations

import json
import os
import struct
import urllib.request
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from common import SEED
from features import normalize

REPO = "sentence-transformers/static-similarity-mrl-multilingual-v1"
FILES = {"model.safetensors": "0_StaticEmbedding/model.safetensors", "tokenizer.json": "0_StaticEmbedding/tokenizer.json"}
DIMS = 128
C_GRID = (1.0, 10.0, 100.0)


def model_dir() -> Path:
    d = Path(os.environ.get("MODEL_B_DIR", Path.home() / ".cache" / "vaulta-ml" / "static-mrl"))
    d.mkdir(parents=True, exist_ok=True)
    for name, path in FILES.items():
        if not (d / name).exists():
            urllib.request.urlretrieve(f"https://huggingface.co/{REPO}/resolve/main/{path}", d / name)
    return d


def _safetensors(path: Path) -> np.ndarray:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
        name, meta = next((k, v) for k, v in header.items() if k != "__metadata__")
        assert meta["dtype"] == "F32", meta["dtype"]
        start, end = meta["data_offsets"]
        f.seek(8 + n + start)
        return np.frombuffer(f.read(end - start), dtype=np.float32).reshape(meta["shape"])


class Embedder:
    def __init__(self):
        from tokenizers import Tokenizer
        d = model_dir()
        table = _safetensors(d / "model.safetensors")[:, :DIMS]
        self.scale = np.abs(table).max(axis=1, keepdims=True) / 127.0 + 1e-12
        self.table = np.rint(table / self.scale).astype(np.int8)      # what would ship: int8 rows, one scale each
        self.tokenizer = Tokenizer.from_file(str(d / "tokenizer.json"))
        self.size_bytes = self.table.nbytes + self.scale.size * 2 + (d / "tokenizer.json").stat().st_size

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), DIMS), dtype=np.float64)
        for i, enc in enumerate(self.tokenizer.encode_batch([normalize(t) for t in texts], add_special_tokens=False)):
            if enc.ids:
                rows = self.table[enc.ids].astype(np.float64) * self.scale[enc.ids]
                v = rows.mean(axis=0)
                out[i] = v / (np.linalg.norm(v) or 1.0)
        return out


def train(train_rows, val_rows):
    emb = Embedder()
    tx, ty = emb.embed([r["text"] for r in train_rows]), [r["label"] for r in train_rows]
    vx, vy = emb.embed([r["text"] for r in val_rows]), [r["label"] for r in val_rows]
    best, grid = None, {}
    for C in C_GRID:
        clf = LogisticRegression(C=C, max_iter=3000, random_state=SEED).fit(tx, ty)
        f1 = f1_score(vy, clf.predict(vx), average="macro")
        grid[str(C)] = round(float(f1), 4)
        if best is None or f1 > best[0]:
            best = (f1, C, clf)
    _, C, clf = best
    model = Model(emb, clf)
    model.temperature = model.fit_temperature(vx, vy)
    return model, {"c_grid": grid, "C": C, "dims": DIMS, "size_mb": round(emb.size_bytes / 1e6, 1),
                   "temperature": model.temperature}


class Model:
    def __init__(self, emb: Embedder, clf: LogisticRegression):
        self.emb, self.clf, self.temperature = emb, clf, 1.0
        self.labels = list(clf.classes_)

    def _proba(self, X: np.ndarray, T: float) -> np.ndarray:
        z = self.clf.decision_function(X) / T
        z = np.exp(z - z.max(axis=1, keepdims=True))
        return z / z.sum(axis=1, keepdims=True)

    def fit_temperature(self, X, y) -> float:
        from scipy.optimize import minimize_scalar
        idx = np.array([self.labels.index(l) for l in y])
        nll = lambda T: -np.log(self._proba(X, T)[np.arange(len(idx)), idx] + 1e-12).mean()  # noqa: E731
        return round(float(minimize_scalar(nll, bounds=(0.05, 20), method="bounded").x), 4)

    def predict_many(self, texts: list[str]) -> list[tuple[str, float]]:
        p = self._proba(self.emb.embed(texts), self.temperature)
        return [(self.labels[i], float(row[i])) for row, i in zip(p, p.argmax(axis=1))]
