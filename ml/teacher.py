"""
Teacher labels from LLMs on Groq: knowledge distillation, so every metric is "agreement with teacher labels".

Only stripped merchant strings are sent: each catalogue merchant and local shop as a bank prints its name, after the
PII stripper, plus (if present) the stripped real narrations from data/private/real.jsonl. Nothing else.

Self-consistency: two independent labels from two different models (A, B), in different orders and batches. When
they differ, a third model (C) labels the string. The label is the majority; with no majority, or when the majority
says "ambiguous", the string is ambiguous and excluded from training and evaluation.

Every answer is cached (data/teacher_cache.jsonl for synthetic strings, which is committed; data/private/ for real
ones), so re-runs make no calls for strings already labelled. The number of calls, retries and tokens is written to
artifacts/teacher_log.json. Stops at once if a call is needed and GROQ_API_KEY is missing (with everything cached,
it runs without a key); the key is never printed.

    python teacher.py
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import urllib.request
import urllib.error

from common import ARTIFACTS, DATA, LABELS, PRIVATE, ROOT, SEED, SUBCATEGORIES, read_jsonl, strip, write_jsonl

URL = "https://api.groq.com/openai/v1/chat/completions"
MODELS = {"A": "openai/gpt-oss-120b", "B": "qwen/qwen3.8-27b", "C": "openai/gpt-oss-20b"}
PROMPT_VERSION = "v1"
BATCH = 80
MAX_ATTEMPTS = 4
AMBIGUOUS = "ambiguous"

SYSTEM = """You label Indian bank transaction merchant strings with one subcategory id from this list.

{labels}

Rules:
- Label what the merchant mostly is. You only see the merchant name as a bank prints it, not the items bought.
- Quick commerce (Blinkit, Zepto, Swiggy Instamart, BB Now) is groceries.quick_commerce. Swiggy and Zomato alone are food.delivery.
- Amazon, Flipkart, Meesho with nothing more specific: shopping.marketplace. Amazon Prime: entertainment.video_streaming.
- Pharmacies and chemists ("medicals", "medical store", Apollo Pharmacy, 1mg, PharmEasy): health.pharmacy. Hospitals: health.hospital.
- Petrol pumps and fuel stations: transport.fuel. Credit card bill payments: transfers.credit_card_bill.
- Payment apps or wallets where the real merchant is hidden (Google Pay, PhonePe, Paytm, CRED): finance.payment_app.
- Rent platforms (NoBroker, CRED Rent, RentPay): housing.rent.
- Salary, interest, dividends, cashback and refunds from government are income.* subcategories.
- Generic local shop names are labelled by their shop word ("SRI BALAJI MEDICALS" is health.pharmacy).
- Answer "ambiguous" only when the string could reasonably be several very different subcategories.

Reply with JSON only: {{"labels": {{"1": "<id>", "2": "<id>", ...}}}} with one entry for every numbered string."""


def api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    env = ROOT / "backend" / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GROQ_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        sys.exit("GROQ_API_KEY is missing (environment or backend/.env): no labels without the teacher. Stopping.")
    return key


def cache_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}|{PROMPT_VERSION}|{text}".encode()).hexdigest()


class Teacher:
    def __init__(self, cache_path: Path):
        self.key, self.cache_path = None, cache_path
        self.cache = {r["key"]: r for r in read_jsonl(cache_path)}
        self.lock = threading.Lock()
        self.log = Counter()
        self.system = SYSTEM.format(labels="\n".join(LABELS + [AMBIGUOUS]))

    def _save(self, rows: list[dict]) -> None:
        with self.lock:
            for r in rows:
                self.cache[r["key"]] = r
            write_jsonl(self.cache_path, sorted(self.cache.values(), key=lambda r: r["key"]))

    def _call(self, model: str, texts: list[str]) -> dict[int, str]:
        self.key = self.key or api_key()
        user = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))
        body = {"model": model, "temperature": 0.3, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": self.system}, {"role": "user", "content": user}]}
        if model.startswith("openai/"):
            body["reasoning_effort"] = "low"
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                                              "User-Agent": "vaulta-ml-teacher"})
        with self.lock:
            self.log[f"calls:{model}"] += 1
        with urllib.request.urlopen(req, timeout=120) as res:
            data = json.loads(res.read())
            remaining = res.headers.get("x-ratelimit-remaining-tokens")
        with self.lock:
            self.log[f"tokens:{model}"] += data.get("usage", {}).get("total_tokens", 0)
        if remaining is not None and int(remaining) < 4000:
            time.sleep(20)                                  # let the per-minute token budget refill
        labels = json.loads(data["choices"][0]["message"]["content"])["labels"]
        return {int(k): v for k, v in labels.items()}

    def label(self, slot: str, texts: list[str]) -> dict[str, str]:
        """{text: label} from model `slot` for every text, using the cache first."""
        model = MODELS[slot]
        todo = [t for t in texts if cache_key(model, t) not in self.cache]
        rng = random.Random(f"{SEED}-{slot}")
        rng.shuffle(todo)
        for start in range(0, len(todo), BATCH):
            batch = todo[start:start + BATCH]
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    got = self._call(model, batch)
                except urllib.error.HTTPError as e:
                    with self.lock:
                        self.log[f"http_{e.code}:{model}"] += 1
                    if e.code == 429:
                        wait = float(e.headers.get("retry-after") or 30)
                        if wait > 3600:                     # the daily token budget refills slowly; wait up to an hour
                            sys.exit(f"{model}: rate limit for the day reached; re-run later (cached labels are kept).")
                        time.sleep(wait + 1)
                        continue
                    time.sleep(5 * attempt)
                    continue
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError, TypeError):
                    with self.lock:
                        self.log[f"bad_response:{model}"] += 1
                    time.sleep(3 * attempt)
                    continue
                rows = [{"key": cache_key(model, t), "model": model, "text": t, "label": got[i]}
                        for i, t in enumerate(batch, 1) if got.get(i) in SUBCATEGORIES or got.get(i) == AMBIGUOUS]
                self._save(rows)
                missing = [t for t in batch if cache_key(model, t) not in self.cache]
                if not missing:
                    break
                with self.lock:
                    self.log[f"retries:{model}"] += 1
                batch = missing                       # ask again only for what was missing or invalid
            print(f"  {slot} {model}: {min(start + BATCH, len(todo))}/{len(todo)}", flush=True)
        return {t: self.cache[cache_key(model, t)]["label"] for t in texts if cache_key(model, t) in self.cache}


def vote(labels: list[str]) -> str:
    top, n = Counter(labels).most_common(1)[0]
    return top if n >= 2 else AMBIGUOUS


def run(teacher: Teacher, texts: list[str]) -> list[dict]:
    with ThreadPoolExecutor(2) as pool:                  # A and B have separate rate limits
        a, b = pool.map(lambda slot: teacher.label(slot, texts), ["A", "B"])
    disagree = [t for t in texts if t in a and t in b and a[t] != b[t]]
    c = teacher.label("C", disagree)
    out = []
    for t in texts:
        votes = [x[t] for x in (a, b, c) if t in x]
        if len(votes) < 2 or (len(set(votes)) == 2 and len(votes) == 2):
            continue                                       # not fully labelled yet (re-run to finish)
        out.append({"text": t, "votes": votes, "label": vote(votes)})
    teacher.log["disagreements"] += len(disagree)
    return out


def _save_log(teacher: "Teacher", extra: dict) -> None:
    """Add this run's calls to artifacts/teacher_log.json (also when a run stops early)."""
    path = ARTIFACTS / "teacher_log.json"
    log = json.loads(path.read_text()) if path.exists() else {}
    calls = sum(v for k, v in teacher.log.items() if k.startswith("calls:"))
    log["llm_calls_total"] = log.get("llm_calls_total", 0) + calls
    if teacher.log:
        log.setdefault("runs", []).append({"calls": calls, **teacher.log})
    log.update(extra)
    path.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n")


def main() -> None:
    merchants = read_jsonl(DATA / "merchant_list.jsonl")
    if not merchants:
        sys.exit("Run generate.py first.")
    for m in merchants:
        m["teacher_text"] = strip(m["name"].upper())
    synthetic = Teacher(DATA / "teacher_cache.jsonl")
    try:
        labels = run(synthetic, sorted({m["teacher_text"] for m in merchants}))
    finally:
        _save_log(synthetic, {"models": MODELS, "prompt_version": PROMPT_VERSION})
    by_text = {r["text"]: r for r in labels}
    write_jsonl(DATA / "labels.jsonl", [{"merchant": m["name"], "split": m["split"], "kind": m["kind"], "hint": m["hint"],
                                         **by_text[m["teacher_text"]]} for m in merchants if m["teacher_text"] in by_text])
    real = read_jsonl(PRIVATE / "real.jsonl")
    if real:
        private = Teacher(PRIVATE / "teacher_cache.jsonl")
        try:
            write_jsonl(PRIVATE / "real_labels.jsonl", run(private, sorted({r["text"] for r in real})))
        finally:
            _save_log(private, {"real_strings": len(real)})
    summary = {"strings": len(by_text), "ambiguous": sum(1 for r in labels if r["label"] == AMBIGUOUS),
               "labelled_merchants": sum(1 for m in merchants if m["teacher_text"] in by_text), "merchants": len(merchants)}
    _save_log(Teacher(DATA / "teacher_cache.jsonl"), summary)      # records the counts (no calls)
    print(json.dumps(summary))

if __name__ == "__main__":
    main()
