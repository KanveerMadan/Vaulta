"""Savings goals: contributions, required monthly, pace, projection, estimate, chat, reports."""

import json

import pytest

from app.core import clock
from app.services import llm
from tests.conftest import as_user
from tests.test_end_to_end import TODAY, USER, load_three_months

BOB = as_user("bob")


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)   # 2024-06-28


def new_goal(client, headers=USER, **body):
    res = client.post("/api/goals", json={"name": "Laptop", "target_amount": "60000", "target_date": "2024-12-31", **body},
                      headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def put(client, goal, amount, day=None, headers=USER):
    res = client.post(f"/api/goals/{goal['id']}/entries", json={"amount": amount, **({"date": day} if day else {})}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_progress_required_monthly_and_projection(client):
    g = new_goal(client)
    assert (g["saved"], g["remaining"], g["months_left"], g["required_monthly"], g["status"]) == (
        "0.00", "60000.00", 6, "10000.00", "not_started")
    put(client, g, "5000", "2024-05-10")
    g = put(client, g, "5000", "2024-06-20")
    assert (g["saved"], g["remaining"], g["required_monthly"], g["monthly_pace"]) == ("10000.00", "50000.00", "8333.33", "5000.00")
    assert (g["projected_date"], g["status"], g["progress_pct"]) == ("2025-04-29", "behind", "16.7")
    g = put(client, g, "40000")
    assert (g["monthly_pace"], g["projected_date"], g["status"]) == ("25000.00", "2024-07-11", "on_track")
    g = put(client, g, "-1000")                                   # took some back out
    assert g["saved"] == "49000.00" and len(g["entries"]) == 4
    g = client.delete(f"/api/goals/{g['id']}/entries/{g['entries'][-1]['id']}", headers=USER).json()
    g = put(client, g, "10000")
    assert (g["status"], g["remaining"], g["required_monthly"], g["projected_date"]) == ("done", "0.00", "0.00", "2024-06-28")
    assert client.get("/api/transactions", headers=USER).json()["total"] == 0   # entries are not transactions


def test_savings_rate_estimate_is_separate(client):
    load_three_months(client)
    g = new_goal(client, category="Food & Dining")
    g = put(client, g, "10000", "2024-06-01")
    # Mar–May: income 1,60,000, spend 47,298 → saved 1,12,702 ÷ 3
    assert g["estimate"]["monthly_savings"] == "37567.33"
    assert g["estimate"]["projected_date"] == "2024-08-08" and "Estimate" in g["estimate"]["label"]
    assert g["saved"] == "10000.00"                              # the estimate never counts as saved
    assert g["category_spend"] == {"category": "Food & Dining", "this_month": "300.00"}


def test_validation(client):
    bad = [{"target_date": "2024-06-28"}, {"target_amount": "0"}, {"category": "Bribes"}, {"name": ""}, {"extra": 1}]
    for body in bad:
        res = client.post("/api/goals", json={"name": "X", "target_amount": "100", "target_date": "2025-01-01", **body}, headers=USER)
        assert res.status_code == 422, body
    g = new_goal(client)
    assert client.post(f"/api/goals/{g['id']}/entries", json={"amount": "0"}, headers=USER).status_code == 422
    assert client.post(f"/api/goals/{g['id']}/entries", json={"amount": "5", "date": "2024-07-01"}, headers=USER).status_code == 422
    assert client.patch(f"/api/goals/{g['id']}", json={"target_date": "2024-01-01"}, headers=USER).status_code == 422
    g = client.patch(f"/api/goals/{g['id']}", json={"name": " Bike ", "category": "Transport"}, headers=USER).json()
    assert (g["name"], g["category"]) == ("Bike", "Transport")
    assert client.patch(f"/api/goals/{g['id']}", json={"category": None}, headers=USER).json()["category"] is None


def test_goals_are_per_user(client):
    g = new_goal(client)
    assert client.get("/api/goals", headers=BOB).json() == {"items": []}
    assert client.patch(f"/api/goals/{g['id']}", json={"name": "x"}, headers=BOB).status_code == 404
    assert client.post(f"/api/goals/{g['id']}/entries", json={"amount": "5"}, headers=BOB).status_code == 404
    g = put(client, g, "100")
    assert client.delete(f"/api/goals/{g['id']}/entries/{g['entries'][0]['id']}", headers=BOB).status_code == 404
    assert client.delete(f"/api/goals/{g['id']}", headers=BOB).status_code == 404
    assert client.get("/api/goals", headers=USER).json()["items"][0]["saved"] == "100.00"
    assert client.delete(f"/api/goals/{g['id']}", headers=USER).status_code == 204
    assert client.get("/api/goals", headers=USER).json() == {"items": []}


def _chat(client, monkeypatch, calls):
    script = [{"content": "", "tool_calls": [{"id": f"c{i}", "type": "function",
                                              "function": {"name": name, "arguments": json.dumps(args)}}]}
              for i, (name, args) in enumerate(calls)] + [{"content": "Done."}]
    seen = []
    monkeypatch.setattr(llm, "complete", lambda messages, *a, **k: seen.append(messages) or script.pop(0))
    return client.post("/api/chat", json={"message": "goal"}, headers=USER).json(), seen


def test_chat_creates_goals_only_after_confirmation(client, monkeypatch):
    res, _ = _chat(client, monkeypatch, [("create_goal", {"name": "Goa trip", "target_amount": 30000, "target_date": "2024-12-01"})])
    [action] = res["actions"]
    assert action["summary"] == "Create a goal: Goa trip, ₹30,000 by 01 Dec 2024"
    assert client.get("/api/goals", headers=USER).json()["items"] == []
    done = client.post("/api/chat/confirm", json={"token": action["token"], "decision": "confirm"}, headers=USER).json()
    assert done == {"ok": True, "message": "Goal created: Goa trip, ₹30,000 by 01 Dec 2024."}

    res, _ = _chat(client, monkeypatch, [("add_to_goal", {"goal": "goa", "amount": 5000})])
    action = res["actions"][0]
    assert action["summary"] == "Record ₹5,000 put towards Goa trip"
    client.post("/api/chat/confirm", json={"token": action["token"], "decision": "confirm"}, headers=USER)

    res, seen = _chat(client, monkeypatch, [("goal_status", {})])
    tool = json.loads([m for m in seen[-1] if m["role"] == "tool"][0]["content"])
    [goal] = tool["goals"]
    assert (goal["name"], goal["saved"], goal["required_monthly"], goal["status"]) == ("Goa trip", "5000.00", "4166.67", "on_track")
    assert res["tables"][0]["rows"] == [["Goa trip", "₹5,000", "₹30,000", "2024-12-01"]]

    res, _ = _chat(client, monkeypatch, [("create_goal", {"name": "Past", "target_amount": 10, "target_date": "2024-01-01"})])
    assert res["actions"] == []


def test_goals_in_monthly_report(client):
    load_three_months(client)
    put(client, new_goal(client), "12000", "2024-06-02")
    report = client.post("/api/reports/generate", json={"period_type": "monthly", "date": "2024-05-31"}, headers=USER).json()
    [goal] = report["data"]["goals"]
    assert (goal["name"], goal["saved"], goal["status"]) == ("Laptop", "12000.00", "on_track")
    weekly = client.post("/api/reports/generate", json={"period_type": "weekly", "date": "2024-06-16"}, headers=USER).json()
    assert "goals" not in weekly["data"]
