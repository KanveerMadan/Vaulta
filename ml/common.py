"""Shared paths, the taxonomy, the catalogue readers and the stripper used by every ml/ script."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ML = Path(__file__).resolve().parent
ROOT = ML.parent
DATA = ML / "data"
PRIVATE = DATA / "private"          # git-ignored: anything derived from real statements
ARTIFACTS = ML / "artifacts"
SEED = 20261017

sys.path.insert(0, str(ROOT / "backend"))
from app.services.pii import sanitize_description  # noqa: E402  (the server's stripper, same rules as the browser's)

TAXONOMY = json.loads((ROOT / "backend/app/data/taxonomy.json").read_text())
SUBCATEGORIES = {s["id"]: {**s, "group": g["name"]} for g in TAXONOMY["groups"] for s in g["subcategories"]}
LABELS = sorted(SUBCATEGORIES)


def stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16)


def _entries(path: Path):
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, rest = line.split(":", 1)
        yield key.strip(), [x.strip() for x in rest.split(";") if x.strip()]


def merchants() -> list[dict]:
    """[{name, aliases, hint}] from data/merchants.txt."""
    out, seen = [], set()
    for hint, items in _entries(DATA / "merchants.txt"):
        assert hint in SUBCATEGORIES, hint
        for item in items:
            m = re.fullmatch(r"(.+?)\s*\((.+)\)", item)
            name, aliases = (m.group(1), [a.strip() for a in m.group(2).split("|")]) if m else (item, [])
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({"name": name, "aliases": aliases, "hint": hint, "kind": "brand"})
    return out


def local_shop_words() -> dict[str, list[str]]:
    return dict(_entries(DATA / "local_shops.txt"))


def name_stems() -> list[str]:
    text = "\n".join(l for l in (DATA / "name_stems.txt").read_text().splitlines() if not l.startswith("#"))
    return [x.strip() for x in text.split(";") if x.strip()]


def strip(narration: str) -> str:
    """What the server stores and the model sees: the narration after the PII stripper (app/services/pii.py)."""
    return sanitize_description(narration)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
