"""Recurring detection (services/recurring.py) and /api/recurring."""

from datetime import date, timedelta
from decimal import Decimal

from app.services.recurring import add_months
from tests.conftest import as_user
from tests.test_import_batch import row

ALICE = as_user("alice")
TODAY = date.today()


def months_ago(n, day_shift=0):
    return (add_months(TODAY, -n) + timedelta(days=day_shift)).isoformat()


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def debit(d, desc, amount, **kw):
    return row(date=d, description_raw=desc, amount=amount, reference=None, **kw)


def load(client, *rows):
    assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=ALICE).status_code == 200
    overview = client.get("/api/recurring", headers=ALICE).json()
    return overview, {s["name"]: s for s in overview["series"]}


def test_monthly_subscription_with_price_hike(client):
    _, series = load(client, *[
        debit(months_ago(3), "NETFLIX COM", "499.00"),
        debit(months_ago(2, 2), "NETFLIX COM", "499.00"),     # ±3 days tolerance
        debit(months_ago(1), "NETFLIX COM", "649.00"),
        debit(days_ago(2), "NETFLIX COM", "649.00"),
    ])
    n = series["Netflix"]
    assert (n["cadence"], n["type"], n["status"], n["occurrences"]) == ("monthly", "subscription", "active", 4)
    assert n["typical_amount"] == "649.00"
    assert n["price_change"] == {"old": "499.00", "new": "649.00"}
    assert n["next_expected"] == add_months(TODAY - timedelta(days=2), 1).isoformat()


def test_weekly_and_yearly(client):
    _, series = load(client, *[debit(days_ago(d), "CULT FIT SESSION", "300.00") for d in (21, 14, 7, 0)],
                     debit(months_ago(24), "AMAZON PRIME", "1499.00"), debit(months_ago(12), "AMAZON PRIME", "1499.00"))
    assert series["Cult Fit Session"]["cadence"] == "weekly"
    assert series["Amazon"]["cadence"] == "yearly"


def test_missed_and_cancelled(client):
    _, series = load(
        client,
        *[debit(days_ago(35 + 30 * k), "ACT FIBERNET", "1100.00") for k in (2, 1, 0)],     # due ~5 days ago → missed
        *[debit(days_ago(50 + 30 * k), "SPOTIFY INDIA", "119.00") for k in (2, 1, 0)],     # 50 days > 1.5×30 → cancelled
    )
    assert series["Broadband"]["status"] == "missed"   # the normalizer names ACT Fibernet "Broadband"
    assert series["Spotify"]["status"] == "cancelled"


def test_rent_to_a_person(client):
    _, series = load(client, *[debit(months_ago(k), "UPI-RAHUL SHARMA-R***@okaxis-XXXX-Rent", "15000.00") for k in (2, 1, 0)])
    rent = series["Rahul Sharma"]
    assert (rent["type"], rent["cadence"], rent["typical_amount"]) == ("rent", "monthly", "15000.00")


def test_not_recurring(client):
    _, series = load(
        client,
        debit(months_ago(2), "IRCTC", "500.00"), debit(months_ago(1), "IRCTC", "2300.00"), debit(months_ago(0), "IRCTC", "900.00"),
        debit(months_ago(1), "BOOKMYSHOW", "400.00"), debit(months_ago(0), "BOOKMYSHOW", "400.00"),   # only 2 monthly
        debit(days_ago(40), "DMART", "800.00"), debit(days_ago(20), "DMART", "800.00"), debit(days_ago(1), "DMART", "800.00"),  # 19–20 day gaps
    )
    assert series == {}


def test_totals_upcoming_and_user_fields_survive_redetection(client):
    overview, series = load(
        client,
        *[debit(months_ago(k, 10), "NETFLIX COM", "649.00") for k in (3, 2, 1)],            # last ~20 days ago, due in ~10
        *[debit(days_ago(d), "CULT FIT SESSION", "300.00") for d in (21, 14, 7, 0)],
    )
    assert Decimal(overview["monthly_committed"]) == Decimal("649.00") + (Decimal("300") * 52 / 12).quantize(Decimal("0.01"))
    assert {s["name"] for s in overview["upcoming"]} == {"Netflix", "Cult Fit Session"}

    gym = series["Cult Fit Session"]
    res = client.patch(f"/api/recurring/{gym['id']}", json={"name": "Gym", "type": "other", "usage": "review"}, headers=ALICE)
    assert (res.json()["name"], res.json()["type"], res.json()["usage"]) == ("Gym", "other", "review")
    netflix = series["Netflix"]
    client.patch(f"/api/recurring/{netflix['id']}", json={"user_status": "dismissed"}, headers=ALICE)

    assert client.post("/api/recurring/refresh", headers=ALICE).status_code == 204
    overview = client.get("/api/recurring", headers=ALICE).json()
    assert [s["name"] for s in overview["series"]] == ["Gym"]
    assert overview["monthly_committed"] == "1300.00"
    for bad in [{}, {"type": "loan"}, {"user_status": "maybe"}, {"name": ""}]:
        assert client.patch(f"/api/recurring/{gym['id']}", json=bad, headers=ALICE).status_code == 422
