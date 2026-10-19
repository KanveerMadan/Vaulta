"""Split leakage: no merchant, name stem or identical narration crosses from train into a held-out split."""

import re
import sys
from collections import defaultdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA, read_jsonl  # noqa: E402

NARRATIONS = read_jsonl(DATA / "narrations.jsonl")
MERCHANTS = read_jsonl(DATA / "merchant_list.jsonl")
pytestmark = pytest.mark.skipif(not NARRATIONS, reason="run `make data` first")


def test_every_merchant_is_in_exactly_one_split():
    splits = defaultdict(set)
    for r in NARRATIONS:
        splits[r["merchant"].lower()].add(r["split"])
    assert all(len(s) == 1 for s in splits.values())
    assert len({m["name"].lower() for m in MERCHANTS}) == len(MERCHANTS)


def test_no_held_out_narration_is_also_in_train():
    train = {r["text"].lower() for r in NARRATIONS if r["split"] == "train"}
    assert not [r for r in NARRATIONS if r["split"] != "train" and r["text"].lower() in train]


def test_unseen_local_shops_have_name_stems_never_seen_in_training():
    seen = {m["stem"] for m in MERCHANTS if m["kind"] == "local" and m["split"] in ("train", "val")}
    held = {m["stem"] for m in MERCHANTS if m["split"] == "test_local"}
    assert held and not (held & seen)
    assert all(m["kind"] == "local" for m in MERCHANTS if m["split"] == "test_local")


def test_the_main_test_set_is_unseen_catalogue_merchants():
    assert {m["kind"] for m in MERCHANTS if m["split"] == "test"} == {"brand"}


def test_narrations_are_stripped():
    for r in NARRATIONS:
        assert not re.search(r"\d{9,}", r["text"]), "long digit run survived the stripper"
        assert not re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", r["text"]), "IFSC survived the stripper"
        assert not re.search(r"(?<![\dX])[6-9]\d{9}(?!\d)", r["text"]), "phone number survived the stripper"
