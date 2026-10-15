"""
The Python statement parsers (tests/reference/) are kept only as the reference for the browser
ports (frontend/src/import/). This pins their output on the shared fixtures;
frontend/src/import/parity.test.js checks the JS ports against the same file.
"""

import json
from pathlib import Path

import pytest

from tests.reference.csv_parser import parse_csv
from tests.reference.upi_statement_parser import parse_upi_statement

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "statements"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())


@pytest.mark.parametrize("name", ["hdfc.csv", "icici.csv", "sbi.csv", "axis.csv", "kotak.csv"])
def test_csv_reference(name):
    _, txns = parse_csv((FIXTURES / name).read_bytes(), filename=name)
    assert [
        {"date": t.transaction_date.strftime("%Y-%m-%d"), "description_raw": t.merchant_raw,
         "amount": f"{t.amount:.2f}", "direction": "debit"}
        for t in txns
    ] == EXPECTED[name]


def test_google_pay_reference():
    _, txns = parse_upi_statement((FIXTURES / "gpay.pdf").read_bytes())
    assert [
        {"date": t.transaction_date.strftime("%Y-%m-%dT%H:%M:%S"), "description_raw": t.merchant_raw,
         "amount": f"{t.amount:.2f}", "direction": "credit" if t.direction == "received" else "debit",
         "reference": t.utr, "type": "transfer" if t.direction == "self_transfer" else "transaction"}
        for t in txns
    ] == EXPECTED["gpay.pdf"]
