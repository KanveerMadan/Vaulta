"""
Synthetic bank narrations for every catalogue merchant and generated local shop, in the formats Indian banks print
(UPI from each bank, POS, payment gateways, credit-card descriptors, IMPS/NEFT, NACH, BBPS, ATM, salary credits),
with truncation, city codes and legal names, then passed through the real PII stripper (app/services/pii.py), which
is exactly what the server stores and the model sees.

Splits are by canonical merchant, so no merchant is in two splits:
  brands: train 70% / val 15% / test 15% by a hash of the name;
  local shops: every shop built on a held-out name stem is in test_local (shop words are shared, names never are);
  the rest go to train / val like brands.
Writes data/merchant_list.jsonl (one row per merchant) and data/narrations.jsonl. Deterministic (common.SEED).
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter

from common import ARTIFACTS, DATA, PRIVATE, SEED, local_shop_words, merchants, name_stems, read_jsonl, stable_hash, strip, write_jsonl

BANKS = ["HDFC", "ICIC", "SBIN", "UTIB", "KKBK", "YESB", "PUNB", "BARB", "IDIB", "CNRB", "INDB", "FDRL"]
BANK_NAMES = ["HDFC BANK", "ICICI BANK", "STATE BANK OF INDIA", "AXIS BANK", "KOTAK MAHINDRA", "YES BANK", "PNB", "BANK OF BARODA"]
HANDLES = ["ybl", "okaxis", "oksbi", "okicici", "okhdfcbank", "paytm", "axl", "ibl", "icici", "hdfcbank", "axisbank", "upi", "apl"]
CITIES = ["BANGALORE", "BENGALURU", "BLR", "MUMBAI", "MUM", "NEW DELHI", "DELHI", "GURGAON", "GURUGRAM", "NOIDA", "HYDERABAD",
          "HYD", "CHENNAI", "PUNE", "KOLKATA", "AHMEDABAD", "JAIPUR", "LUCKNOW", "KOCHI", "CHANDIGARH", "INDORE", "THANE",
          "NAVI MUMBAI", "COIMBATORE", "MYSORE", "NAGPUR", "SURAT", "VADODARA", "BHOPAL", "PATNA", "GOA", "VIZAG"]
GATEWAYS = ["RAZORPAY", "RZP", "PAYU", "PAYUMONEY", "CASHFREE", "CF", "CCAVENUE", "CCAV", "BILLDESK", "PAYTM", "JUSPAY",
            "EASEBUZZ", "PINELABS", "PHONEPE PG", "AMAZONPAY"]
REMARKS = ["Payment", "Pay", "UPI", "Paid via app", "Collect request", "Sent using Paytm", "NA", "Order", "Payment from PhonePe",
           "", "", "", "UPI Txn", "Pay to merchant", "Bill"]
LEGAL = ["PVT LTD", "PRIVATE LIMITED", "LTD", "LIMITED", "INDIA PVT LTD", "INDIA PRIVATE LIMITED", "SERVICES"]
LOCAL_SHOPS_PER_SUBCATEGORY = 26      # ≈ 1,500 shops across the subcategories in data/local_shops.txt
NARRATIONS = {"brand": 7, "local": 6}
HELD_OUT_STEM_SHARE = 0.25


def digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())[:20] or "merchant"


def shown_name(rng: random.Random, m: dict) -> str:
    """The merchant as a bank prints it: upper case, sometimes the legal name, truncated or squashed."""
    name = m["name"]
    if m["aliases"] and rng.random() < 0.3:
        name = rng.choice(m["aliases"])
        if rng.random() < 0.5 and not re.search(r"\b(ltd|limited|pvt)\b", name, re.I):
            name = f"{name} {rng.choice(LEGAL)}"
    name = re.sub(r"[’']", "", name).upper()
    r = rng.random()
    if r < 0.15:
        name = name[: rng.randint(8, 18)].rstrip()            # bank field width
    elif r < 0.22:
        name = name.replace(" ", "")                          # UPI apps squash spaces
    elif r < 0.27:
        name = name.replace("&", "AND")
    return name


def vpa(rng: random.Random, m: dict) -> str:
    s = slug(m["name"])
    return rng.choice([
        f"{s}@{rng.choice(HANDLES)}", f"{s}.rzp@axisbank", f"{s}@icici", f"{s}.payu@hdfcbank",
        f"paytmqr{digits(rng, 10)}@paytm", f"bharatpe.{digits(rng, 10)}@fbpe", f"q{digits(rng, 9)}@ybl",
        f"{s}{digits(rng, 3)}@{rng.choice(HANDLES)}", f"{digits(rng, 10)}@{rng.choice(HANDLES)}",
    ])


def ifsc(rng: random.Random) -> str:
    return f"{rng.choice(BANKS)}0{''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(6))}"


def debit_formats(rng, m, name):
    utr, city = digits(rng, 12), rng.choice(CITIES)
    v, remark = vpa(rng, m), rng.choice(REMARKS)
    return {
        "upi_icici": f"UPI/{utr}/{name}/{v}/{rng.choice(BANK_NAMES)}/{remark}",
        "upi_hdfc": f"UPI-{name}-{v}-{ifsc(rng)}-{utr}-{remark}",
        "upi_sbi": f"TO TRANSFER-UPI/DR/{utr}/{name[:12]}/{rng.choice(BANKS)}/{v[:12]}/{remark}",
        "upi_axis": f"UPI/P2M/{utr}/{name}/{remark}/{rng.choice(BANK_NAMES)}",
        "upi_kotak": f"UPI/{name}/{utr}/{remark}",
        "upi_app": rng.choice([m["name"], name.title(), name.replace(" ", "")]),
        "pos": rng.choice([f"POS XXXXXXXXXXXX{digits(rng, 4)} {name[:22]} {city}", f"POS/{name}/{city}/{digits(rng, 6)}",
                           f"PCD/{digits(rng, 4)}/{name}/{city}"]),
        "gateway": rng.choice([f"{rng.choice(GATEWAYS)}*{name}", f"{rng.choice(GATEWAYS)}/{name}/{city}",
                               f"PG {rng.choice(GATEWAYS)} {name} {digits(rng, 8)}"]),
        "card": f"{name[:23]} {city} IN" if rng.random() < 0.7 else f"{name[:23]} {city}",
        "imps": f"IMPS/P2M/{digits(rng, 12)}/{name}/{remark or 'Payment'}",
        "neft": f"NEFT-{ifsc(rng)}-{name}-{remark or 'NEFT'}-N{digits(rng, 9)}",
    }


def mandate_formats(rng, m, name):
    return {
        "nach": rng.choice([f"NACH-DR-{name}-{rng.choice(BANKS)}{digits(rng, 16)}", f"ACH D- {name}-{digits(rng, 10)}",
                            f"NACH/{name}/{digits(rng, 8)}", f"ECS/{name}/{digits(rng, 10)}"]),
        "si": f"SI {name} {digits(rng, 8)}",
        "bbps": rng.choice([f"BBPS/{name}/{digits(rng, 10)}", f"BIL/BPAY/{digits(rng, 9)}/{name}", f"BILLPAY {name} {digits(rng, 6)}"]),
    }


def credit_formats(rng, m, name):
    return {
        "neft_cr": f"NEFT CR-{ifsc(rng)}-{name}-{rng.choice(['SALARY', 'SAL', 'PAYMENT', 'NEFT', name[:10]])}-{digits(rng, 12)}",
        "by_transfer": f"BY TRANSFER-NEFT*{ifsc(rng)}*{digits(rng, 10)}*{name}",
        "imps_cr": f"IMPS/P2A/{digits(rng, 12)}/{name}/CREDIT",
        "upi_cr": f"UPI/CR/{digits(rng, 12)}/{name}/{rng.choice(BANKS)}/{vpa(rng, m)}",
        "plain_cr": f"{name} {rng.choice(['CREDIT', 'CR', 'PAYOUT', 'CREDITED'])} {digits(rng, 6)}",
    }


def atm_formats(rng, m, name):
    city = rng.choice(CITIES)
    return {
        "atm": rng.choice([f"ATM WDL {rng.choice(BANK_NAMES)} {city}", f"NWD-XXXXXXXXXXXX{digits(rng, 4)}-{rng.choice(BANKS)}{digits(rng, 4)}-{city}",
                           f"ATW-{digits(rng, 6)}XXXXXX{digits(rng, 4)}-S1AW{digits(rng, 4)}-{city}", f"{name} {city} {digits(rng, 6)}",
                           f"CASH WDL {name} {city}"]),
    }


def card_bill_formats(rng, m, name):
    return {
        "card_bill": rng.choice([f"{name} {digits(rng, 10)}", f"BILLDESK*{name}", f"AUTOPAY SI-TAD {name}", f"CRED CLUB {name}",
                                 f"UPI/{digits(rng, 12)}/{name}/cred.club@axisbank/Payment", f"IB BILLPAY DR-{name}-{digits(rng, 6)}"]),
    }


def narrations_for(rng: random.Random, m: dict, n: int) -> list[tuple[str, str]]:
    out = []
    for _ in range(n):
        name = shown_name(rng, m)
        hint = m["hint"]
        if hint.startswith("income."):
            fmts = credit_formats(rng, m, name)
        elif hint == "cash.atm":
            fmts = atm_formats(rng, m, name)
        elif hint == "transfers.credit_card_bill":
            fmts = {**card_bill_formats(rng, m, name), **{k: v for k, v in debit_formats(rng, m, name).items() if k.startswith("upi")}}
        else:
            fmts = debit_formats(rng, m, name)
            if hint.split(".")[0] in ("utilities", "insurance", "investments", "finance", "education", "housing", "taxes"):
                fmts.update(mandate_formats(rng, m, name))
        fmt = rng.choice(sorted(fmts))
        out.append((fmt, fmts[fmt]))
    return out


def local_shops(rng: random.Random, taken: set[str]) -> list[dict]:
    stems, words = name_stems(), local_shop_words()
    shops, seen = [], set(taken)
    for hint, shop_words in words.items():
        for _ in range(LOCAL_SHOPS_PER_SUBCATEGORY):
            stem, word = rng.choice(stems), rng.choice(shop_words)
            name = f"{stem} {word}"
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            shops.append({"name": name, "aliases": [], "hint": hint, "kind": "local", "stem": stem})
    return shops


def split_of(m: dict, held_out: set[str]) -> str:
    if m["kind"] == "local" and m["stem"] in held_out:
        return "test_local"
    h = stable_hash(m["name"].lower()) % 100
    if m["kind"] == "local":
        return "train" if h < 85 else "val"
    return "train" if h < 70 else "val" if h < 85 else "test"


def main() -> None:
    rng = random.Random(SEED)
    stems = name_stems()
    held_out = set(random.Random(SEED + 1).sample(stems, int(len(stems) * HELD_OUT_STEM_SHARE)))
    brands = merchants()
    everything = brands + local_shops(rng, {m["name"].lower() for m in brands})
    rows, merchant_rows = [], []
    for m in everything:
        m["split"] = split_of(m, held_out)
        merchant_rows.append({k: m.get(k) for k in ("name", "aliases", "hint", "kind", "split", "stem")})
        for i, (fmt, raw) in enumerate(narrations_for(rng, m, NARRATIONS[m["kind"]])):
            rows.append({"merchant": m["name"], "kind": m["kind"], "hint": m["hint"], "split": m["split"],
                         "format": fmt, "text": strip(raw), "source": "synthetic"})
    # identical stripped text in a held-out split and in train would be leakage: drop it from the held-out split
    train_texts = {r["text"].lower() for r in rows if r["split"] == "train"}
    rows = [r for r in rows if r["split"] == "train" or r["text"].lower() not in train_texts]
    write_jsonl(DATA / "merchant_list.jsonl", merchant_rows)
    write_jsonl(DATA / "narrations.jsonl", rows)
    real = read_jsonl(PRIVATE / "real.jsonl")
    summary = {split: {"synthetic": n, "real": 0} for split, n in sorted(Counter(r["split"] for r in rows).items())}
    summary["real_test"] = {"synthetic": 0, "real": len(real)}
    summary["merchants"] = dict(Counter(f"{m['split']}:{m['kind']}" for m in merchant_rows))
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "data_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"merchants: {Counter(m['kind'] for m in merchant_rows)}; by split: {Counter(m['split'] for m in merchant_rows)}")
    print(f"narrations: {len(rows)}; by split: {Counter(r['split'] for r in rows)}")


if __name__ == "__main__":
    main()
