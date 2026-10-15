"""
Three months of one synthetic user, imported the way the browser sends it
(already parsed and PII-stripped rows, one batch per statement), plus the
user's own actions through the API. Every figure is asserted exactly.

Accounts: HDFC Bank (salary, rent, card bill, self-transfer out, failed UPI),
SBI (electricity, lending to Ankit, self-transfer in), HDFC credit card
(Netflix with a price hike, Swiggy with a refund, Amazon split), Google Pay
(Zepto — the same payments the HDFC statement shows — and money from Priya).

Expected spend per month (kind=spend net of refunds):
  Apr  Rent 20000 + Netflix 499 + Swiggy 600 + Zepto 900 + Electricity 1200      = 23199
  May  Rent 20000 + Netflix 499 + Swiggy 1200−400 + Zepto 1500 + Electricity 1300 = 24099
  Jun  Rent 20000 + Netflix 649 + Swiggy 300 + Zepto 400 + Electricity 1250
       + Amazon 3000 (split 2000 Shopping / 1000 Health)                          = 25599
Not spending: card bill payments (transfer pairs), HDFC→SBI ₹15,000 (transfer
pair), failed Zomato ₹350 (reversal pair), ₹3,000 lent to Ankit.
Income: salary 80000 each month; Jun also ₹1,500 from Priya. Ankit's ₹2,000
back is a repayment, the Swiggy ₹400 a refund — neither is income.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core import clock
from tests.conftest import as_user

USER = as_user("rahul")
TODAY = date(2024, 6, 28)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def r(d, desc, amount, direction="debit", ref=None, source_type="bank_csv", label="HDFC Bank", type_="transaction"):
    return {"date": d, "description_raw": desc, "amount": amount, "direction": direction, "reference": ref,
            "source_type": source_type, "source_label": label, "type": type_}


HDFC = []
for m, zepto_ref in ((4, "612400000408"), (5, "612400000508"), (6, "612400000608")):
    HDFC += [
        r(f"2024-{m:02d}-01", "NEFT CR-ACME CORP PAYROLL", "80000.00", "credit", ref=f"N0{m}ACME0001"),
        r(f"2024-{m:02d}-03", "UPI-RAVI KUMAR-R***@okaxis-XXXX-Rent", "20000.00"),
        r(f"2024-{m:02d}-08", "UPI-ZEPTO-zepto@ybl-XXXX-Order", {4: "900.00", 5: "1500.00", 6: "400.00"}[m], ref=zepto_ref),
        r(f"2024-{m:02d}-20", "BILLPAY HDFC CC PAYMENT", "5000.00"),
    ]
HDFC += [
    r("2024-05-25", "IMPS-SELF-SBI", "15000.00"),
    r("2024-06-05", "UPI-ZOMATO-zomato@hdfcbank-XXXX-Order", "350.00", ref="412300000001"),
    r("2024-06-06", "UPI-REV-ZOMATO-XXXX", "350.00", "credit", ref="412300000001"),
]

SBI = [
    r("2024-04-07", "BESCOM BILL PAYMENT", "1200.00", label="SBI"),
    r("2024-05-07", "BESCOM BILL PAYMENT", "1300.00", label="SBI"),
    r("2024-06-07", "BESCOM BILL PAYMENT", "1250.00", label="SBI"),
    r("2024-04-12", "UPI/P2A/XXXX/ANKIT JAIN/loan", "3000.00", label="SBI"),
    r("2024-05-26", "IMPS CR SELF", "15000.00", "credit", label="SBI"),
    r("2024-05-28", "UPI/P2A/XXXX/ANKIT JAIN/return", "2000.00", "credit", label="SBI"),
]

CARD = dict(source_type="credit_card", label="HDFC Bank Credit Card")
HDFC_CARD = [
    r("2024-04-10", "NETFLIX COM", "499.00", **CARD),
    r("2024-05-10", "NETFLIX COM", "499.00", **CARD),
    r("2024-06-10", "NETFLIX COM", "649.00", **CARD),
    r("2024-04-15", "SWIGGY ORDER", "600.00", **CARD),
    r("2024-05-15", "SWIGGY ORDER", "1200.00", **CARD),
    r("2024-05-18", "SWIGGY REFUND", "400.00", "credit", **CARD),
    r("2024-06-15", "SWIGGY ORDER", "300.00", **CARD),
    r("2024-06-22", "AMAZON PAY INDIA", "3000.00", **CARD),
] + [r(f"2024-{m:02d}-20", "PAYMENT RECEIVED - THANK YOU", "5000.00", "credit", type_="transfer", **CARD) for m in (4, 5, 6)]

GPAY = dict(source_type="upi_google_pay", label="Google Pay")
GOOGLE_PAY = [
    r("2024-04-08T13:05:00", "ZEPTO MARKETPLACE PRIVATE LIMITED", "900.00", ref="612400000408", **GPAY),
    r("2024-05-08T19:41:00", "ZEPTO MARKETPLACE PRIVATE LIMITED", "1500.00", ref="612400000508", **GPAY),
    r("2024-06-08T08:15:00", "ZEPTO MARKETPLACE PRIVATE LIMITED", "400.00", ref="612400000608", **GPAY),
    r("2024-06-02T21:10:00", "Priya Nair", "1500.00", "credit", ref="612400000602", **GPAY),
]


def month(client, m):
    return client.get(f"/api/transactions/summary?period=month&year=2024&month={m}", headers=USER).json()


def txns(client):
    return client.get("/api/transactions?page_size=200", headers=USER).json()["items"]


def find(client, desc, day):
    return next(t for t in txns(client) if t["merchant_raw"] == desc and t["transaction_date"].startswith(day))


def test_three_months(client):
    imported = 0
    for statement in (HDFC, SBI, HDFC_CARD, GOOGLE_PAY):
        res = client.post("/api/import/batch", json={"rows": statement}, headers=USER)
        assert res.status_code == 200, res.text
        assert res.json()["failed"] == 0
        imported += res.json()["imported"]
    # Google Pay's 3 Zepto payments are the HDFC ones (same UTR) → merged, not added
    assert imported == len(HDFC) + len(SBI) + len(HDFC_CARD) + len(GOOGLE_PAY) - 3

    # ── The user's actions ───────────────────────────────────────────────────
    loan = find(client, "UPI/P2A/XXXX/ANKIT JAIN/loan", "2024-04-12")
    assert client.patch(f"/api/transactions/{loan['id']}", json={"kind": "lent"}, headers=USER).status_code == 200
    repay = next(c for c in client.get("/api/review", headers=USER).json()["items"] if c["type"] == "repayment")
    assert repay["question"] == "Ankit Jain sent you ₹2,000. Is it a repayment?"
    client.post(f"/api/review/{repay['id']}/answer", json={"answer": "repayment"}, headers=USER)
    amazon = find(client, "AMAZON PAY INDIA", "2024-06-22")
    res = client.post(f"/api/transactions/{amazon['id']}/split",
                      json={"parts": [{"amount": "2000", "category": "Shopping"}, {"amount": "1000", "category": "Health"}]},
                      headers=USER)
    assert res.status_code == 200, res.text

    # ── Kinds the system worked out on its own ────────────────────────────────
    kinds = {(t["merchant_raw"], t["transaction_date"][:10]): t["kind"] for t in txns(client)}
    for m in ("04", "05", "06"):
        assert kinds[("BILLPAY HDFC CC PAYMENT", f"2024-{m}-20")] == "transfer"
        assert kinds[("PAYMENT RECEIVED - THANK YOU", f"2024-{m}-20")] == "transfer"
    assert kinds[("IMPS-SELF-SBI", "2024-05-25")] == kinds[("IMPS CR SELF", "2024-05-26")] == "transfer"
    assert kinds[("UPI-ZOMATO-zomato@hdfcbank-XXXX-Order", "2024-06-05")] == "reversal"
    assert kinds[("UPI-REV-ZOMATO-XXXX", "2024-06-06")] == "reversal"
    assert kinds[("SWIGGY REFUND", "2024-05-18")] == "refund"

    # ── Monthly totals ───────────────────────────────────────────────────────
    expected = {
        4: ("23199.00", "80000.00", {"Rent & Housing": "20000.00", "Utilities": "1200.00",
                                     "Groceries": "900.00", "Food & Dining": "600.00", "Entertainment": "499.00"}),
        5: ("24099.00", "80000.00", {"Rent & Housing": "20000.00", "Groceries": "1500.00", "Utilities": "1300.00",
                                     "Food & Dining": "800.00", "Entertainment": "499.00"}),
        6: ("25599.00", "81500.00", {"Rent & Housing": "20000.00", "Shopping": "2000.00", "Utilities": "1250.00",
                                     "Health": "1000.00", "Entertainment": "649.00", "Groceries": "400.00",
                                     "Food & Dining": "300.00"}),
    }
    for m, (spend, income, categories) in expected.items():
        s = month(client, m)
        assert (s["total_spend"], s["total_received"]) == (spend, income), m
        assert {c["category"]: c["total"] for c in s["categories"]} == categories, m
        assert s["net_cash_flow"] == f"{Decimal(income) - Decimal(spend):.2f}", m
    assert month(client, 5)["mom_total_delta"] == "900.00"

    # ── Recurring ────────────────────────────────────────────────────────────
    overview = client.get("/api/recurring", headers=USER).json()
    series = {s["name"]: s for s in overview["series"]}
    assert set(series) == {"Ravi Kumar", "Netflix", "Electricity Bill"}
    view = lambda s: (s["cadence"], s["typical_amount"], s["type"], s["status"], s["last_date"], s["next_expected"], s["price_change"])
    assert view(series["Ravi Kumar"]) == ("monthly", "20000.00", "rent", "active", "2024-06-03", "2024-07-03", None)
    assert view(series["Netflix"]) == ("monthly", "649.00", "subscription", "active", "2024-06-10", "2024-07-10",
                                       {"old": "499.00", "new": "649.00"})
    assert view(series["Electricity Bill"]) == ("monthly", "1250.00", "bill", "active", "2024-06-07", "2024-07-07", None)
    assert overview["monthly_committed"] == "21899.00"     # 20000 + 649 + 1250


def test_upcoming_window(client):
    """Next dues 3, 7 and 10 July are within 14 days of 28 June."""
    for statement in (HDFC, SBI, HDFC_CARD, GOOGLE_PAY):
        client.post("/api/import/batch", json={"rows": statement}, headers=USER)
    upcoming = [(s["name"], s["next_expected"]) for s in client.get("/api/recurring", headers=USER).json()["upcoming"]]
    assert upcoming == [("Ravi Kumar", "2024-07-03"), ("Electricity Bill", "2024-07-07"), ("Netflix", "2024-07-10")]


def test_people_balances(client):
    for statement in (HDFC, SBI, HDFC_CARD, GOOGLE_PAY):
        client.post("/api/import/batch", json={"rows": statement}, headers=USER)
    loan = find(client, "UPI/P2A/XXXX/ANKIT JAIN/loan", "2024-04-12")
    back = find(client, "UPI/P2A/XXXX/ANKIT JAIN/return", "2024-05-28")
    client.patch(f"/api/transactions/{loan['id']}", json={"kind": "lent"}, headers=USER)
    client.patch(f"/api/transactions/{back['id']}", json={"kind": "repayment"}, headers=USER)
    people = {p["name"]: p for p in client.get("/api/people", headers=USER).json()["people"]}
    assert set(people) == {"Ravi Kumar", "Ankit Jain", "Priya Nair"}
    pick = lambda p: (p["paid_total"], p["received_total"], p["transaction_count"], p["balance"], p["outstanding_days"])
    assert pick(people["Ravi Kumar"]) == ("60000.00", "0.00", 3, "0.00", None)
    assert pick(people["Ankit Jain"]) == ("3000.00", "2000.00", 2, "1000.00", 77)      # owes you ₹1,000 · 77 days
    assert pick(people["Priya Nair"]) == ("0.00", "1500.00", 1, "0.00", None)
