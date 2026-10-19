"""Server quick-add parser (Telegram) matches the browser's: shared cases."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from app.services.quick_add import GENERIC, KEYWORDS, parse_quick_add

REPO = Path(__file__).resolve().parents[2]
SHARED = json.loads((REPO / "fixtures" / "quick_add_cases.json").read_text())
TODAY = date.fromisoformat(SHARED["today"])


@pytest.mark.parametrize("text, expected", SHARED["cases"])
def test_shared_cases(text, expected):
    assert parse_quick_add(text, TODAY) == expected


def test_keyword_lists_match_the_browser():
    js = (REPO / "frontend" / "src" / "lib" / "quickAdd.js").read_text()
    for category, words in KEYWORDS.items():
        line = re.search(rf'"{re.escape(category)}": \[(.*?)\]', js).group(1)
        assert re.findall(r'"([^"]+)"', line) == words, category
    generic = re.search(r"const GENERIC = new Set\(\[(.*?)\]\);", js, re.S).group(1)
    assert set(re.findall(r'"([^"]+)"', generic)) == GENERIC
