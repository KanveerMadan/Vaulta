"""
Merchant resolution: which catalogue brand a narration is from, by nearest neighbour over character 3–5-gram sets
(idf-weighted containment: how much of the brand name's n-gram weight appears in the narration). Used for the
display name (merchant_clean) when the normalizer doesn't know the merchant. Generic descriptors ("Medical Store",
"Salary Credit") are left out of the index: they name a kind of shop, not a merchant.

The threshold is tuned on validation narrations for precision; local shops (never in the index) measure how often a
narration is wrongly resolved. Exported as artifacts/merchant_index.json (names only; idf is recomputed on load).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from common import DATA, name_stems
from features import normalize

N = (3, 4, 5)
MIN_PRECISION = 0.95


# Payment rails, gateways, banks, UPI handles, remarks and cities: in narrations they surround the merchant, so they
# never count towards a match (and brands that are only these words, like Paytm or BillDesk, aren't in the index)
RAIL_WORDS = set("""upi dr cr p0m p0a to transfer neft imps nach ecs ach bbps billpay bil bpay pos pcd pg payment payments pay
paid via app sent using collect request txn bill order na in from by xxxx xxxxxxxxxxxx credit debit payout credited
razorpay rzp payu payumoney cashfree cf ccavenue ccav billdesk paytm juspay easebuzz pinelabs phonepe amazonpay gpay
googlepay merchant ybl okaxis oksbi okicici okhdfcbank axl ibl icici hdfcbank axisbank apl fbpe hdfc icic sbin utib
kkbk yesb punb barb idib cnrb indb fdrl bank state of india axis kotak mahindra yes pnb baroda autopay si tad ib
bangalore bengaluru blr mumbai mum new delhi gurgaon gurugram noida hyderabad hyd chennai pune kolkata ahmedabad jaipur
lucknow kochi chandigarh indore thane navi coimbatore mysore nagpur surat vadodara bhopal patna goa vizag""".split())


def words(text: str) -> list[str]:
    """Same as merchant_words in backend/app/services/categorizer.py."""
    return [w for w in normalize(text).split(" ")
            if len(w) > 1 and w not in RAIL_WORDS and not w.startswith("@") and not set(w) <= set("0x")]


def merchant_text(text: str) -> str:
    """Same as merchant_text in backend/app/services/categorizer.py: the words the known-merchant step matches."""
    return " ".join(t for t in re.split(r"[^A-Za-z0-9&.']+", text or "") if words(t))


def grams(text: str) -> set[str]:
    out = set()
    for word in words(text):
        w = f" {word} "
        for n in N:
            out.update(w[i:i + n] for i in range(len(w) - n + 1))
    return out


def generic_words() -> set[str]:
    words = set()
    for line in (DATA / "local_shops.txt").read_text().splitlines():
        if ":" in line and not line.startswith("#"):
            words.update(normalize(line.split(":", 1)[1].replace(";", " ")).split())
    words |= set(("store stores shop centre center stall fees fee payment payments charges bill bills salary credit "
                  "transfer account deposit interest tax challan recharge booking tickets ticket services service "
                  "online app cash withdrawal atm card monthly rent maintenance agency classes clinic hospital "
                  "market mart bazaar point corner wala the and of to for with my your self own").split())
    for stem in name_stems():                       # "Sharma Kirana" is a kind of shop with a family name, not a brand
        words.update(normalize(stem).split())
    return words


class Index:
    def __init__(self, names: list[str]):
        self.names = names
        self.grams = [grams(n) for n in names]
        df = defaultdict(int)
        for g in self.grams:
            for x in g:
                df[x] += 1
        self.idf = {x: math.log(len(names) / c) + 1.0 for x, c in df.items()}
        self.total = [sum(self.idf[x] for x in g) or 1.0 for g in self.grams]
        self.postings = defaultdict(list)
        for i, g in enumerate(self.grams):
            for x in g:
                self.postings[x].append(i)

    def resolve(self, text: str) -> tuple[str | None, float]:
        """(name, score) of the best match, ties going to the longer name; (None, 0) if nothing shares an n-gram."""
        score = defaultdict(float)
        for x in grams(text):
            for i in self.postings.get(x, ()):
                score[i] += self.idf[x]
        if not score:
            return None, 0.0
        i = max(score, key=lambda i: (round(score[i] / self.total[i], 6), self.total[i]))
        return self.names[i], round(score[i] / self.total[i], 6)


# Catalogue groups that hold descriptors ("Salary Credit", "ATM WDL", "Credit Card Payment"), not merchants
DESCRIPTOR_HINTS = ("income.", "transfers.", "cash.", "finance.bank_charges", "investments.deposits")


def index_names(merchants: list[dict]) -> list[str]:
    generic = generic_words()
    merchants = [m for m in merchants if not m["hint"].startswith(DESCRIPTOR_HINTS)]
    generic |= {w + "s" for w in generic} | {w[:-1] for w in generic if w.endswith("s")}
    return sorted(m["name"] for m in merchants
                  if m["kind"] == "brand" and words(m["name"]) and not set(words(m["name"])) <= generic
                  and sum(c.isalpha() for c in m["name"]) >= 3)


def evaluate(index: Index, rows: list[dict], threshold: float) -> dict:
    """rows: narrations; a brand narration should resolve to its merchant, a local shop's to nothing."""
    in_index = set(index.names)
    brand = [r for r in rows if r["merchant"] in in_index]
    local = [r for r in rows if r["kind"] == "local"]
    res = {id(r): index.resolve(r["text"]) for r in brand + local}
    resolved = [(r, res[id(r)][0]) for r in brand if res[id(r)][1] >= threshold]
    correct = sum(1 for r, name in resolved if name == r["merchant"])
    wrong_local = sum(1 for r in local if res[id(r)][1] >= threshold)
    return {"threshold": threshold, "brand_rows": len(brand),
            "coverage": round(len(resolved) / len(brand), 4) if brand else None,
            "precision": round(correct / len(resolved), 4) if resolved else None,
            "local_rows": len(local), "local_false_resolution_rate": round(wrong_local / len(local), 4) if local else None}


def tune(index: Index, val_rows: list[dict]) -> float:
    for t in [x / 100 for x in range(50, 100)]:
        e = evaluate(index, val_rows, t)
        if e["precision"] and e["precision"] >= MIN_PRECISION and (e["local_false_resolution_rate"] or 0) <= 0.02:
            return t
    return 1.0
