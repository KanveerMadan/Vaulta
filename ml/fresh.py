"""
The fresh frozen test set (go-live stage 1). The Phase 9 test sets were looked at while the method was being chosen,
so their numbers are optimistic. This set is built from merchants and local-shop name stems written afterwards, kept
only when they were never used in any earlier run, labelled by the same teacher procedure, and frozen.

Never used for training, model choice or thresholds: train.py tunes on validation and only *reports* on this set.

New, by canonical merchant and by string. A candidate is dropped when any of its names or aliases, squashed to
letters and digits:
  - equals an earlier merchant name, alias, local shop or name stem, or
  - contains one of them as whole words, or is contained in one (so "Swiggy Partner Payout" goes because of "Swiggy");
and a narration is dropped when its stripped text was an earlier narration, or its teacher string was ever sent to the
teacher before (it is a Phase 9 merchant's teacher string).

Writes data/fresh_test.jsonl (committed: stripped synthetic narrations and their teacher labels, no user data) and
artifacts/fresh_test.json (its sha256 and counts). Once frozen it is never rewritten: a re-run only checks the hash.

    python fresh.py            # build, label (calls the teacher for new strings) and freeze; or check the frozen set
    python fresh.py --freeze-without-unlabelled   # when a few strings never get a valid label
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import Counter

import generate
import teacher
from common import ARTIFACTS, DATA, SEED, _entries, local_shop_words, merchants, name_stems, read_jsonl, strip, write_jsonl

FROZEN = DATA / "fresh_test.jsonl"
MANIFEST = ARTIFACTS / "fresh_test.json"
LOCAL_PER_SUBCATEGORY = 6
NARRATIONS = {"brand": 7, "local": 6}


def words(s: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", s.lower()))


def contains(longer: tuple, shorter: tuple) -> bool:
    n = len(shorter)
    return 0 < n <= len(longer) and any(longer[i:i + n] == shorter for i in range(len(longer) - n + 1))


class Seen:
    """Every string used before, for the equality and whole-word containment checks."""

    def __init__(self, strings):
        self.words = {words(s) for s in strings if words(s)}
        self.squashed = {"".join(w) for w in self.words}

    def clashes(self, s: str) -> bool:
        w = words(s)
        return ("".join(w) in self.squashed or any(contains(w, old) or contains(old, w) for old in self.words))


def earlier_strings() -> list[str]:
    out = []
    for m in merchants():
        out += [m["name"], *m["aliases"]]
    out += [m["name"] for m in read_jsonl(DATA / "merchant_list.jsonl")]      # includes the generated local shops
    out += name_stems()
    return out


def fresh_brands(seen: Seen) -> tuple[list[dict], int]:
    out, dropped, names = [], 0, set()
    for hint, items in _entries(DATA / "fresh_merchants.txt"):
        for item in items:
            m = re.fullmatch(r"(.+?)\s*\((.+)\)", item)
            name, aliases = (m.group(1), [a.strip() for a in m.group(2).split("|")]) if m else (item, [])
            if any(seen.clashes(s) for s in [name, *aliases]) or name.lower() in names:
                dropped += 1
                continue
            names.add(name.lower())
            out.append({"name": name, "aliases": aliases, "hint": hint, "kind": "brand"})
    return out, dropped


def fresh_stems(seen: Seen) -> tuple[list[str], int]:
    text = "\n".join(l for l in (DATA / "fresh_name_stems.txt").read_text().splitlines() if not l.startswith("#"))
    stems = [x.strip() for x in text.split(";") if x.strip()]
    kept = [s for s in stems if not seen.clashes(s)]
    return kept, len(stems) - len(kept)


def local_shops(rng: random.Random, stems: list[str], taken: set[str]) -> list[dict]:
    shops = []
    for hint, shop_words in local_shop_words().items():
        for _ in range(LOCAL_PER_SUBCATEGORY):
            name = f"{rng.choice(stems)} {rng.choice(shop_words)}"
            if name.lower() not in taken:
                taken.add(name.lower())
                shops.append({"name": name, "aliases": [], "hint": hint, "kind": "local"})
    return shops


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if FROZEN.exists():
        manifest = json.loads(MANIFEST.read_text())
        if sha256(FROZEN) != manifest["sha256"]:
            sys.exit("data/fresh_test.jsonl differs from its frozen hash: the fresh test set must never change.")
        print(f"fresh test set frozen and unchanged: {manifest['rows']} rows")
        return

    seen = Seen(earlier_strings())
    brands, dropped_brands = fresh_brands(seen)
    stems, dropped_stems = fresh_stems(seen)
    rng = random.Random(SEED + 2026)
    everything = brands + local_shops(rng, stems, {b["name"].lower() for b in brands})

    earlier_texts = {r["text"].lower() for r in read_jsonl(DATA / "narrations.jsonl")}
    # what earlier runs sent to the teacher: every Phase 9 merchant as the bank prints it (teacher.py). Not the cache,
    # which this run adds to.
    cached = {strip(m["name"].upper()) for m in read_jsonl(DATA / "merchant_list.jsonl")}
    rows, used_before = [], Counter()
    for m in everything:
        m["teacher_text"] = strip(m["name"].upper())
        if m["teacher_text"] in cached:                       # sent to the teacher in an earlier run
            used_before["teacher_string"] += 1
            continue
        for fmt, raw in generate.narrations_for(rng, m, NARRATIONS[m["kind"]]):
            text = strip(raw)
            if text.lower() in earlier_texts:
                used_before["narration"] += 1
                continue
            rows.append({"merchant": m["name"], "kind": m["kind"], "hint": m["hint"], "format": fmt, "text": text,
                         "teacher_text": m["teacher_text"]})

    t = teacher.Teacher(DATA / "teacher_cache.jsonl")
    try:
        labelled = teacher.run(t, sorted({r["teacher_text"] for r in rows}))
    finally:
        teacher._save_log(t, {})
    by_text = {r["text"]: r for r in labelled}
    # strings the teacher still couldn't label after its retries are left out, and counted (as in Phase 9)
    missing = {r["teacher_text"] for r in rows} - set(by_text)
    if missing and "--freeze-without-unlabelled" not in sys.argv:
        sys.exit(f"{len(missing)} strings aren't fully labelled yet: re-run (rate limit), or freeze without them with "
                 "--freeze-without-unlabelled once re-runs no longer help.")
    rows = [r for r in rows if r["teacher_text"] in by_text]
    out = [{k: r[k] for k in ("merchant", "kind", "hint", "format", "text")} |
           {"label": by_text[r["teacher_text"]]["label"], "votes": by_text[r["teacher_text"]]["votes"]} for r in rows]
    write_jsonl(FROZEN, out)
    merchants_by_kind = Counter(m["kind"] for m in everything if m["teacher_text"] not in cached)
    manifest = {
        "sha256": sha256(FROZEN), "rows": len(out),
        "rows_by_kind": dict(Counter(r["kind"] for r in out)),
        "merchants_by_kind": dict(merchants_by_kind),
        "ambiguous_rows": sum(r["label"] == teacher.AMBIGUOUS for r in out),
        "unlabelled_strings_left_out": len(missing),
        "dropped_as_used_before": {"brands": dropped_brands, "name_stems": dropped_stems, **used_before},
        "name_stems_used": len(stems),
        "teacher": {"models": teacher.MODELS, "prompt_version": teacher.PROMPT_VERSION},
        "note": "Evaluation only. Never used for training, model choice or thresholds.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
