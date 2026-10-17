"""
Trains Model A and Model B, tunes thresholds on validation, evaluates both against the current rule-based system
on every test set, applies the ship criteria, and writes:

  artifacts/merchant_model.json   Model A as shipped (if it ships), with its threshold
  artifacts/merchant_index.json   merchant-resolution index (brand names) and threshold
  artifacts/metrics.json          every number in docs/ml/evaluation.md
  artifacts/worst_errors.json     the 50 most confident disagreements on the main test set
  docs/ml/*.png                   coverage–agreement curves, reliability diagram, per-category F1

Ship criteria (Phase 9 step 6), all on teacher labels:
  1. macro-F1 above the rules on the main test set AND on the unseen-local-shops set, and
  2. a lower review rate than the rules at equal-or-better covered agreement. The threshold is picked on validation:
     the rows the model files must agree with the teacher at least AGREEMENT_FLOOR, and the whole order must keep
     covered agreement at least the rules'.
The shipped order is: a known merchant (the normalizer's patterns on the merchant's own words, without payment
rails, banks, handles, remarks or cities), then the model above its threshold, then review. The baseline is the
rules exactly as the app runs them today (patterns anywhere in the narration).
Prefer Model A unless Model B's macro-F1 is ≥ 3 points higher on the main test set.

    python train.py [--skip-b]
"""

from __future__ import annotations

import argparse
import json
import random

import numpy as np

import dataset
import metrics as M
import model_a
import resolver
from common import ARTIFACTS, DATA, LABELS, ROOT, SEED, SUBCATEGORIES, read_jsonl

DOCS = ROOT / "docs" / "ml"
THRESHOLDS = np.round(np.arange(0.0, 1.0001, 0.02), 2)
AGREEMENT_FLOOR = 0.90


def evaluate_split(rows, preds, threshold) -> dict:
    texts, y = [r["text"] for r in rows], [r["label"] for r in rows]
    rules = [M.rules_predict(t)[0] for t in texts]
    model_alone = M.system(texts, preds, threshold, use_rules=False)
    shipped = M.system(texts, preds, threshold, use_rules=True)
    known_only = [M.known_merchant(t)[0] for t in texts]     # the stricter known-merchant step with no model
    out = {"rows": len(rows), "rules": M.score(y, rules), "model": M.score(y, model_alone),
           "known_merchant_only": M.score(y, known_only), "rules_then_model": M.score(y, shipped)}
    if rows:
        conf = [c for _, c in preds]
        out["model"]["ece"] = M.ece(conf, [p == t for (p, _), t in zip(preds, y)])
        out["model"]["top1_agreement_no_threshold"] = round(float(np.mean([p == t for (p, _), t in zip(preds, y)])), 4)
        rr, rm = out["rules"]["review_rate"], out["rules_then_model"]["review_rate"]
        out["review_reduction"] = round((rr - rm) / rr, 4) if rr else None
        out["curve_model"] = M.curve(y, preds, texts, THRESHOLDS, use_rules=False)
        out["curve_rules_then_model"] = M.curve(y, preds, texts, THRESHOLDS, use_rules=True)
    return out


FIRST = ("Rahul Priya Amit Sneha Arjun Kavya Rohan Ananya Vikram Pooja Karthik Divya Suresh Meera Aditya Neha Sanjay "
         "Lakshmi Imran Fatima Joseph Mary Harpreet Simran Rajesh Sunita Abhishek Swati Manish Deepa").split()
SURNAMES = ("Sharma Verma Gupta Iyer Nair Reddy Patel Shah Khan Singh Das Ghosh Rao Menon Pillai Joshi Kulkarni Mehta "
            "Agarwal Fernandes").split()


def person_narrations() -> list[str]:
    """Bank narrations of payments to individuals (no merchant), as the browser masks them."""
    from common import strip
    rng = random.Random(SEED + 7)
    out = []
    for _ in range(500):
        f, l = rng.choice(FIRST), rng.choice(SURNAMES)
        h = rng.choice(["okaxis", "oksbi", "okhdfcbank", "ybl", "paytm", "ibl"])
        vpa = f"{f.lower()}{l.lower()[:3]}{rng.randint(1, 99)}@{h}"
        out.append(strip(rng.choice([f"UPI-{f.upper()} {l.upper()}-{vpa}-HDFC0001234-{rng.randint(10**11, 10**12 - 1)}-Payment",
                                     f"UPI/{rng.randint(10**11, 10**12 - 1)}/{f.upper()} {l.upper()}/{vpa}/ICICI BANK/Sent",
                                     f"IMPS/P2A/{rng.randint(10**11, 10**12 - 1)}/{f.upper()} {l.upper()[:5]}/Rent",
                                     f"TO TRANSFER-UPI/DR/{rng.randint(10**11, 10**12 - 1)}/{f.upper()}/SBIN/{vpa[:10]}/dinner"])))
    return out


def threshold_for(y, preds, texts, floor, rules_val) -> float:
    """On validation: the rows the model files must agree with the teacher ≥ AGREEMENT_FLOOR, and the whole shipped
    order must keep covered agreement ≥ the rules' (raised further if needed)."""
    t = M.model_only_threshold(y, preds, floor)
    while t < 1.0 and M.score(y, M.system(texts, preds, t))["covered_agreement"] < rules_val["covered_agreement"]:
        t = round(t + 0.01, 2)
    return t


def ships(ev: dict) -> dict:
    main, local = ev["test"], ev["test_local"]
    sys_, rules = main["rules_then_model"], main["rules"]
    checks = {
        "macro_f1_main": sys_["macro_f1"] > rules["macro_f1"],
        "macro_f1_local": local["rules_then_model"]["macro_f1"] > local["rules"]["macro_f1"],
        "lower_review_rate_main": sys_["review_rate"] < rules["review_rate"],
        "equal_or_better_covered_agreement_main": sys_["covered_agreement"] >= rules["covered_agreement"],
    }
    return {"checks": checks, "ships": all(checks.values())}


def plots(ev: dict, name: str, preds_test, rows_test) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    DOCS.mkdir(parents=True, exist_ok=True)
    files = []

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, split, title in ((axes[0], "test", "Main test set (unseen merchants)"), (axes[1], "test_local", "Unseen local shops")):
        e = ev[split]
        for key, label, style in (("curve_model", f"{name} alone", "-"), ("curve_rules_then_model", f"rules → {name}", "--")):
            pts = [p for p in e[key] if p["covered_agreement"] is not None]
            ax.plot([p["coverage"] for p in pts], [p["covered_agreement"] for p in pts], style, label=label)
        r = e["rules"]
        ax.scatter([1 - r["review_rate"]], [r["covered_agreement"] or 0], color="black", zorder=5, label="rules today")
        ax.set_xlabel("coverage (share categorised automatically)")
        ax.set_ylabel("agreement with teacher on covered rows")
        ax.set_title(title)
        ax.set_xlim(0, 1.02)
        ax.set_ylim(0.4, 1.01)
        ax.grid(alpha=0.3)
        ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    files.append("coverage-agreement.png")
    fig.savefig(DOCS / files[-1], dpi=130)
    plt.close(fig)

    conf = np.array([c for _, c in preds_test])
    correct = np.array([p == r["label"] for (p, _), r in zip(preds_test, rows_test)], dtype=float)
    edges = np.linspace(0, 1, 11)
    xs, ys, ns = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            xs.append(conf[m].mean()); ys.append(correct[m].mean()); ns.append(int(m.sum()))
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    ax.plot([0, 1], [0, 1], ":", color="grey")
    ax.plot(xs, ys, "o-")
    for x, y_, n in zip(xs, ys, ns):
        ax.annotate(str(n), (x, y_), fontsize=7, xytext=(3, -9), textcoords="offset points")
    ax.set_xlabel("confidence (after temperature)")
    ax.set_ylabel("agreement with teacher")
    ax.set_title(f"Reliability, main test set (ECE {ev['test']['model']['ece']})")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    files.append("reliability.png")
    fig.savefig(DOCS / files[-1], dpi=130)
    plt.close(fig)

    groups = {}
    for c, f in ev["test"]["rules_then_model"]["per_class_f1"].items():
        groups.setdefault(SUBCATEGORIES[c]["group"], []).append(f)
    rules_groups = {}
    for c, f in ev["test"]["rules"]["per_class_f1"].items():
        rules_groups.setdefault(SUBCATEGORIES[c]["group"], []).append(f)
    names = sorted(groups, key=lambda g: -np.mean(groups[g]))
    fig, ax = plt.subplots(figsize=(9, 5))
    yy = np.arange(len(names))
    ax.barh(yy - 0.2, [np.mean(groups[g]) for g in names], height=0.4, label=f"rules → {name}")
    ax.barh(yy + 0.2, [np.mean(rules_groups.get(g, [0])) for g in names], height=0.4, label="rules today")
    ax.set_yticks(yy, names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("mean per-subcategory F1 (main test set)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    files.append("f1-by-group.png")
    fig.savefig(DOCS / files[-1], dpi=130)
    plt.close(fig)
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-b", action="store_true", help="skip Model B (needs a ~430 MB download)")
    args = ap.parse_args()
    random.seed(SEED)
    np.random.seed(SEED)
    data = dataset.load()
    assert data["train"], "no labelled training data: run generate.py and teacher.py"

    # rules' covered agreement on validation is the bar the model's threshold must meet
    val = data["val"]
    rules_val = M.score([r["label"] for r in val], [M.rules_predict(r["text"])[0] for r in val])
    # the model files a row only where, on validation, ≥ AGREEMENT_FLOOR of what it files agrees with the teacher
    target = AGREEMENT_FLOOR

    results = {"data": {s: {"rows": len(v), "labels": len(M.label_counts(v)),
                            "synthetic": sum(r["source"] == "synthetic" for r in v),
                            "real": sum(r["source"] == "real" for r in v)} for s, v in data.items()},
               "teacher": json.loads((ARTIFACTS / "teacher_log.json").read_text()) if (ARTIFACTS / "teacher_log.json").exists() else None,
               "rules_val": {k: rules_val[k] for k in ("agreement", "macro_f1", "covered_agreement", "review_rate")},
               "threshold_target": target,
               "label_space": len(LABELS)}

    # ── Model A
    exported, report_a = model_a.train(data["train"], val)
    a = model_a.Exported(exported)
    preds = {s: [a.predict(r["text"]) for r in rows] for s, rows in data.items() if s != "train"}
    thr_a = threshold_for([r["label"] for r in val], preds["val"], [r["text"] for r in val], target, rules_val)
    exported["threshold"] = thr_a
    ev_a = {s: evaluate_split(rows, preds[s], thr_a) for s, rows in data.items() if s != "train"}
    results["model_a"] = {"training": report_a, "threshold": thr_a, "eval": ev_a, "ship": ships(ev_a),
                          "size_bytes": len(json.dumps(exported, separators=(",", ":")))}

    # ── Model B
    if not args.skip_b:
        import model_b
        b, report_b = model_b.train(data["train"], val)
        preds_b = {s: b.predict_many([r["text"] for r in rows]) for s, rows in data.items() if rows and s != "train"}
        thr_b = threshold_for([r["label"] for r in val], preds_b["val"], [r["text"] for r in val], target, rules_val)
        ev_b = {s: evaluate_split(rows, preds_b.get(s, []), thr_b) for s, rows in data.items() if s != "train"}
        results["model_b"] = {"training": report_b, "threshold": thr_b, "eval": ev_b, "ship": ships(ev_b)}

    # ── choice: A unless B is ≥ 3 macro-F1 points better on the main test set (and B itself meets the criteria)
    choice = "model_a"
    if "model_b" in results:
        fa = results["model_a"]["eval"]["test"]["rules_then_model"]["macro_f1"]
        fb = results["model_b"]["eval"]["test"]["rules_then_model"]["macro_f1"]
        if fb - fa >= 0.03 and results["model_b"]["ship"]["ships"]:
            choice = "model_b"
    results["choice"] = choice
    people = person_narrations()
    shipped_people = M.system(people, [a.predict(t) for t in people], thr_a, use_rules=True)
    results["person_narrations"] = {"rows": len(people),
                                    "auto_categorised_rate": round(sum(1 for p in shipped_people if p) / len(people), 4)}
    results["data_counts"] = json.loads((ARTIFACTS / "data_summary.json").read_text())
    results["ships"] = results[choice]["ship"]["ships"]

    # ── merchant resolution
    merchants = read_jsonl(DATA / "merchant_list.jsonl")
    names = resolver.index_names(merchants)
    index = resolver.Index(names)
    thr_r = resolver.tune(index, val)
    results["resolution"] = {"index_names": len(names), "threshold": thr_r,
                             "val": resolver.evaluate(index, val, thr_r),
                             "test": resolver.evaluate(index, data["test"] + data["test_local"], thr_r)}

    # ── worst confident errors (main test set), plots, artefacts
    chosen_preds = preds["test"]
    errors = sorted(((c, r["text"], r["label"], p) for (p, c), r in zip(chosen_preds, data["test"]) if p != r["label"]),
                    reverse=True)[:50]
    (ARTIFACTS / "worst_errors.json").write_text(json.dumps(
        [{"confidence": round(c, 4), "text": t, "teacher": l, "model": p} for c, t, l, p in errors], indent=1) + "\n")
    results["plots"] = plots(ev_a, "Model A", chosen_preds, data["test"])
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "merchant_model.json").write_text(json.dumps(exported, separators=(",", ":"), sort_keys=True))
    (ARTIFACTS / "merchant_index.json").write_text(json.dumps({"names": names, "threshold": thr_r, "n": list(resolver.N)},
                                                              separators=(",", ":")))
    (ARTIFACTS / "metrics.json").write_text(json.dumps(results, indent=1, sort_keys=True) + "\n")

    def line(name, e):
        r, s = e["rules"], e["rules_then_model"]
        return (f"{name:<11} rows {e['rows']:>5}  macro-F1 rules {r['macro_f1']} → {s['macro_f1']}  "
                f"review {r['review_rate']} → {s['review_rate']}  covered agreement {r['covered_agreement']} → {s['covered_agreement']}")
    for m in ("model_a", "model_b"):
        if m in results:
            print(m, "threshold", results[m]["threshold"], results[m]["ship"])
            for s in ("test", "test_local"):
                print("  " + line(s, results[m]["eval"][s]))
    print("choice:", choice, "ships:", results["ships"], "| resolution", results["resolution"]["test"])


if __name__ == "__main__":
    main()
