"""
Merchant categoriser (services/categorizer.py): order, fallback, personal memory, explanations, re-categorisation,
metrics, and parity with the browser and the training code. Most tests use a tiny hand-made model so they don't
depend on the trained weights; test_parity_with_the_training_code uses the shipped model.
"""

import gzip
import json
import logging
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import categorizer
from app.services.merchant_normalizer import normalize
from tests.conftest import as_user, user_session
from tests.test_import_batch import post, row

ALICE, BOB = as_user("alice"), as_user("bob")
ROOT = Path(__file__).resolve().parents[2]
PARITY = ROOT / "fixtures" / "merchant_model_parity.json"

TINY = {
    "kind": "char-ngram-tfidf-logreg", "ngram_range": [1, 5], "scale": 1.0, "temperature": 1.0, "threshold": 0.6,
    "labels": ["food.street_food", "groceries.kirana", "income.salary", "shopping.fashion"],
    "bias": [0.0, 0.0, 0.0, 0.0],
    "idf": {" tea ": 1.0, "stall": 1.0, "kiran": 1.0, "salar": 1.0, "garme": 1.0},
    "weights": {" tea ": [0, 6], "stall": [0, 6], "kiran": [1, 9], "salar": [2, 9], "garme": [3, 9]},
}


@pytest.fixture
def tiny_model(tmp_path, monkeypatch):
    path = tmp_path / "model.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump(TINY, f)
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"names": ["Ganesh Garments Emporium"], "threshold": 0.8, "n": [3, 4, 5]}))
    monkeypatch.setattr(categorizer, "MODEL_FILE", path)
    monkeypatch.setattr(categorizer, "INDEX_FILE", index)
    monkeypatch.setattr(settings, "MERCHANT_MODEL_ENABLED", True)
    categorizer.model.cache_clear()
    categorizer._index.cache_clear()
    yield
    categorizer.model.cache_clear()
    categorizer._index.cache_clear()


def txns(client, headers=ALICE):
    return {t["merchant_raw"]: t for t in client.get("/api/transactions", headers=headers).json()["items"]}


def test_order_known_merchant_then_model_then_review(client, tiny_model):
    post(client, [row(description_raw="UPI-SWIGGY-swiggy@ybl-Payment", reference="412345678901"),
                  row(description_raw="UPI-RAJU KIRANA-R***@okaxis-Payment", reference="412345678902"),
                  row(description_raw="UPI-QWERTY ZXCV-Q***@ybl-Payment", reference="412345678903")])
    t = txns(client)
    swiggy, kirana, unknown = t["UPI-SWIGGY-swiggy@ybl-Payment"], t["UPI-RAJU KIRANA-R***@okaxis-Payment"], t["UPI-QWERTY ZXCV-Q***@ybl-Payment"]
    assert (swiggy["category"], swiggy["subcategory"]) == ("Food & Dining", "food.delivery")        # known merchant wins
    assert (kirana["category"], kirana["subcategory"]) == ("Groceries", "groceries.kirana")         # the model
    assert unknown["category"] is None                                                              # → review queue
    why = client.get(f"/api/transactions/{kirana['id']}/explanation", headers=ALICE).json()
    assert why["source"] == "model" and "% sure this is Kirana & general stores" in why["text"]
    assert client.get(f"/api/transactions/{swiggy['id']}/explanation", headers=ALICE).json()["source"] == "known_merchant"
    assert client.get(f"/api/transactions/{unknown['id']}/explanation", headers=ALICE).json()["source"] == "none"
    assert client.get(f"/api/transactions/{kirana['id']}/explanation", headers=BOB).status_code == 404


def test_income_is_only_for_credits(client, tiny_model):
    post(client, [row(description_raw="NEFT-ACME SALARY-Payment", reference="412345678901"),
                  row(description_raw="NEFT CR-ACME SALARY-SAL", direction="credit", reference="412345678902")])
    t = txns(client)
    assert t["NEFT-ACME SALARY-Payment"]["category"] is None
    assert (t["NEFT CR-ACME SALARY-SAL"]["category"], t["NEFT CR-ACME SALARY-SAL"]["subcategory"]) == ("Income", "income.salary")


def test_fallback_to_rules_when_disabled_or_missing(client, tiny_model, monkeypatch):
    monkeypatch.setattr(settings, "MERCHANT_MODEL_ENABLED", False)
    post(client, [row(description_raw="UPI-RAJU KIRANA-R***@okaxis-Payment", reference="412345678902"),
                  row(description_raw="UPI-SWIGGY-swiggy@ybl-Payment", reference="412345678901")])
    t = txns(client)
    assert t["UPI-RAJU KIRANA-R***@okaxis-Payment"]["category"] is None          # the model isn't asked
    assert t["UPI-SWIGGY-swiggy@ybl-Payment"]["category"] == "Food & Dining"     # rules still work
    monkeypatch.setattr(settings, "MERCHANT_MODEL_ENABLED", True)
    monkeypatch.setattr(categorizer, "MODEL_FILE", Path("/nonexistent/model.json.gz"))
    categorizer.model.cache_clear()
    assert not categorizer.enabled() and categorizer.predict("RAJU KIRANA") is None


def test_on_device_prediction_is_used_and_checked(client, tiny_model):
    rows = [row(description_raw="UPI-NEW SHOP-N***@ybl-Payment", reference="412345678901",
                predicted_subcategory="shopping.footwear", predicted_confidence=0.93)]
    post(client, rows)
    t = txns(client)["UPI-NEW SHOP-N***@ybl-Payment"]
    assert t["subcategory"] == "shopping.footwear"
    assert "worked out on your device" in client.get(f"/api/transactions/{t['id']}/explanation", headers=ALICE).json()["text"]
    bad = post(client, [row(reference="412345678909", predicted_subcategory="DROP TABLE", predicted_confidence=0.9)])
    assert bad.status_code == 422
    unknown = post(client, [row(description_raw="UPI-OTHER SHOP-O***@ybl", reference="412345678908",
                                predicted_subcategory="made.up", predicted_confidence=0.99)])
    assert unknown.status_code == 200 and txns(client)["UPI-OTHER SHOP-O***@ybl"]["category"] is None  # not a taxonomy id


def test_personal_memory_overrides_the_model(client, tiny_model):
    post(client, [row(description_raw="UPI-SHARMA TEA STALL-S***@ybl-Payment", reference="412345678901")])
    first = txns(client)["UPI-SHARMA TEA STALL-S***@ybl-Payment"]
    assert first["subcategory"] == "food.street_food"
    client.patch(f"/api/transactions/{first['id']}", json={"subcategory": "food.canteen"}, headers=ALICE)
    # a later, slightly different narration of the same shop follows the user's correction, not the model
    post(client, [row(description_raw="POS SHARMA TEA STALL BANGALORE", date="2024-03-09", reference="412345678902")])
    second = txns(client)["POS SHARMA TEA STALL BANGALORE"]
    assert (second["category"], second["subcategory"]) == ("Food & Dining", "food.canteen")
    why = client.get(f"/api/transactions/{second['id']}/explanation", headers=ALICE).json()
    assert why["source"] == "personal"
    # someone else's corrections never apply
    post(client, [row(description_raw="POS SHARMA TEA STALL BANGALORE", date="2024-03-09", reference="412345678902")], headers=BOB)
    assert txns(client, BOB)["POS SHARMA TEA STALL BANGALORE"]["subcategory"] == "food.street_food"


def test_recategorising_is_dry_run_reversible_and_never_touches_corrections(client, tiny_model, monkeypatch):
    monkeypatch.setattr(settings, "MERCHANT_MODEL_ENABLED", False)          # imported under the rules alone
    post(client, [row(description_raw="UPI-RAJU KIRANA-R***@okaxis", reference="412345678901"),
                  row(description_raw="UPI-GUPTA KIRANA-G***@okaxis", reference="412345678902"),
                  row(description_raw="UPI-ANAND GARMENTS-A***@okaxis", reference="412345678903")])
    before = txns(client)
    corrected = before["UPI-GUPTA KIRANA-G***@okaxis"]
    client.patch(f"/api/transactions/{corrected['id']}", json={"category": "Shopping"}, headers=ALICE)
    monkeypatch.setattr(settings, "MERCHANT_MODEL_ENABLED", True)

    plan = client.post("/api/categories/recategorise", json={"dry_run": True}, headers=ALICE).json()
    assert plan["changed"] == 2 and plan["summary"] == {"Uncategorized → Groceries": 1, "Uncategorized → Shopping": 1}
    assert txns(client)["UPI-RAJU KIRANA-R***@okaxis"]["category"] is None                  # a dry run writes nothing

    run = client.post("/api/categories/recategorise", json={"dry_run": False}, headers=ALICE).json()
    after = txns(client)
    assert after["UPI-RAJU KIRANA-R***@okaxis"]["subcategory"] == "groceries.kirana"
    assert after["UPI-ANAND GARMENTS-A***@okaxis"]["subcategory"] == "shopping.fashion"
    assert (after["UPI-GUPTA KIRANA-G***@okaxis"]["category"], after["UPI-GUPTA KIRANA-G***@okaxis"]["subcategory"]) == ("Shopping", None)

    # a row corrected after the run keeps the correction through undo
    client.patch(f"/api/transactions/{after['UPI-ANAND GARMENTS-A***@okaxis']['id']}", json={"category": "Travel"}, headers=ALICE)
    assert client.post(f"/api/categories/recategorise/{run['run_id']}/undo", headers=BOB).status_code == 404
    assert client.post(f"/api/categories/recategorise/{run['run_id']}/undo", headers=ALICE).json() == {"restored": 1}
    undone = txns(client)
    assert undone["UPI-RAJU KIRANA-R***@okaxis"]["category"] is None
    assert undone["UPI-ANAND GARMENTS-A***@okaxis"]["category"] == "Travel"
    assert undone["UPI-GUPTA KIRANA-G***@okaxis"]["category"] == "Shopping"
    assert client.post(f"/api/categories/recategorise/{run['run_id']}/undo", headers=ALICE).json() == {"restored": 0}


def test_merchant_resolution_names_known_brands_only(client, tiny_model):
    post(client, [row(description_raw="POS GANESH GARMENTS EMPORIUM PUNE", reference="412345678901"),
                  row(description_raw="POS RAMESH GARMENTS PUNE", reference="412345678902")])
    t = txns(client)
    assert t["POS GANESH GARMENTS EMPORIUM PUNE"]["merchant_clean"] == "Ganesh Garments Emporium"
    assert t["POS RAMESH GARMENTS PUNE"]["merchant_clean"] is None


def test_model_metrics_are_aggregate_counts(client, tiny_model, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_SECRET", "test-internal-secret")
    post(client, [row(description_raw="UPI-RAJU KIRANA-R***@okaxis", reference="412345678901"),
                  row(description_raw="UPI-SWIGGY-swiggy@ybl", reference="412345678902")])
    kirana = txns(client)["UPI-RAJU KIRANA-R***@okaxis"]
    client.patch(f"/api/transactions/{kirana['id']}", json={"category": "Shopping"}, headers=ALICE)
    client.patch(f"/api/transactions/{kirana['id']}", json={"category": "Travel"}, headers=ALICE)   # counted once
    assert client.get("/internal/model-metrics").status_code == 401
    res = client.get("/internal/model-metrics", headers={"X-Internal-Secret": settings.INTERNAL_SECRET})
    by = res.json()["by_source"]
    assert by["model"] == {"categorised": 1, "corrected": 1, "correction_rate": 1.0}
    assert by["known_merchant"]["categorised"] == 1 and by["known_merchant"]["corrected"] == 0
    assert "KIRANA" not in res.text.upper() and "SWIGGY" not in res.text.upper()


def test_no_merchant_strings_in_logs(client, tiny_model, caplog):
    caplog.set_level(logging.DEBUG)
    post(client, [row(description_raw="UPI-RAJU KIRANA-R***@okaxis", reference="412345678901")])
    kirana = txns(client)["UPI-RAJU KIRANA-R***@okaxis"]
    client.patch(f"/api/transactions/{kirana['id']}", json={"subcategory": "groceries.dairy"}, headers=ALICE)
    client.post("/api/categories/recategorise", json={"dry_run": False}, headers=ALICE)
    client.get(f"/api/transactions/{kirana['id']}/explanation", headers=ALICE)
    logs = "\n".join(r.getMessage() for r in caplog.records).upper()
    assert "KIRANA" not in logs and "RAJU" not in logs


def test_parity_with_the_training_code():
    """The shipped model gives the answers ml/ recorded for it (ml/export.py writes the fixture with the model)."""
    categorizer.model.cache_clear()
    if not categorizer.MODEL_FILE.exists():
        assert not PARITY.exists(), "a parity fixture without a shipped model"
        return
    cases = json.loads(PARITY.read_text())
    assert len(cases) >= 200
    for c in cases:
        p = categorizer.predict(c["text"])
        assert p is not None and p.subcategory == c["subcategory"], c["text"]
        assert abs(p.confidence - c["confidence"]) < 1e-9
        known = normalize(categorizer.merchant_text(c["text"]))
        assert (known.subcategory if known.confidence >= 0.5 else None) == c["known_merchant"], c["text"]
        assert categorizer.resolve_merchant(c["text"]) == c["resolved"], c["text"]


def test_training_export_takes_only_consenting_users_corrections(client, tmp_path, monkeypatch, capsys):
    import sys
    from scripts import export_training_corrections as export
    for who in (ALICE, BOB):
        post(client, [row(description_raw="UPI-RAJU KIRANA-R***@okaxis", reference="412345678901")], headers=who)
        t = txns(client, who)["UPI-RAJU KIRANA-R***@okaxis"]
        client.patch(f"/api/transactions/{t['id']}", json={"subcategory": "groceries.dairy"}, headers=who)
    assert client.patch("/api/settings", json={"ml_training_consent": True}, headers=ALICE).status_code == 200
    out = tmp_path / "corrections.jsonl"
    monkeypatch.setattr(sys, "argv", ["export", "--out", str(out)])
    export.main()
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert rows == [{"text": "UPI-RAJU KIRANA-R***@okaxis", "label": "groceries.dairy", "source": "correction"}]
    printed = capsys.readouterr().out
    assert "consenting" in printed and "KIRANA" not in printed.upper()
