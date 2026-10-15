"""Chat agent with a scripted LLM (services/llm.complete is replaced)."""

import copy
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import SessionLocal
from app.models.chat import ChatAction
from app.services import chat as chat_service
from app.services import llm
from tests.conftest import as_user
from tests.test_end_to_end import GOOGLE_PAY, HDFC, HDFC_CARD, SBI, USER, frozen_today, load_three_months  # noqa: F401

BOB = as_user("bob")


class FakeLLM:
    """Replays scripted assistant messages and records every payload sent."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, messages, tools=None, temperature=0.2):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools})
        step = self.script.pop(0) if self.script else {"content": "Done."}
        if isinstance(step, Exception):
            raise step
        return step


def call(name, **args):
    return {"content": "", "tool_calls": [{"id": f"call_{name}", "type": "function",
                                           "function": {"name": name, "arguments": json.dumps(args)}}]}


def say(text):
    return {"content": text}


@pytest.fixture
def fake(monkeypatch):
    def install(*script):
        f = FakeLLM(*script)
        monkeypatch.setattr(llm, "complete", f)
        return f
    return install


def ask(client, message, headers=USER, **extra):
    return client.post("/api/chat", json={"message": message, **extra}, headers=headers)


def tool_results(fake_llm):
    """Tool results in order (the last call's messages carry all of them)."""
    return [json.loads(m["content"]) for m in fake_llm.calls[-1]["messages"] if m["role"] == "tool"]


def test_read_tool_answer_matches_chatpanel_contract(client, fake):
    load_three_months(client)
    f = fake(call("spend_summary", start="2024-06-01", end="2024-06-30", group_by="category"),
             say("You spent ₹25,599 in June; rent was ₹20,000 of it."))
    res = ask(client, "What did I spend in June?")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reply"] == "You spent ₹25,599 in June; rent was ₹20,000 of it."   # ChatPanel reads data.reply
    assert body["tools_used"] == ["spend_summary"]
    assert body["tables"][0]["rows"][:2] == [["Rent & Housing", "₹20,000", 1], ["Shopping", "₹2,000", 1]]
    result = tool_results(f)[0]
    assert (result["total"], result["count"]) == ("25599.00", 7)
    system = f.calls[0]["messages"][0]
    assert system["role"] == "system" and "Friday 28 June 2024" in system["content"]
    assert {t["function"]["name"] for t in f.calls[0]["tools"]} >= {"spend_summary", "search_transactions", "set_budget", "what_if_reduce"}


def test_llm_payload_never_contains_narrations_references_or_vpas(client, fake):
    load_three_months(client)
    # 4 tool rounds + the answer (5 rounds is the cap)
    f = fake(call("search_transactions", limit=50),
             {"content": "", "tool_calls": [  # two tools in one round
                 {"id": "a", "type": "function", "function": {"name": "person_balances", "arguments": "{}"}},
                 {"id": "b", "type": "function", "function": {"name": "income_summary",
                                                              "arguments": json.dumps({"start": "2024-04-01", "end": "2024-06-30"})}}]},
             call("recurring_overview"), call("search_transactions", query="RAVI"), say("ok"))
    ask(client, "Show me everything")
    payload = json.dumps([c["messages"] for c in f.calls], ensure_ascii=False)
    rows = HDFC + SBI + HDFC_CARD + GOOGLE_PAY
    people = {"Priya Nair"}   # a UPI app's "narration" is just the person's name, which is their display label
    for r in rows:
        if r["description_raw"] not in people:
            assert r["description_raw"] not in payload, r["description_raw"]
        if r["reference"]:
            assert r["reference"] not in payload, r["reference"]
    for vpa in ("R***@okaxis", "@okaxis", "zepto@ybl", "zomato@hdfcbank"):
        assert vpa not in payload
    # what it does contain: names, categories, amounts, dates, people's labels
    for expected in ("Netflix", "Rent & Housing", "649.00", "2024-06-10", "Ravi Kumar", "Ankit Jain"):
        assert expected in payload
    found = tool_results(f)[4]
    assert found["count"] == 3 and {t["merchant"] for t in found["transactions"]} == {"Ravi Kumar"}


def test_actions_need_confirmation_tokens_are_single_use_and_per_user(client, fake):
    load_three_months(client)
    fake(call("set_budget", category="Food & Dining", amount=5000), say("I've prepared a ₹5,000 food budget."))
    body = ask(client, "Set my food budget to 5000").json()
    [card] = body["actions"]
    assert card["summary"] == "Set a ₹5,000 monthly budget for Food & Dining"
    assert client.get("/api/budgets", headers=USER).json()["items"] == []            # nothing written yet

    assert client.post("/api/chat/confirm", json={"token": card["token"], "decision": "confirm"}, headers=BOB).status_code == 410
    assert client.get("/api/budgets", headers=USER).json()["items"] == []
    ok = client.post("/api/chat/confirm", json={"token": card["token"], "decision": "confirm"}, headers=USER)
    assert ok.status_code == 200 and ok.json() == {"ok": True, "message": "Budget set: ₹5,000 a month for Food & Dining."}
    assert [(b["category"], b["monthly_limit"]) for b in client.get("/api/budgets", headers=USER).json()["items"]] == [
        ("Food & Dining", "5000.00")]
    assert client.post("/api/chat/confirm", json={"token": card["token"], "decision": "confirm"}, headers=USER).status_code == 410

    fake(call("remove_budget", category="Food & Dining"), say("Ready."))
    card = ask(client, "remove it").json()["actions"][0]
    cancel = client.post("/api/chat/confirm", json={"token": card["token"], "decision": "cancel"}, headers=USER).json()
    assert cancel == {"ok": False, "message": "Cancelled: Remove the Food & Dining budget (₹5,000 a month)."}
    assert len(client.get("/api/budgets", headers=USER).json()["items"]) == 1

    fake(call("remove_budget", category="Food & Dining"), say("Ready."))
    card = ask(client, "remove it").json()["actions"][0]
    with SessionLocal() as db:
        db.query(ChatAction).update({ChatAction.expires_at: datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
    assert client.post("/api/chat/confirm", json={"token": card["token"], "decision": "confirm"}, headers=USER).status_code == 410
    assert client.post("/api/chat/confirm", json={"token": "x" * 43, "decision": "confirm"}, headers=USER).status_code == 410
    with SessionLocal() as db:
        assert all(card["token"] not in (a.token_hash, json.dumps(a.args)) for a in db.query(ChatAction))   # token never stored


def confirm(client, body):
    [card] = body["actions"]
    return client.post("/api/chat/confirm", json={"token": card["token"], "decision": "confirm"}, headers=USER).json()


def test_every_action_tool(client, fake):
    load_three_months(client)
    zepto = next(t for t in client.get("/api/transactions?page_size=200", headers=USER).json()["items"] if t["merchant_clean"] == "Zepto")

    fake(call("recategorize", merchant_or_transaction="Swiggy", category="Shopping"), say("ok"))
    body = ask(client, "Swiggy is shopping")
    assert body.json()["actions"][0]["summary"] == "File all Swiggy transactions, past and future, under Shopping"
    assert confirm(client, body.json())["ok"]
    assert {t["category"] for t in client.get("/api/transactions?page_size=200", headers=USER).json()["items"]
            if t["merchant_clean"] == "Swiggy" and t["kind"] == "spend"} == {"Shopping"}

    fake(call("recategorize", merchant_or_transaction=zepto["id"], category="Food & Dining"), say("ok"))
    assert confirm(client, ask(client, "that zepto was food").json())["message"] == "Changed 1 transaction to Food & Dining."

    fake(call("tag_person", person="Ravi", tag="Rent"), say("ok"))
    assert confirm(client, ask(client, "Ravi is my landlord").json())["message"] == "Ravi Kumar is tagged Rent."
    ravi = next(p for p in client.get("/api/people", headers=USER).json()["people"] if p["name"] == "Ravi Kumar")
    assert ravi["tag"] == "Rent"

    fake(call("mark_kind", transaction_id=zepto["id"], kind="transfer"), say("ok"))
    confirm(client, ask(client, "that was a transfer").json())
    assert next(t for t in client.get("/api/transactions?page_size=200", headers=USER).json()["items"] if t["id"] == zepto["id"])["kind"] == "transfer"

    fake(call("add_cash_expense", amount=150, description="Auto to station", date="2024-06-27"), say("ok"))
    assert confirm(client, ask(client, "150 auto yesterday").json())["message"] == "Added Auto to station, ₹150."
    june = client.get("/api/transactions/summary?period=month&year=2024&month=6", headers=USER).json()
    assert june["total_spend"] == "25349.00"     # 25599 − 400 Zepto (now a transfer) + 150 auto

    # invalid proposals come back to the model as errors and create no card
    f = fake(call("set_budget", category="Bribes", amount=10), call("mark_kind", transaction_id=zepto["id"], kind="income"),
             call("tag_person", person="Nobody", tag="Rent"), say("Sorry."))
    body = ask(client, "do weird things").json()
    assert body["actions"] == []
    assert [r["error"].split(".")[0].split(" '")[0] for r in tool_results(f)] == ["Unknown category", "A debit can't be", "No person matching"]


def test_what_if_is_computed_in_code(client, fake):
    load_three_months(client)
    f = fake(call("what_if_reduce", category_or_merchant="food & dining", percent=50, horizon_months=12), say("ok"))
    ask(client, "what if I halve food?")
    r = tool_results(f)[0]
    # last 3 full months before 28 Jun 2024: Mar 0, Apr 600, May 800 (1200 − 400 refund)
    assert (r["target"], r["monthly_totals"], r["monthly_average"], r["monthly_saving"], r["total_saving"]) == (
        "Food & Dining", ["0.00", "600.00", "800.00"], "466.67", "233.34", "2800.08")


def test_tool_round_limit_timeout_and_unconfigured(client, fake):
    f = fake(*[call("safe_to_spend_today")] * 10)
    body = ask(client, "loop forever").json()
    assert len(f.calls) == chat_service.MAX_TOOL_ROUNDS
    assert body["reply"].startswith("I couldn't work that out")
    fake(llm.LLMError("timeout"))
    assert ask(client, "slow").json()["reply"].startswith("That took too long")
    fake(llm.LLMError("AI isn't configured"))
    res = ask(client, "anyone?")
    assert res.status_code == 200 and res.json()["reply"].startswith("I can't reach the AI service")


def test_rate_limit(client, fake, monkeypatch):
    monkeypatch.setattr(chat_service, "PER_MINUTE", 3)
    fake(*[say("hi")] * 5)
    assert [ask(client, f"q{i}").status_code for i in range(4)] == [200, 200, 200, 429]
    assert ask(client, "q", headers=BOB).status_code == 200            # per user


def test_history_is_kept_per_session_trimmed_and_clearable(client, fake, monkeypatch):
    monkeypatch.setattr(chat_service, "PER_MINUTE", 100)
    session = str(uuid.uuid4())
    fake(*[say(f"answer {i}") for i in range(12)])
    for i in range(12):
        ask(client, f"question {i}", session_id=session)
    history = client.get(f"/api/chat/history?session_id={session}", headers=USER).json()
    assert len(history) == 20 and history[0] == {"role": "user", "content": "question 2"} and history[-1]["content"] == "answer 11"
    f = fake(say("ok"))
    ask(client, "and now?", session_id=session)
    sent = f.calls[0]["messages"]
    # context = the 10 stored turns (questions 2–11), then the new question
    assert [m["content"] for m in sent[1:3]] == ["question 2", "answer 2"] and len(sent) == 1 + 20 + 1
    assert sent[-1]["content"] == "and now?"
    assert client.get(f"/api/chat/history?session_id={session}", headers=BOB).json() == []
    assert client.delete("/api/chat/history", headers=USER).status_code == 204
    assert client.get(f"/api/chat/history?session_id={session}", headers=USER).json() == []


def test_history_older_than_30_days_is_purged(client, fake):
    session = str(uuid.uuid4())
    fake(say("old"), say("new"))
    ask(client, "old question", session_id=session)
    from app.models.chat import ChatMessage
    with SessionLocal() as db:
        db.query(ChatMessage).update({ChatMessage.created_at: datetime.now(timezone.utc) - timedelta(days=31)})
        db.commit()
    ask(client, "new question", session_id=session)
    assert [m["content"] for m in client.get(f"/api/chat/history?session_id={session}", headers=USER).json()] == ["new question", "new"]


def test_ai_chat_toggle(client, fake):
    fake(say("hi"), say("hi"))
    assert client.get("/api/settings", headers=USER).json()["ai_chat_enabled"] is True
    assert client.patch("/api/settings", json={"ai_chat_enabled": False}, headers=USER).json()["ai_chat_enabled"] is False
    res = ask(client, "hello")
    assert res.status_code == 403 and res.json()["detail"] == "AI chat is turned off in settings."
    assert client.post("/api/chat/confirm", json={"token": "x" * 43, "decision": "confirm"}, headers=USER).status_code == 403
    assert ask(client, "hello", headers=BOB).status_code == 200          # someone else's setting
    client.patch("/api/settings", json={"ai_chat_enabled": True}, headers=USER)
    assert ask(client, "hello").status_code == 200
    assert client.patch("/api/settings", json={"ai_chat_enabled": "no"}, headers=USER).status_code == 422


def test_clearing_history_only_clears_your_own(client, fake):
    session = str(uuid.uuid4())
    fake(say("a"), say("b"))
    ask(client, "mine", session_id=session)
    ask(client, "his", session_id=session, headers=BOB)          # same session id, different user
    assert client.delete(f"/api/chat/history?session_id={session}", headers=BOB).status_code == 204
    assert [m["content"] for m in client.get(f"/api/chat/history?session_id={session}", headers=USER).json()] == ["mine", "a"]
