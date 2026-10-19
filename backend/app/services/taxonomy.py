"""
Two-level category taxonomy (app/data/taxonomy.json, documented in docs/ml/taxonomy.md).

A transaction's `category` is a group ("Food & Dining"), the same names as before the taxonomy existed, so totals,
budgets and reports keep working. `subcategory` is optional: a taxonomy id ("food.delivery") or one of the user's
own subcategories ("custom:<uuid>", models/category.py). The group is always derived from the subcategory.
frontend/src/lib/taxonomy.json is a copy (tests/test_taxonomy.py keeps them identical).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

TAXONOMY = json.loads((Path(__file__).resolve().parent.parent / "data" / "taxonomy.json").read_text())

GROUPS: dict[str, dict] = {g["name"]: g for g in TAXONOMY["groups"]}
SUBCATEGORIES: dict[str, dict] = {
    s["id"]: {**s, "group": g["name"]} for g in TAXONOMY["groups"] for s in g["subcategories"]
}
SYSTEM_GROUPS = [g["name"] for g in TAXONOMY["system_groups"]]
GROUP_NAMES = frozenset(GROUPS) | frozenset(SYSTEM_GROUPS)
CREDIT_ONLY_GROUPS = frozenset(g["name"] for g in TAXONOMY["groups"] if g.get("credit_only"))
CUSTOM_PREFIX = "custom:"


def group_of(subcategory: Optional[str]) -> Optional[str]:
    """The group of a taxonomy subcategory id, or None (custom subcategories are resolved by their row)."""
    s = SUBCATEGORIES.get(subcategory or "")
    return s["group"] if s else None


def label(subcategory: Optional[str]) -> Optional[str]:
    s = SUBCATEGORIES.get(subcategory or "")
    return s["name"] if s else None
