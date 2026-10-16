"""Export my data, the activity log, and Firebase revocation checks on sensitive routes."""

import io
import time
import json
import zipfile

import pytest
from fastapi import HTTPException

import app.core.auth as auth
from tests.conftest import as_user, token_payload
from tests.test_end_to_end import USER, frozen_today, load_three_months  # noqa: F401 (fixture)

BOB = as_user("bob")


def export(client, headers=USER):
    res = client.get("/api/export", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip" and res.headers["cache-control"] == "no-store"
    assert res.headers["content-disposition"].startswith('attachment; filename="vaulta-export-')
    return zipfile.ZipFile(io.BytesIO(res.content))


def test_export_has_everything_decrypted_and_no_key_material(client):
    load_three_months(client)
    client.post("/api/goals", json={"name": "Bike trip", "target_amount": "50000", "target_date": "2024-12-01"}, headers=USER)
    txn = client.get("/api/transactions", headers=USER).json()["items"][0]
    client.patch(f"/api/transactions/{txn['id']}", json={"notes": "=HYPERLINK(\"x\")"}, headers=USER)
    z = export(client)
    names = set(z.namelist())
    assert {"vaulta-export/README.txt", "vaulta-export/data.json", "vaulta-export/csv/transactions.csv",
            "vaulta-export/csv/people.csv", "vaulta-export/csv/goals.csv", "vaulta-export/csv/users.csv"} <= names
    data = json.loads(z.read("vaulta-export/data.json"))
    api_count = client.get("/api/transactions?page_size=200", headers=USER).json()["total"]
    assert len([t for t in data["transactions"] if not t["split_parent_id"]]) == api_count
    assert "UPI-RAVI KUMAR-R***@okaxis-XXXX-Rent" in {t["merchant_raw"] for t in data["transactions"]}   # decrypted
    assert data["goals"][0]["name"] == "Bike trip"
    raw = z.read("vaulta-export/data.json").decode() + "".join(z.read(n).decode() for n in names if n.endswith(".csv"))
    for secret in ("data_key", "k1:", "e1:", "s1:", "inbound_token_hash", "idempotency_key", "firebase_uid"):
        assert secret not in raw
    csv_text = z.read("vaulta-export/csv/transactions.csv").decode()
    assert "'=HYPERLINK" in csv_text                                   # formulas don't run in a spreadsheet
    assert ",-" not in csv_text.split("\n")[0]


def test_export_and_activity_are_per_user(client):
    load_three_months(client)
    client.get("/auth/me", headers=BOB)
    data = json.loads(export(client, BOB).read("vaulta-export/data.json"))
    assert data["transactions"] == [] and [u["email"] for u in data["users"]] == ["bob@test.local"]
    client.patch("/api/settings", json={"ai_chat_enabled": False}, headers=USER)
    assert [e["kind"] for e in client.get("/api/activity", headers=BOB).json()] == ["export", "sign_in", "sign_up"]
    assert "settings_changed" in [e["kind"] for e in client.get("/api/activity", headers=USER).json()]


def test_activity_log_records_account_events(client, monkeypatch):
    monkeypatch.setattr(auth, "verify_firebase_token",
                        lambda token, check_revoked=False: token_payload(token, auth_time=int(time.time()) - 200))
    client.get("/auth/me", headers=USER)
    client.get("/auth/me", headers=USER)                                         # same sign-in: logged once
    monkeypatch.setattr(auth, "verify_firebase_token",
                        lambda token, check_revoked=False: token_payload(token, auth_time=int(time.time()) - 100))
    client.patch("/api/settings", json={"timezone": "Asia/Dubai", "ai_chat_enabled": False}, headers=USER)
    client.post("/api/inbound/regenerate", headers=USER)
    client.post("/api/telegram/link-code", headers=USER)
    client.delete("/api/telegram", headers=USER)
    client.get("/api/export", headers=USER)
    goal = client.post("/api/goals", json={"name": "X", "target_amount": "100", "target_date": "2025-01-01"}, headers=USER).json()
    client.delete(f"/api/goals/{goal['id']}", headers=USER)
    events = client.get("/api/activity", headers=USER).json()
    kinds = [e["kind"] for e in reversed(events)]
    assert kinds == ["sign_up", "sign_in", "sign_in", "settings_changed", "address_regenerated", "telegram_unlinked", "export",
                     "deleted"]
    assert events[-1]["detail"] == {"method": "password"} and events[-2]["detail"] == {"method": "password"}
    assert events[-4]["detail"] == {"fields": ["ai_chat_enabled", "timezone"]}   # names, never values
    assert events[0]["detail"] == {"what": "goal"}
    assert "Asia/Dubai" not in json.dumps(events)


SENSITIVE = [("DELETE", "/auth/me"), ("PATCH", "/auth/me"), ("GET", "/api/export"), ("PATCH", "/api/settings"),
             ("POST", "/api/inbound/regenerate"), ("POST", "/api/telegram/link-code"), ("DELETE", "/api/telegram"),
             ("PATCH", "/api/telegram")]


def test_sensitive_routes_check_for_revoked_sessions(client, monkeypatch):
    client.get("/auth/me", headers=USER)
    seen = []

    def verify(token, check_revoked=False):
        seen.append(check_revoked)
        if check_revoked:
            raise HTTPException(status_code=401, detail=auth.SIGNED_OUT)
        return token_payload(token)
    monkeypatch.setattr(auth, "verify_firebase_token", verify)
    for method, path in SENSITIVE:
        res = client.request(method, path, headers=USER, json={"weekly": True} if path == "/api/telegram" else {})
        assert res.status_code == 401 and res.json()["detail"] == auth.SIGNED_OUT, (method, path)
    assert client.get("/api/transactions", headers=USER).status_code == 200      # ordinary reads don't call Firebase
    assert seen[-1] is False
    assert client.get("/auth/me", headers=USER).status_code == 200                # the account is untouched


def test_revocation_errors_from_firebase_mean_signed_out(monkeypatch):
    def revoked(token, check_revoked=False):
        raise auth.firebase_auth.RevokedIdTokenError("revoked")
    monkeypatch.setattr(auth.firebase_auth, "verify_id_token", revoked)
    with pytest.raises(HTTPException) as e:
        auth.verify_firebase_token("t", check_revoked=True)
    assert e.value.status_code == 401 and e.value.detail == auth.SIGNED_OUT
