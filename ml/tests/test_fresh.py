"""The fresh frozen test set (fresh.py): unchanged since it was frozen, new, and never part of training or tuning."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dataset  # noqa: E402
import fresh  # noqa: E402
from common import ARTIFACTS, DATA, read_jsonl  # noqa: E402

FRESH = read_jsonl(DATA / "fresh_test.jsonl")
NARRATIONS = read_jsonl(DATA / "narrations.jsonl")


def test_frozen_set_is_unchanged():
    manifest = json.loads((ARTIFACTS / "fresh_test.json").read_text())
    assert hashlib.sha256((DATA / "fresh_test.jsonl").read_bytes()).hexdigest() == manifest["sha256"]
    assert len(FRESH) == manifest["rows"] > 1000


@pytest.mark.skipif(not NARRATIONS, reason="run `make data` first")
def test_no_fresh_merchant_or_narration_was_used_before():
    seen = fresh.Seen(fresh.earlier_strings())
    brands = {r["merchant"] for r in FRESH if r["kind"] == "brand"}
    assert brands and not [m for m in brands if seen.clashes(m)]
    # local shops share shop words with earlier data by design; their name stems are new and no full name was used
    stems, _ = fresh.fresh_stems(seen)
    assert stems and not [s for s in stems if seen.clashes(s)]
    locals_ = {r["merchant"] for r in FRESH if r["kind"] == "local"}
    assert locals_ and all(any(m.startswith(s + " ") for s in stems) for m in locals_)
    assert not ({"".join(fresh.words(m)) for m in locals_} & seen.squashed)
    earlier = {r["text"].lower() for r in NARRATIONS}
    assert not [r for r in FRESH if r["text"].lower() in earlier]


@pytest.mark.skipif(not NARRATIONS, reason="run `make data` first")
def test_training_and_tuning_data_never_include_it():
    fresh_texts = {r["text"] for r in FRESH}
    data = dataset.load()
    assert not [r for split in ("train", "val", "test", "test_local") for r in data[split] if r["text"] in fresh_texts]
