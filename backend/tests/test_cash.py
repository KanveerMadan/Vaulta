"""Cash wallet (services/cash.py)."""

import json
import uuid
from datetime import date, timedelta

import pytest

from app.core.database import SessionLocal
from app.models.user import User
from app.services import cash, llm, telegram, telegram_bot
from tests.conftest import as_user, user_session, reset_rate_limits
from tests.test_import_batch import row

ALICE, BOB = as_user("alice"), as_user("bob")
TODAY = date.today()
MONTH = f"/api/transactions/summary?period=month&year={TODAY.year}&month={TODAY.month}"


def withdraw(client, amount, desc="ATW-512345XXXXXX6789-S1ANMU12-MUMBAI", day=TODAY, headers=ALICE):
    r = row(date=day.isoformat(), description_raw=desc, amount=amount, reference=None)
    assert client.post("/api/import/batch", json={"rows": [r]}, headers=headers).status_code == 200


def cash_spend(client, amount, merchant="Auto", category="Transport", direction="debit", headers=ALICE):
    res = client.post("/api/transactions", json={"client_id": str(uuid.uuid4()), "date": TODAY.isoformat(), "amount": amount,
                                                 "merchant": merchant, "category": category, "payment_method": "cash",
                                                 "direction": direction}, headers=headers)
    assert res.status_code == 201, res.text


def wallet(client, headers=ALICE):
    return client.get("/api/cash", headers=headers).json()


def spend(client):
    return client.get(MONTH, headers=ALICE).json()["total_spend"]


def cash_card(client):
    return next((c for c in client.get("/api/review", headers=ALICE).json()["items"] if c["type"] == "cash"), None)


@pytest.mark.parametrize("narration", ["ATW-512345XXXXXX6789-S1ANMU12-MUMBAI", "NFS/CASH WDL/412300000000/SBI ATM",
                                       "ATM WDL 0123 MG ROAD", "CASH WITHDRAWAL ATM ABC"])
def test_atm_withdrawal_is_a_transfer_into_the_wallet_not_spending(client, narration):
    withdraw(client, "2000.00", desc=narration.replace("412300000000", "XXXX"))
    [t] = client.get("/api/transactions", headers=ALICE).json()["items"]
    assert (t["kind"], t["cash_flow"]) == ("transfer", "withdrawal")
    assert spend(client) == "0.00"
    assert (wallet(client)["withdrawn"], wallet(client)["balance"]) == ("2000.00", "2000.00")


def test_withdrawal_is_never_paired_with_an_account_credit(client):
    withdraw(client, "2000.00")
    credit = row(date=TODAY.isoformat(), description_raw="NEFT CR FRIEND", amount="2000.00", direction="credit",
                 reference=None, source_label="SBI")
    client.post("/api/import/batch", json={"rows": [credit]}, headers=ALICE)
    by = {t["merchant_raw"]: t for t in client.get("/api/transactions", headers=ALICE).json()["items"]}
    assert by["NEFT CR FRIEND"]["kind"] == "income" and by["ATW-512345XXXXXX6789-S1ANMU12-MUMBAI"]["transfer_group_id"] is None


def test_cash_spend_counts_once_and_cash_received_adds(client):
    withdraw(client, "2000.00")
    cash_spend(client, "150", "Auto", "Transport")
    cash_spend(client, "500", "Rahul", None, direction="credit")
    assert spend(client) == "150.00"                              # the withdrawal isn't spending; the cash spend is, once
    summary = client.get(MONTH, headers=ALICE).json()
    assert [(c["category"], c["total"]) for c in summary["categories"]] == [("Transport", "150.00")]
    assert summary["total_received"] == "500.00"
    w = wallet(client)
    assert (w["withdrawn"], w["received"], w["spent"], w["balance"], w["unaccounted"]) == (
        "2000.00", "500.00", "150.00", "2350.00", "2350.00")
    client.post("/api/budgets", json={"category": "Transport", "monthly_limit": "1000"}, headers=ALICE)
    transport = client.get(MONTH, headers=ALICE).json()["categories"][0]
    assert transport["budget_consumed_pct"] == "15.0"


def test_declaring_cash_in_hand_sets_the_baseline(client):
    withdraw(client, "2000.00")
    cash_spend(client, "1400")
    res = client.post("/api/cash/declare", json={"amount": "300"}, headers=ALICE).json()
    assert (res["expected"], res["declared"], res["gap"]) == ("600.00", "300", "300.00")
    w = res["wallet"]
    assert (w["balance"], w["unaccounted"], w["declared"]) == ("300.00", "0.00", "300.00")
    cash_spend(client, "100")
    assert (wallet(client)["balance"], wallet(client)["unaccounted"]) == ("200.00", "-100.00")
    assert client.post("/api/cash/declare", json={"amount": 300}, headers=ALICE).status_code == 422


@pytest.mark.parametrize("answer, category, expected_spend", [
    ("misc", "Misc cash", "2000.00"),
    ("Food & Dining", "Food & Dining", "2000.00"),
    ("have", None, "1400.00"),
])
def test_weekly_reconciliation_card(client, answer, category, expected_spend):
    withdraw(client, "2000.00", day=TODAY - timedelta(days=8))
    cash_spend(client, "1400")
    card = cash_card(client)
    assert card["question"] == "₹600 cash unaccounted."
    assert [o["value"] for o in card["options"]][-3:] == ["have", "misc", "skip"]
    if answer in [o["value"] for o in card["options"]]:
        assert client.post(f"/api/review/{card['id']}/answer", json={"answer": answer}, headers=ALICE).status_code == 200
    else:   # a category that isn't one of the card's suggestions: allocate from the wallet view
        client.post("/api/cash/reconcile", json={"action": "category", "category": answer}, headers=ALICE)
    assert cash_card(client) is None
    assert spend(client) == expected_spend
    if category:
        assert "Cash (reconciled)" in {t["merchant_raw"] for t in client.get("/api/transactions", headers=ALICE).json()["items"]}
    assert wallet(client)["unaccounted"] == "0.00"


def test_no_card_under_the_threshold_or_once_reconciled(client):
    withdraw(client, "500.00")
    cash_spend(client, "350")
    assert cash_card(client) is None                                  # ₹150 unaccounted
    cash_spend(client, "50", direction="credit", merchant="Change")
    withdraw(client, "300.00")
    assert cash_card(client)["question"] == "₹500 cash unaccounted."
    client.post("/api/cash/reconcile", json={"action": "have"}, headers=ALICE)
    assert cash_card(client) is None                                  # reconciled since the week ended
    withdraw(client, "1000.00")
    assert cash_card(client) is None                                  # new cash this week waits for next week's check


def test_telegram_cash_command_and_weekly_reminder(client, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "configured", lambda: True)
    monkeypatch.setattr(telegram, "call", lambda method, payload: sent.append((method, payload)) or {"ok": True})
    withdraw(client, "2000.00", day=TODAY - timedelta(days=8))
    cash_spend(client, "1400")
    with user_session("alice") as (db, user):
        user.telegram_chat_id = 555
        db.commit()
        assert telegram_bot.send_cash_reminder(db, user) is True
        assert telegram_bot.send_cash_reminder(db, user) is False     # once per week end
    assert sent[0][1]["text"] == "₹600 cash unaccounted this week. What happened to it?"
    reset_rate_limits()
    with SessionLocal() as db:
        telegram_bot.handle_update(db, {"message": {"message_id": 1, "chat": {"id": 555, "type": "private"}, "text": "/cash"}})
        assert "Cash in hand (expected): ₹600" in sent[-1][1]["text"] and "₹600 isn't logged yet" in sent[-1][1]["text"]
        telegram_bot.handle_update(db, {"callback_query": {"id": "c", "data": "cash:misc",
                                                           "message": {"message_id": 2, "chat": {"id": 555, "type": "private"}}}})
    assert sent[-1][1]["text"].startswith("Recorded 600.00 of cash spending under Misc cash")
    assert wallet(client)["unaccounted"] == "0.00" and spend(client) == "2000.00"


def test_cash_wallet_chat_tool(client, monkeypatch):
    withdraw(client, "2000.00")
    cash_spend(client, "150")
    calls = []
    script = [{"content": "", "tool_calls": [{"id": "c", "type": "function", "function": {"name": "cash_wallet", "arguments": "{}"}}]},
              {"content": "You should have ₹1,850 in cash."}]
    monkeypatch.setattr(llm, "complete", lambda messages, *a, **k: calls.append(messages) or script.pop(0))
    res = client.post("/api/chat", json={"message": "how much cash do I have?"}, headers=ALICE).json()
    assert res["tools_used"] == ["cash_wallet"]
    tool = json.loads([m for m in calls[-1] if m["role"] == "tool"][0]["content"])
    assert (tool["balance"], tool["spent"]) == ("1850.00", "150.00")
    assert "ATW-512345XXXXXX6789-S1ANMU12-MUMBAI" not in json.dumps(calls)   # narrations never reach the LLM


def test_wallet_is_per_user(client):
    withdraw(client, "2000.00")
    assert wallet(client, BOB)["withdrawn"] == "0.00"
    client.post("/api/cash/declare", json={"amount": "999"}, headers=BOB)
    client.post("/api/cash/reconcile", json={"action": "misc"}, headers=BOB)
    assert wallet(client)["withdrawn"] == "2000.00" and wallet(client)["declared"] == "0.00"
    assert client.post("/api/cash/reconcile", json={"action": "category", "category": "Bribes"}, headers=ALICE).status_code == 422
