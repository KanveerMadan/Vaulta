"""Inbound bank-alert email (services/email_alerts.py, services/inbound.py)."""

import logging
from datetime import datetime

import pytest
from sqlalchemy import text as sql

from app.core.config import settings
from app.core.database import Base
from app.services.transaction_service import IST
from tests.conftest import as_user, owner_engine, user_session
from tests.test_import_batch import row

ALICE, BOB = as_user("alice"), as_user("bob")
SECRET = "inbound-secret-for-tests"
HDFC_DKIM = "mx.cloudflare.net; dkim=pass header.d=hdfcbank.net header.s=s1; spf=softfail smtp.mailfrom=alerts@gmail.com"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_SECRET", SECRET)
    monkeypatch.setattr(settings, "INBOUND_DOMAIN", "example.in")


def address(client, headers=ALICE):
    return client.get("/api/inbound", headers=headers).json()["address"]


def mail(client, to, sender, subject, body, auth=HDFC_DKIM, html=None):
    res = client.post("/internal/inbound-email", headers={"X-Internal-Secret": SECRET},
                      json={"to": to, "from": sender, "subject": subject, "text": body, "html": html, "auth_results": auth})
    assert res.status_code == 200, res.text
    return res.json()["outcome"]


def txns(client, headers=ALICE):
    return client.get("/api/transactions?page_size=200", headers=headers).json()["items"]


HDFC = "HDFC Bank InstaAlerts <alerts@hdfcbank.net>"
UPI_DEBIT = ("Dear Customer, Rs.450.00 has been debited from account **1234 to VPA swiggy@icici SWIGGY on 05-03-24. "
             "Your UPI transaction reference number is 412345678901. If you did not authorize this transaction, call us.")


def test_hdfc_upi_debit_parses(client):
    to = address(client)
    assert to.endswith("@in.example.in") and len(to.split("@")[0]) == 10
    assert mail(client, to, HDFC, "You have done a UPI txn. Check details!", UPI_DEBIT) == "parsed"
    [t] = txns(client)
    assert (t["amount"], t["direction"], t["kind"], t["merchant_clean"], t["category"], t["transaction_date"][:10]) == (
        "450.00", "debit", "spend", "Swiggy", "Food & Dining", "2024-03-05")
    status = client.get("/api/inbound", headers=ALICE).json()
    assert (status["this_week"], status["total"]) == (1, 1)
    assert status["sources"][0]["bank"] == "HDFC Bank" and status["last_received_at"]


@pytest.mark.parametrize("sender, auth_domain, body, expected", [
    (HDFC, "hdfcbank.net",
     "Thank you for using your HDFC Bank Credit Card ending 4321 for Rs 2,199.00 at AMAZON PAY INDIA on 15-03-2024 10:01:44.",
     ("2024-03-15T10:01:44", "2199.00", "debit", "Amazon", "HDFC Bank Credit Card x4321")),
    ("ICICI Bank <credit_cards@icicibank.com>", "icicibank.com",
     "INR 342.50 spent using ICICI Bank Credit Card XX9876 on 02-Apr-24 on UBER INDIA SYSTEMS. Avl Limit: INR 1,20,000.00.",
     ("2024-04-02", "342.50", "debit", "Uber", "ICICI Bank Credit Card x9876")),
    ("SBI Card <onlinesbicard@sbicard.com>", "sbicard.com",
     "Rs.389.00 spent on your SBI Credit Card ending 5555 at ZOMATO on 05/03/24. Trxn. not done by you? Report at https://sbicard.com",
     ("2024-03-05", "389.00", "debit", "Zomato", "SBI Card Credit Card x5555")),
    ("Axis Bank Alerts <alerts@axisbank.com>", "axisbank.com",
     "INR 1,845.25 debited from A/c no. XX7777 on 01-06-2024 14:22:05 IST at UPI/P2M/415311110000/BIGBASKET. Avl Bal INR 52,000.00",
     ("2024-06-01T14:22:05", "1845.25", "debit", "BigBasket", "Axis Bank x7777")),
    ("Kotak Bank <BankAlerts@kotak.com>", "kotak.com",
     "Received Rs.500.00 in your Kotak Bank AC X2468 from rahul.s@okaxis on 05-03-24.UPI Ref:412345678902.",
     ("2024-03-05", "500.00", "credit", None, "Kotak Mahindra Bank x2468")),
    ("Yes Bank <alerts@yesbank.in>", "yesbank.in",          # no template: generic parser
     "Dear Customer, INR 1,250.00 has been debited from your account XX5678 towards BigBasket on 12/06/2024 18:22.",
     ("2024-06-12T18:22:00", "1250.00", "debit", "BigBasket", "Yes Bank x5678")),
])
def test_bank_formats(client, sender, auth_domain, body, expected):
    assert mail(client, address(client), sender, "Transaction alert", body, auth=f"dkim=pass header.d={auth_domain}") == "parsed"
    [t] = txns(client)
    date, amount, direction, merchant, label = expected
    if "T" in date:   # alert times are Indian time; compare instants (the database may return any offset)
        assert datetime.fromisoformat(t["transaction_date"]) == datetime.fromisoformat(date).replace(tzinfo=IST)
    else:
        assert t["transaction_date"].startswith(date)
    assert (t["amount"], t["direction"]) == (amount, direction)
    if merchant:
        assert t["merchant_clean"] == merchant
    from app.core.database import SessionLocal
    from app.models.transaction_source import TransactionSourceRecord
    with user_session("alice") as (db, _):
        assert db.query(TransactionSourceRecord.source_label).scalar() == label


def test_personal_vpa_and_long_numbers_are_stripped(client):
    mail(client, address(client), "Kotak Bank <BankAlerts@kotak.com>", "Alert",
         "Received Rs.500.00 in your Kotak Bank AC X2468 from rahul.s@okaxis on 05-03-24.UPI Ref:412345678902.",
         auth="dkim=pass header.d=kotak.com")
    [t] = txns(client)
    assert t["merchant_raw"] == "R***@okaxis"


def test_unreadable_and_non_transaction_mail(client):
    to = address(client)
    assert mail(client, to, HDFC, "Alert", "Your account has been debited. Amount details are unavailable.") == "unparsed"
    assert mail(client, to, HDFC, "OTP", "Your OTP for the transaction is 482913. Do not share it.") == "not_transaction"
    assert mail(client, to, HDFC, "Offer", "Get a personal loan at 10.5% p.a. today!") == "not_transaction"
    assert txns(client) == []
    assert client.get("/api/inbound", headers=ALICE).json()["unreadable"] == [{"bank": "HDFC Bank", "count": 1}]


@pytest.mark.parametrize("sender, auth, outcome", [
    (HDFC, "dkim=fail header.d=hdfcbank.net", "auth_failed"),                         # forged signature
    (HDFC, "dkim=none; spf=fail smtp.mailfrom=hdfcbank.net", "auth_failed"),
    (HDFC, "dkim=pass header.d=evil.example", "auth_failed"),                          # signed, but by someone else
    ("HDFC <alerts@hdfcbank.net.evil.example>", "dkim=pass header.d=hdfcbank.net.evil.example", "untrusted_sender"),
    ("Some Shop <offers@shop.example>", "dkim=pass header.d=shop.example", "untrusted_sender"),
    ("Google <someone@google.com>", "dkim=pass header.d=google.com", "untrusted_sender"),   # only Google Pay's address counts
    (HDFC, "spf=pass smtp.mailfrom=bounce@google.com", "auth_failed"),                 # SPF passed for Google, not HDFC
])
def test_spoofed_or_unauthenticated_alerts_are_discarded(client, sender, auth, outcome):
    assert mail(client, address(client), sender, "Alert", UPI_DEBIT, auth=auth) == outcome
    assert txns(client) == []
    assert client.get("/api/inbound", headers=ALICE).json()["total"] == 0


GMAIL_CONFIRMATION = ("alice@gmail.com has requested to automatically forward mail to your email address.\n"
                      "Confirmation code: 482913571\n"
                      "To allow alice@gmail.com to automatically forward mail to your address, please click the link below to confirm the request:\n"
                      "https://mail-settings.google.com/mail/vf-%5BANGjdJ8abc%5D-abcdefXYZ\n")


def test_gmail_forwarding_confirmation_is_shown_not_clicked(client):
    to = address(client)
    out = mail(client, to, "Gmail Team <forwarding-noreply@google.com>", "(#482913571) Gmail Forwarding Confirmation - Receive Mail from alice@gmail.com",
               GMAIL_CONFIRMATION, auth="dkim=pass header.d=google.com")
    assert out == "gmail_confirmation"
    c = client.get("/api/inbound", headers=ALICE).json()["gmail_confirmation"]
    assert (c["link"], c["code"]) == ("https://mail-settings.google.com/mail/vf-%5BANGjdJ8abc%5D-abcdefXYZ", "482913571")
    assert client.post("/api/inbound/gmail-confirmation/dismiss", headers=ALICE).json()["gmail_confirmation"] is None
    # a forged one (no Google DKIM) is not shown
    assert mail(client, to, "Gmail Team <forwarding-noreply@google.com>", "Gmail Forwarding Confirmation", GMAIL_CONFIRMATION,
                auth="dkim=fail header.d=google.com") == "untrusted_sender"
    assert client.get("/api/inbound", headers=ALICE).json()["gmail_confirmation"] is None


def test_alert_then_statement_is_one_transaction(client):
    mail(client, address(client), HDFC, "UPI txn", UPI_DEBIT)
    statement = row(date="2024-03-05", description_raw="UPI-SWIGGY-swiggy@icici-XXXX-Payment", amount="450.00",
                    reference="412345678901", source_type="bank_csv", source_label="HDFC Bank")
    res = client.post("/api/import/batch", json={"rows": [statement]}, headers=ALICE).json()
    assert res["duplicates_merged"] == 1
    assert len(txns(client)) == 1


def test_no_raw_email_content_is_written_anywhere(client, caplog):
    caplog.set_level(logging.DEBUG)
    to = address(client)
    distinctive = [
        "If you did not authorize this transaction", "Dear Customer", "InstaAlerts", "You have done a UPI txn",
        "rahul.s@okaxis", "account **1234", "Avl Bal INR 52,000.00", "482913", "personal loan", "Amount details are unavailable",
    ]
    mail(client, to, HDFC, "You have done a UPI txn. Check details!", UPI_DEBIT)
    mail(client, to, "Kotak Bank <BankAlerts@kotak.com>", "Alert",
         "Received Rs.500.00 in your Kotak Bank AC X2468 from rahul.s@okaxis on 05-03-24.UPI Ref:412345678902.",
         auth="dkim=pass header.d=kotak.com")
    mail(client, to, "Axis Bank Alerts <alerts@axisbank.com>", "Alert",
         "INR 1,845.25 debited from A/c no. XX7777 on 01-06-2024 14:22:05 IST at UPI/P2M/415311110000/BIGBASKET. Avl Bal INR 52,000.00",
         auth="dkim=pass header.d=axisbank.com")
    mail(client, to, HDFC, "OTP", "Your OTP for the transaction is 482913. Do not share it.")
    mail(client, to, HDFC, "Offer", "Get a personal loan at 10.5% p.a. today!")
    mail(client, to, HDFC, "Alert", "Your account has been debited. Amount details are unavailable.")
    mail(client, to, "Spoof <alerts@hdfcbank.net>", "You have done a UPI txn", UPI_DEBIT, auth="dkim=fail")
    assert len(txns(client)) == 3

    with owner_engine.connect() as conn:          # the raw rows, past row-level security
        dump = "\n".join(
            str(r[0]) for table in Base.metadata.sorted_tables
            for r in conn.execute(sql(f"SELECT row_to_json(t)::text FROM {table.name} t")))
    logs = caplog.text
    for raw in distinctive:
        assert raw not in dump, f"{raw!r} found in the database"
        assert raw not in logs, f"{raw!r} found in the logs"


def test_regenerate_retires_the_old_address(client):
    old = address(client)
    new = client.post("/api/inbound/regenerate", headers=ALICE).json()["address"]
    assert new != old and address(client) == new
    assert mail(client, old, HDFC, "UPI txn", UPI_DEBIT) == "unknown_recipient"
    assert mail(client, f"Me <{new.upper()}>, other@example.com", HDFC, "UPI txn", UPI_DEBIT) == "parsed"


def test_endpoint_guards(client, monkeypatch):
    payload = {"to": "x@in.example.in", "from": HDFC, "subject": "s", "text": "t", "html": None, "auth_results": ""}
    assert client.post("/internal/inbound-email", json=payload).status_code == 401
    assert client.post("/internal/inbound-email", json=payload, headers={"X-Internal-Secret": "nope"}).status_code == 401
    big = {**payload, "text": "x" * (256 * 1024)}
    assert client.post("/internal/inbound-email", json=big, headers={"X-Internal-Secret": SECRET}).status_code == 413
    assert client.post("/internal/inbound-email", json={"to": "x"}, headers={"X-Internal-Secret": SECRET}).status_code == 422
    assert mail(client, "nobody12345@in.example.in", HDFC, "s", UPI_DEBIT) == "unknown_recipient"
    assert mail(client, "x@elsewhere.example", HDFC, "s", UPI_DEBIT) == "unknown_recipient"
    monkeypatch.setattr(settings, "INBOUND_DOMAIN", "")
    assert client.post("/internal/inbound-email", json=payload, headers={"X-Internal-Secret": SECRET}).status_code == 503
    assert client.get("/api/inbound", headers=ALICE).json()["address"] is None


def test_addresses_are_per_user(client):
    alice, bob = address(client), address(client, BOB)
    assert alice != bob
    mail(client, alice, HDFC, "UPI txn", UPI_DEBIT)
    assert txns(client, BOB) == [] and client.get("/api/inbound", headers=BOB).json()["total"] == 0
    client.post("/api/inbound/regenerate", headers=BOB)
    client.post("/api/inbound/gmail-confirmation/dismiss", headers=BOB)
    assert address(client) == alice
