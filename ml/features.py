"""
Text features for Model A. Ported line for line to frontend/src/lib/merchantModel.js and
backend/app/services/categorizer.py (a parity test runs all three on the same strings).

normalize: lower case; every digit → "0"; everything except a–z, 0, "@" and "&" → space; spaces collapsed.
ngrams: for each word, " word " and its character n-grams for n = 1..5 (like scikit-learn's char_wb).
"""

from __future__ import annotations

import re

MIN_N, MAX_N = 1, 5


def normalize(text: str) -> str:
    text = re.sub(r"[0-9]", "0", (text or "").lower())
    text = re.sub(r"[^a-z0@&]+", " ", text)
    return " ".join(text.split())


def ngrams(text: str) -> list[str]:
    out = []
    for word in normalize(text).split(" "):
        if not word:
            continue
        w = f" {word} "
        for n in range(MIN_N, MAX_N + 1):
            if n > len(w):
                break
            out.extend(w[i:i + n] for i in range(len(w) - n + 1))
    return out
