"""
Merchant categoriser: the order a new transaction's automatic category is decided in.

  1. the user's own rules                      (services/rules.py, applied by detection, unchanged)
  2. the user's own corrections, by similarity  (personal memory: a past correction of a similar narration)
  3. a known merchant                           (services/merchant_normalizer.py patterns, on the merchant's own words)
  4. the merchant model, above its threshold    (ml/, docs/MODEL_CARD.md)
  5. otherwise nothing: the transaction goes to the review queue
Payments to people keep their nature category and never reach 2–4.

The model is character n-gram TF-IDF + logistic regression (app/data/merchant_model.json.gz, trained by `make train`
in ml/). frontend/src/lib/merchantModel.js runs the same file in the browser; tests/test_categorizer.py checks both
give the same answers. The merchant index (app/data/merchant_index.json) resolves a narration to a catalogue brand
for the display name. MERCHANT_MODEL_ENABLED=false (or a missing model file) leaves only steps 1, 3 and 5: the
rule-based behaviour from before the model.

Every automatic category carries an explanation (Transaction.category_explanation) shown in the app on tap.
"""

from __future__ import annotations

import gzip
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services import taxonomy
from app.services.merchant_normalizer import normalize as normalize_merchant

DATA = Path(__file__).resolve().parent.parent / "data"
MODEL_FILE = DATA / "merchant_model.json.gz"
INDEX_FILE = DATA / "merchant_index.json"
PERSONAL_SIMILARITY = 0.6        # n-gram Jaccard between a new narration and one the user corrected (tuned in tests)
ALTERNATIVES = 3


# ── Features (same as ml/features.py and merchantModel.js) ────────────────────

def normalize(text: str) -> str:
    text = re.sub(r"[0-9]", "0", (text or "").lower())
    text = re.sub(r"[^a-z0@&]+", " ", text)
    return " ".join(text.split())


def ngrams(text: str, low: int = 1, high: int = 5) -> list[str]:
    out = []
    for word in normalize(text).split(" "):
        if not word:
            continue
        w = f" {word} "
        for n in range(low, high + 1):
            if n > len(w):
                break
            out.extend(w[i:i + n] for i in range(len(w) - n + 1))
    return out


# ── Model ─────────────────────────────────────────────────────────────────────

@dataclass
class Prediction:
    subcategory: str
    confidence: float
    alternatives: list = field(default_factory=list)   # [(subcategory, probability)], best first


@lru_cache(maxsize=1)
def model() -> Optional[dict]:
    if not MODEL_FILE.exists():
        return None
    with gzip.open(MODEL_FILE, "rt") as f:
        return json.load(f)


def enabled() -> bool:
    return settings.MERCHANT_MODEL_ENABLED and model() is not None


def predict(text: str) -> Optional[Prediction]:
    """The model's best subcategory and calibrated probability, or None when it has no model or no known n-gram."""
    m = model()
    if m is None:
        return None
    idf, weights, scale = m["idf"], m["weights"], m["scale"]
    counts = Counter(g for g in ngrams(text, *m["ngram_range"]) if g in idf)
    if not counts:
        return None
    vals = {g: (1.0 + math.log(c)) * idf[g] for g, c in counts.items()}
    norm = math.sqrt(sum(v * v for v in vals.values())) or 1.0
    z = list(m["bias"])
    for g, v in vals.items():
        w = weights[g]
        x = v / norm * scale
        for k in range(0, len(w), 2):
            z[w[k]] += x * w[k + 1]
    t = m["temperature"]
    top = max(z)
    e = [math.exp((v - top) / t) for v in z]
    total = sum(e)
    probs = sorted(((p / total, i) for i, p in enumerate(e)), key=lambda x: (-x[0], x[1]))
    labels = m["labels"]
    return Prediction(labels[probs[0][1]], probs[0][0], [(labels[i], p) for p, i in probs[:ALTERNATIVES]])


def threshold() -> float:
    m = model()
    return m["threshold"] if m else 1.0


# ── Merchant resolution (same as ml/resolver.py and merchantModel.js) ─────────

RAIL_WORDS = set("""upi dr cr p0m p0a to transfer neft imps nach ecs ach bbps billpay bil bpay pos pcd pg payment payments pay
paid via app sent using collect request txn bill order na in from by xxxx xxxxxxxxxxxx credit debit payout credited
razorpay rzp payu payumoney cashfree cf ccavenue ccav billdesk paytm juspay easebuzz pinelabs phonepe amazonpay gpay
googlepay merchant ybl okaxis oksbi okicici okhdfcbank axl ibl icici hdfcbank axisbank apl fbpe hdfc icic sbin utib
kkbk yesb punb barb idib cnrb indb fdrl bank state of india axis kotak mahindra yes pnb baroda autopay si tad ib
bangalore bengaluru blr mumbai mum new delhi gurgaon gurugram noida hyderabad hyd chennai pune kolkata ahmedabad jaipur
lucknow kochi chandigarh indore thane navi coimbatore mysore nagpur surat vadodara bhopal patna goa vizag""".split())


def merchant_words(text: str) -> list[str]:
    """The words that can name a merchant: no rails, banks, cities, UPI handles ("@ybl"), single letters or masks."""
    return [w for w in normalize(text).split(" ")
            if len(w) > 1 and w not in RAIL_WORDS and not w.startswith("@") and not set(w) <= set("0x")]


def merchant_text(text: str) -> str:
    """The narration's own words, original spelling, without rails, banks, handles, remarks or cities: what the known-
    merchant step matches, so "PAYTMQR…@paytm" or "Payment from PhonePe" around a shop's name doesn't make it Paytm."""
    keep = [t for t in re.split(r"[^A-Za-z0-9&.']+", text or "") if merchant_words(t)]
    return " ".join(keep)


def gram_set(text: str, sizes=(3, 4, 5)) -> set[str]:
    out = set()
    for word in merchant_words(text):
        w = f" {word} "
        for n in sizes:
            out.update(w[i:i + n] for i in range(len(w) - n + 1))
    return out


class _Index:
    def __init__(self, names: list[str], sizes: tuple, threshold_: float):
        self.names, self.sizes, self.threshold = names, sizes, threshold_
        self.grams = [gram_set(n, sizes) for n in names]
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

    def resolve(self, text: str) -> tuple[Optional[str], float]:
        score = defaultdict(float)
        for x in gram_set(text, self.sizes):
            for i in self.postings.get(x, ()):
                score[i] += self.idf[x]
        if not score:
            return None, 0.0
        i = max(score, key=lambda i: (round(score[i] / self.total[i], 6), self.total[i]))
        return self.names[i], round(score[i] / self.total[i], 6)


@lru_cache(maxsize=1)
def _index() -> Optional[_Index]:
    if not INDEX_FILE.exists():
        return None
    data = json.loads(INDEX_FILE.read_text())
    return _Index(data["names"], tuple(data["n"]), data["threshold"])


def resolve_merchant(text: str) -> Optional[str]:
    """The catalogue brand this narration is from, when the match clears the tuned threshold."""
    idx = _index() if enabled() else None
    if idx is None:
        return None
    name, score = idx.resolve(text)
    return name if name and score >= idx.threshold else None


# ── Personal memory: the user's own corrections ──────────────────────────────

def similarity(a: str, b: str) -> float:
    ga, gb = gram_set(a), gram_set(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def personal_match(text: str, memory: list[tuple[str, str, Optional[str], str]]) -> Optional[tuple]:
    """(category, subcategory, label, similarity) of the most similar corrected narration, if similar enough.
    memory: [(narration, category, subcategory, merchant label)] from load_memory()."""
    best = None
    for narration, category, subcategory, merchant in memory:
        s = similarity(text, narration)
        if s >= PERSONAL_SIMILARITY and (best is None or s > best[3]):
            best = (category, subcategory, merchant, s)
    return best


def load_memory(db, user_id) -> list[tuple[str, str, Optional[str], str]]:
    """The user's latest category correction per transaction, with that transaction's (encrypted) narration."""
    from app.models.correction import Correction
    from app.models.transaction import Transaction
    latest: dict = {}
    for c in (db.query(Correction).filter(Correction.user_id == user_id, Correction.field.in_(("category", "subcategory")))
              .order_by(Correction.created_at)):
        latest.setdefault(c.transaction_id, {})[c.field] = c.new_value
    if not latest:
        return []
    out = []
    for t in db.query(Transaction).filter(Transaction.user_id == user_id, Transaction.id.in_(list(latest))):
        values = latest[t.id]
        if values.get("category"):
            out.append((t.merchant_raw, values["category"], values.get("subcategory"), t.merchant_clean or ""))
    return out


# ── The decision ──────────────────────────────────────────────────────────────

@dataclass
class Decision:
    category: Optional[str]
    subcategory: Optional[str]
    merchant_clean: Optional[str]
    explanation: Optional[dict]


def categorise(text: str, direction: str, normalized, memory: list, client: Optional[dict] = None) -> Decision:
    """
    Steps 2–5 above for one narration (step 1 runs later in detection). `normalized` is the normalizer's result,
    `client` the browser's own model prediction for statement rows ({"subcategory", "confidence"}), used instead of
    predicting again when it names a real subcategory.
    """
    if enabled():
        # the known-merchant step matches the merchant's own words only (the rule-based behaviour matched anywhere)
        normalized = normalize_merchant(merchant_text(text))
    confident = normalized.confidence >= 0.5
    merchant = normalized.merchant_clean if confident else None
    if enabled():
        hit = personal_match(text, memory)
        if hit:
            category, subcategory, label, s = hit
            return Decision(category, subcategory, merchant or resolve_merchant(text),
                            {"source": "personal", "similar_to": label or None, "similarity": round(s, 3)})
    if confident:
        return Decision(normalized.category, normalized.subcategory, merchant,
                        {"source": "known_merchant", "merchant": merchant})
    if not enabled():
        return Decision(None, None, None, None)
    resolved = resolve_merchant(text)
    if client and client.get("subcategory") in taxonomy.SUBCATEGORIES and isinstance(client.get("confidence"), (int, float)):
        p = Prediction(client["subcategory"], float(client["confidence"]), [])
        on_device = True
    else:
        p, on_device = predict(text), False
    if p is None:
        return Decision(None, None, resolved, None)
    group = taxonomy.group_of(p.subcategory)
    fits_direction = not (group in taxonomy.CREDIT_ONLY_GROUPS and direction == "debit")   # Income is for credits
    explanation = {"source": "model", "confidence": round(p.confidence, 3), "threshold": threshold(),
                   "alternatives": [[s, round(q, 3)] for s, q in p.alternatives], "on_device": on_device}
    if p.confidence >= threshold() and fits_direction:
        return Decision(group, p.subcategory, resolved, explanation)
    return Decision(None, None, resolved, {**explanation, "below_threshold": True})
