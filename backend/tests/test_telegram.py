"""Telegram bot with the Bot API mocked (services/telegram.call is replaced)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core import clock
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.telegram import TelegramLinkCode
from app.services import llm, telegram, telegram_bot
from tests.conftest import as_user, user_session, reset_rate_limits

ALICE, BOB = as_user("alice"), as_user("bob")
SECRET = "tg-webhook-secret"
CHAT, OTHER_CHAT = 111, 222


@pytest.fixture(autouse=True)
def bot(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(telegram, "configured", lambda: True)
    monkeypatch.setattr(telegram, "call", lambda method, payload: sent.append((method, payload)) or {"ok": True})
    reset_rate_limits()
    return sent


def hook(client, update, secret=SECRET):
    return client.post("/internal/telegram", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": secret})


def say(client, text, chat=CHAT, **extra):
    assert hook(client, {"message": {"message_id": 1, "chat": {"id": chat, "type": "private"}, "text": text, **extra}}).status_code == 200


def tap(client, data, chat=CHAT):
    assert hook(client, {"callback_query": {"id": "cb", "data": data,
                                            "message": {"message_id": 9, "chat": {"id": chat, "type": "private"}}}}).status_code == 200


def replies(sent):
    return [p["text"] for m, p in sent if m in ("sendMessage", "editMessageText")]


def buttons(sent):
    return [b["callback_data"] for m, p in sent if "reply_markup" in p for row in p["reply_markup"]["inline_keyboard"] for b in row]


def link(client, chat=CHAT, headers=ALICE):
    code = client.post("/api/telegram/link-code", headers=headers).json()["code"]
    say(client, f"/start {code}", chat=chat)
    return code


def txns(client, headers=ALICE):
    return client.get("/api/transactions?page_size=200", headers=headers).json()["items"]


def test_webhook_secret(client, monkeypatch):
    update = {"message": {"message_id": 1, "chat": {"id": CHAT, "type": "private"}, "text": "hi"}}
    assert hook(client, update, secret="wrong").status_code == 401
    assert client.post("/internal/telegram", json=update).status_code == 401
    assert client.post("/internal/telegram", json=update, headers={"X-Internal-Secret": settings.INTERNAL_SECRET or "x"}).status_code == 401
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
    assert hook(client, update, secret="").status_code == 503


def test_unlinked_chat_gets_only_link_instructions(client, bot):
    say(client, "150 auto cash")
    say(client, "how much did I spend?")
    say(client, "/today")
    tap(client, "save:00000000-0000-0000-0000-000000000000")
    assert replies(bot) == [telegram_bot.LINK_FIRST] * 4
    assert buttons(bot) == []
    hook(client, {"message": {"message_id": 1, "chat": {"id": -100, "type": "group"}, "text": "150 auto"}})
    assert len(replies(bot)) == 4                       # group chats are ignored entirely


def test_link_codes_are_single_use_expire_and_replace_each_other(client, bot):
    code = link(client)
    assert replies(bot)[-1].startswith("Linked to Vaulta")
    assert client.get("/api/telegram", headers=ALICE).json()["linked"] is True
    say(client, f"/start {code}", chat=OTHER_CHAT)                   # reused by someone else
    assert replies(bot)[-1].startswith("That code is wrong or has expired")

    stale = client.post("/api/telegram/link-code", headers=BOB).json()["code"]
    fresh = client.post("/api/telegram/link-code", headers=BOB).json()["code"]
    say(client, f"/start {stale}", chat=OTHER_CHAT)                  # replaced by a newer code
    assert replies(bot)[-1].startswith("That code is wrong")
    with user_session("bob") as (db, _):
        db.query(TelegramLinkCode).update({TelegramLinkCode.expires_at: datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
    say(client, f"/start {fresh}", chat=OTHER_CHAT)                  # expired
    assert replies(bot)[-1].startswith("That code is wrong")
    assert client.get("/api/telegram", headers=BOB).json()["linked"] is False


def test_nothing_saves_without_the_tick(client, bot):
    link(client)
    say(client, "150 auto cash")
    assert replies(bot)[-1] == "₹150 · Auto · Transport · today · cash"
    entry = buttons(bot)[0].split(":")[1]
    assert buttons(bot) == [f"save:{entry}", f"cat:{entry}", f"cancel:{entry}"]
    assert txns(client) == []
    tap(client, f"cancel:{entry}")
    assert replies(bot)[-1] == "Cancelled. Nothing was saved." and txns(client) == []
    tap(client, f"save:{entry}")                                     # cancelled stays cancelled
    assert replies(bot)[-1] == "That entry is no longer open." and txns(client) == []

    say(client, "2400 dmart yesterday upi")
    entry = buttons(bot)[-1].split(":")[1]
    tap(client, f"cat:{entry}")
    pick = next(b for b in buttons(bot) if b.startswith(f"set:{entry}:") and
                telegram_bot.CATEGORY_CHOICES[int(b.rsplit(":", 1)[1])] == "Shopping")
    tap(client, pick)
    assert "Shopping" in replies(bot)[-1]
    assert txns(client) == []
    tap(client, f"save:{entry}")
    tap(client, f"save:{entry}")                                     # double tap
    [t] = txns(client)
    assert (t["amount"], t["merchant_clean"], t["category"], t["source"]) == ("2400.00", "DMart", "Shopping", "manual")


def test_undo_window(client, bot, monkeypatch):
    link(client)
    say(client, "60 chai")
    tap(client, f"save:{buttons(bot)[0].split(':')[1]}")
    assert len(txns(client)) == 1
    say(client, "/undo")
    assert replies(bot)[-1].startswith("Removed:") and txns(client) == []
    say(client, "/undo")
    assert replies(bot)[-1].startswith("Nothing to undo")

    say(client, "80 chai")
    tap(client, f"save:{buttons(bot)[-1].split(':')[1]}")
    later = datetime.now(timezone.utc) + timedelta(minutes=11)
    monkeypatch.setattr(clock, "now", lambda: later)
    say(client, "/undo")
    assert replies(bot)[-1].startswith("Nothing to undo") and len(txns(client)) == 1


def test_commands(client, bot):
    link(client)
    client.post("/api/budgets", json={"category": None, "monthly_limit": "30000"}, headers=ALICE)
    say(client, "450 swiggy dinner")
    tap(client, f"save:{buttons(bot)[0].split(':')[1]}")
    say(client, "/today")
    assert replies(bot)[-1].startswith("Today: ₹450 spent")
    say(client, "/week")
    assert "This week: ₹450 spent." in replies(bot)[-1] and "of ₹30,000 budget" in replies(bot)[-1]
    say(client, "/safe")
    assert replies(bot)[-1].startswith("Safe to spend today: ₹")
    say(client, "/help")
    assert replies(bot)[-1] == telegram_bot.HELP
    say(client, "photo", photo=[{"file_id": "x"}])
    assert replies(bot)[-1] == telegram_bot.PHOTO
    assert not any(m == "getFile" for m, _ in bot)                    # never downloads the image


def test_questions_go_to_the_assistant_and_actions_need_a_tap(client, bot, monkeypatch):
    link(client)
    script = [{"content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
        "name": "set_budget", "arguments": json.dumps({"category": "Food & Dining", "amount": 5000})}}]},
              {"content": "Ready when you confirm."}]
    monkeypatch.setattr(llm, "complete", lambda *a, **k: script.pop(0))
    say(client, "set my food budget to 5000?")
    assert "Ready when you confirm." in replies(bot)[-2]
    assert replies(bot)[-1] == "Set a ₹5,000 monthly budget for Food & Dining"
    ok = [b for b in buttons(bot) if b.startswith("ok:")][0]
    assert client.get("/api/budgets", headers=ALICE).json()["items"] == []
    tap(client, ok)
    assert replies(bot)[-1] == "Budget set: ₹5,000 a month for Food & Dining."
    assert len(client.get("/api/budgets", headers=ALICE).json()["items"]) == 1
    tap(client, ok)                                                  # single use
    assert replies(bot)[-1].startswith("This confirmation has expired or was already used")

    client.patch("/api/settings", json={"ai_chat_enabled": False}, headers=ALICE)
    say(client, "how much on food?")
    assert replies(bot)[-1].startswith("AI chat is turned off")


def test_rate_limit_and_unlink(client, bot):
    link(client)
    before = len(replies(bot))
    for _ in range(25):
        say(client, "/help")
    assert len(replies(bot)) - before == telegram_bot.RATE_LIMIT - 1   # the /start counted too
    reset_rate_limits()
    say(client, "/unlink")
    assert client.get("/api/telegram", headers=ALICE).json()["linked"] is False
    say(client, "150 auto")
    assert replies(bot)[-1] == telegram_bot.LINK_FIRST
    link(client)
    assert client.delete("/api/telegram", headers=ALICE).status_code == 204
    assert client.get("/api/telegram", headers=ALICE).json()["linked"] is False


def test_other_users_entries_are_not_reachable(client, bot):
    link(client)
    link(client, chat=OTHER_CHAT, headers=BOB)
    say(client, "150 auto")
    entry = buttons(bot)[-1].split(":")[1]
    tap(client, f"save:{entry}", chat=OTHER_CHAT)                     # Bob taps Alice's entry id
    assert replies(bot)[-1] == "That entry is no longer open."
    assert txns(client) == [] and txns(client, BOB) == []
    assert client.patch("/api/telegram", json={"weekly": True}, headers=BOB).json()["weekly"] is True
    assert client.get("/api/telegram", headers=ALICE).json()["weekly"] is False


def test_weekly_summary_on_telegram_once(client, bot, monkeypatch):
    from tests.test_end_to_end import load_three_months, USER
    load_three_months(client)
    link(client, headers=USER)
    client.patch("/api/telegram", json={"weekly": True}, headers=USER)
    monkeypatch.setattr(settings, "INTERNAL_SECRET", "x" * 40)
    monkeypatch.setattr(clock, "now", lambda: datetime(2024, 6, 23, 13, 30, tzinfo=timezone.utc))   # Sunday 19:00 IST
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("off")))
    for _ in range(2):
        res = client.post("/internal/run-reports", headers={"X-Internal-Secret": "x" * 40}).json()
    summaries = [t for t in replies(bot) if t.startswith("Week of 17 Jun")]
    assert len(summaries) == 1 and "Full report:" in summaries[0]
    assert res["telegram"] == 0
