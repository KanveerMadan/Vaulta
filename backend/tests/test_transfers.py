"""Own-account transfer detection (services/detection.py)."""

from tests.conftest import as_user, user_session
from tests.test_import_batch import row

ALICE = as_user("alice")


def load(client, *rows):
    res = client.post("/api/import/batch", json={"rows": list(rows)}, headers=ALICE)
    assert res.status_code == 200, res.text
    return res.json(), {t["merchant_raw"]: t for t in client.get("/api/transactions", headers=ALICE).json()["items"]}


def hdfc(**kw):
    return row(reference=None, source_label="HDFC Bank", **kw)


def sbi(**kw):
    return row(reference=None, source_label="SBI", **kw)


def test_pair_across_accounts_within_3_days(client):
    result, txns = load(
        client,
        hdfc(date="2024-03-05", description_raw="IMPS-ROHIT-RENT POOL", amount="15000.00"),
        sbi(date="2024-03-07", description_raw="IMPS CR FROM HDFC", amount="15000.00", direction="credit"),
    )
    a, b = txns["IMPS-ROHIT-RENT POOL"], txns["IMPS CR FROM HDFC"]
    assert a["kind"] == b["kind"] == "transfer"
    assert a["transfer_group_id"] == b["transfer_group_id"] is not None
    assert result["transfers_flagged"] == 2


def test_not_paired_when_too_far_apart_same_account_or_small_unsignalled(client):
    _, txns = load(
        client,
        hdfc(date="2024-03-01", description_raw="DEBIT A", amount="5000.00"),
        sbi(date="2024-03-05", description_raw="CREDIT A", amount="5000.00", direction="credit"),     # 4 days
        hdfc(date="2024-03-10", description_raw="DEBIT B", amount="7000.00"),
        hdfc(date="2024-03-10", description_raw="CREDIT B", amount="7000.00", direction="credit"),    # same account
        hdfc(date="2024-03-12", description_raw="DEBIT C", amount="400.00"),
        sbi(date="2024-03-12", description_raw="CREDIT C", amount="400.00", direction="credit"),      # small, no signal
    )
    assert {t["kind"] for t in txns.values()} == {"spend", "income"}


def test_small_amount_pairs_with_a_transfer_signal(client):
    _, txns = load(
        client,
        hdfc(date="2024-03-12", description_raw="UPI-SELF-XXXX", amount="400.00"),
        sbi(date="2024-03-12", description_raw="UPI CR 412", amount="400.00", direction="credit"),
    )
    assert {t["kind"] for t in txns.values()} == {"transfer"}


def test_ambiguous_pairs_are_left_alone(client):
    _, txns = load(
        client,
        hdfc(date="2024-03-05", description_raw="NEFT OUT", amount="20000.00"),
        sbi(date="2024-03-05", description_raw="NEFT IN ONE", amount="20000.00", direction="credit"),
        row(date="2024-03-06", description_raw="NEFT IN TWO", amount="20000.00", direction="credit", reference=None, source_label="Axis Bank"),
    )
    assert {t["kind"] for t in txns.values()} == {"spend", "income"}


def test_card_bill_payment_pairs_with_bank_debit(client):
    _, txns = load(
        client,
        hdfc(date="2024-03-18", description_raw="BILLPAY-HDFC CC PAYMENT", amount="15000.00"),
        row(date="2024-03-18", description_raw="PAYMENT RECEIVED - THANK YOU", amount="15000.00", direction="credit",
            reference=None, source_type="credit_card", source_label="HDFC Bank Credit Card", type="transfer"),
    )
    a, b = txns["BILLPAY-HDFC CC PAYMENT"], txns["PAYMENT RECEIVED - THANK YOU"]
    assert a["kind"] == b["kind"] == "transfer" and a["transfer_group_id"] == b["transfer_group_id"]


def test_user_kind_is_never_overridden(client):
    _, txns = load(client, hdfc(date="2024-03-05", description_raw="TO MOM", amount="15000.00"))
    client.patch(f"/api/transactions/{txns['TO MOM']['id']}", json={"kind": "spend"}, headers=ALICE)
    _, txns = load(client, sbi(date="2024-03-05", description_raw="FROM HDFC", amount="15000.00", direction="credit"))
    assert txns["TO MOM"]["kind"] == "spend"
    assert txns["FROM HDFC"]["kind"] == "income"   # its only partner is locked as spend


def test_one_sided_signal_is_not_guessed(client):
    from app.core.database import SessionLocal
    from app.models.user import User
    from app.services.detection import run_detection
    _, txns = load(client, hdfc(date="2024-03-05", description_raw="TRANSFER TO OWN A/C 4321", amount="8000.00"))
    assert txns["TRANSFER TO OWN A/C 4321"]["kind"] == "spend"
    with user_session("alice") as (db, _user):
        ctx = run_detection(db, _user)
        assert [str(i) for i in ctx.review_transfer_ids] == [txns["TRANSFER TO OWN A/C 4321"]["id"]]


def test_reanalyze_is_idempotent(client):
    load(client, hdfc(date="2024-03-05", description_raw="OUT", amount="15000.00"),
         sbi(date="2024-03-06", description_raw="IN", amount="15000.00", direction="credit"))
    first = client.get("/api/transactions", headers=ALICE).json()["items"]
    assert client.post("/api/transactions/reanalyze", headers=ALICE).status_code == 204
    assert client.get("/api/transactions", headers=ALICE).json()["items"] == first
