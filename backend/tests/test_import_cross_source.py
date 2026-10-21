"""
A bank statement and a Google Pay statement for the same month, imported in either order: every UPI payment is in
both, and must count once. Synthetic rows, shaped like what the browser sends for a Kotak CSV and a Google Pay PDF.
"""

from decimal import Decimal

import pytest

from app.core.database import engine
from tests.conftest import as_user

ALICE = as_user("alice")


@pytest.fixture(autouse=True)
def utc_database(monkeypatch):
    """Neon and CI run in UTC by default; a developer's local database may not (initdb takes the machine's timezone)."""
    monkeypatch.setenv("PGTZ", "UTC")       # libpq: new connections' session timezone
    engine.dispose()
    yield
    monkeypatch.undo()
    engine.dispose()


def bank(date, desc, amount, direction="debit", ref=None):
    return {"date": date, "description_raw": desc, "amount": amount, "direction": direction, "reference": ref,
            "source_type": "bank_csv", "source_label": "Kotak Mahindra Bank", "type": "transaction"}


def gpay(when, name, amount, direction="debit", utr=None):
    return {"date": when, "description_raw": name, "amount": amount, "direction": direction, "reference": utr,
            "source_type": "upi_google_pay", "source_label": "Google Pay", "type": "transaction"}


BANK = [
    bank("2026-07-03", "UPI/SWIGGY/XXXX/Payment", "450.00", ref="618411110001"),
    bank("2026-07-05", "UPI/PRIYA NAIR/XXXX/split", "1200.00", ref="618611110002"),
    bank("2026-07-09", "UPI/CHAI POINT/XXXX/Payment", "20.00", ref="619011110003"),      # two chais, one day
    bank("2026-07-09", "UPI/CHAI POINT/XXXX/Payment", "20.00", ref="619011110004"),
    bank("2026-07-12", "UPI/ZOMATO LTD/XXXX/Payment", "300.00"),                          # no UTR in the bank row
    bank("2026-07-15", "NEFT/ACME PAYROLL/N100015", "85000.00", "credit", "NEFT-N100015"),
    bank("2026-07-20", "ATM WDL/KOTAK ATM MUMBAI/20", "2000.00", ref="ATM-1020"),
    bank("2026-07-22", "UPI/AMIT SHAH/XXXX", "500.00", "credit", "620311110006"),
]
GPAY = [
    gpay("2026-07-03T13:05:00", "Swiggy", "450.00", utr="618411110001"),
    gpay("2026-07-05T20:10:00", "Priya Nair", "1200.00", utr="618611110002"),
    gpay("2026-07-09T08:00:00", "Chai Point", "20.00", utr="619011110003"),
    gpay("2026-07-09T17:30:00", "Chai Point", "20.00", utr="619011110004"),
    gpay("2026-07-12T01:15:00", "Zomato", "300.00", utr="619311110005"),                  # after midnight, IST
    gpay("2026-07-22T10:00:00", "Amit Shah", "500.00", "credit", utr="620311110006"),
    gpay("2026-07-25T19:00:00", "BigBasket", "899.00", utr="620611110007"),               # paid from another account
]


def items(client):
    res = client.get("/api/transactions", params={"limit": 100}, headers=ALICE).json()
    assert res["total"] == len(res["items"])
    return res["items"]


@pytest.mark.parametrize("first,second", [(BANK, GPAY), (GPAY, BANK)], ids=["bank-then-gpay", "gpay-then-bank"])
def test_bank_and_upi_statements_for_the_same_month_count_each_payment_once(client, first, second):
    assert client.post("/api/import/batch", json={"rows": first}, headers=ALICE).json()["imported"] == len(first)
    res = client.post("/api/import/batch", json={"rows": second}, headers=ALICE).json()
    assert res["failed"] == 0
    assert res["duplicates_merged"] == 6 and res["imported"] == len(second) - 6, res   # every shared UPI payment

    txns = items(client)
    assert len(txns) == len(BANK) + 1                                   # the bank's rows, plus the other account's one
    spent = sum(Decimal(t["amount"]) for t in txns if t["direction"] == "debit")
    assert spent == Decimal("450") + 1200 + 20 + 20 + 300 + 2000 + 899
    assert sorted(t["amount"] for t in txns if t["amount"] == "20.00") == ["20.00", "20.00"]   # two chais stay two


def test_importing_both_statements_again_adds_nothing(client):
    for rows in (BANK, GPAY):
        client.post("/api/import/batch", json={"rows": rows}, headers=ALICE)
    for rows in (GPAY, BANK):
        res = client.post("/api/import/batch", json={"rows": rows}, headers=ALICE).json()
        assert res["imported"] == 0 and res["duplicates_merged"] == len(rows)
    assert len(items(client)) == len(BANK) + 1
