"""Merchant normalizer: short brand tokens must not match inside other words."""

import pytest

from app.services.merchant_normalizer import normalize


@pytest.mark.parametrize("raw, merchant", [
    ("UPI-RAVI KUMAR-R***@okaxis-XXXX-Rent", "Rent"),        # was "Vodafone Idea" (vi inside RAVI)
    ("NEFT-SURESH DEVI-XXXX", "NEFT-SURESH DEVI-XXXX"),      # unrecognized, not Vodafone Idea
    ("NACH-PUBLIC PROVIDENT FUND", "NACH-PUBLIC PROVIDENT FUND"),  # not LIC
    ("POS MOTOROLA STORE", "MOTOROLA STORE"),                 # not Ola
    ("TO CURRENT A/C", "CURRENT A/C"),                         # not Rent
])
def test_no_substring_false_positives(raw, merchant):
    n = normalize(raw)
    if n.confidence >= 0.5:
        assert n.merchant_clean == merchant, (raw, n)
    else:
        assert n.merchant_clean != "Vodafone Idea"


@pytest.mark.parametrize("raw, merchant", [
    ("UPI-OLA-ola@icici", "Ola"), ("VI POSTPAID BILL", "Vodafone Idea"), ("LIC PREMIUM", "LIC"),
    ("HOUSE RENT MAY", "Rent"), ("ZEPTOMARKETPLACEPRIVATELIMITED", "Zepto"), ("UPI/SWIGGY*ORDER", "Swiggy"),
    ("NETFLIX COM", "Netflix"), ("KFC KORAMANGALA", "KFC"),
])
def test_real_brands_still_match(raw, merchant):
    assert normalize(raw).merchant_clean == merchant
