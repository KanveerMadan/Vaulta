"""Server PII rules (services/pii.py) are the browser's (pii.js): same shared cases, same token list."""

import json
import re
from pathlib import Path

import pytest

from app.services.pii import BUSINESS_VPA_TOKENS, clean_reference, holder_name_pattern, sanitize_description

REPO = Path(__file__).resolve().parents[2]
CASES = json.loads((REPO / "fixtures" / "pii_cases.json").read_text())


@pytest.mark.parametrize("text, holder, expected", CASES["descriptions"])
def test_descriptions(text, holder, expected):
    assert sanitize_description(text, name_pattern=holder_name_pattern(holder)) == expected


@pytest.mark.parametrize("ref, expected", CASES["references"])
def test_references(ref, expected):
    assert clean_reference(ref) == expected


def test_merchant_vpa_tokens_match_the_browser():
    js = (REPO / "frontend" / "src" / "import" / "pii.js").read_text()
    block = re.search(r"const BUSINESS_VPA_TOKENS = \[(.*?)\];", js, re.S).group(1)
    assert re.findall(r'"([^"]+)"', block) == BUSINESS_VPA_TOKENS


def test_counts():
    counts = {}
    sanitize_description("UPI-A-a.b@okaxis-HDFC0001234-412398765432-9876543210", counts)
    assert counts == {"upi_ids": 1, "phone_numbers": 1, "ifsc_codes": 1, "account_numbers": 1}
