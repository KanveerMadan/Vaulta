"""
Optional real narrations for the real-narrations test set. Reads bank CSVs (and UPI-app PDFs, when pdfplumber is
installed) from local-statements/ with the Python reference parsers (backend/tests/reference), keeps only each row's
narration after the PII stripper (no amounts, dates or references), de-duplicates, and writes
data/private/real.jsonl. data/private/ and local-statements/ are git-ignored; nothing here is ever printed.

    python prepare_real.py [--input DIR] [--out FILE]
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
from pathlib import Path

from common import PRIVATE, ROOT, strip, write_jsonl

sys.path.insert(0, str(ROOT / "backend"))


def narrations(folder: Path) -> tuple[list[str], dict]:
    from tests.reference.csv_parser import parse_csv
    texts, counts = [], {"csv": 0, "pdf": 0, "skipped": 0}
    for path in sorted(folder.iterdir()):
        try:
            if path.suffix.lower() == ".csv":
                _, rows = parse_csv(path.read_bytes(), path.name)
                texts += [r.merchant_raw for r in rows]
                counts["csv"] += 1
            elif path.suffix.lower() == ".pdf":
                from tests.reference.upi_statement_parser import parse_upi_statement
                _, rows = parse_upi_statement(path.read_bytes(), path.name)
                texts += [r.merchant_raw for r in rows]
                counts["pdf"] += 1
            else:
                counts["skipped"] += 1
        except Exception:                      # an unreadable or unsupported file: counted, never shown
            counts["skipped"] += 1
    return texts, counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=ROOT / "local-statements")
    ap.add_argument("--out", type=Path, default=PRIVATE / "real.jsonl")
    args = ap.parse_args()
    if not args.input.is_dir() or not any(args.input.iterdir()):
        print(f"No statements in {args.input}: the real-narrations test set stays empty.")
        write_jsonl(args.out, [])
        return
    # the reference parsers print and log skipped rows (with their dates): keep that out of the terminal
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
        logging.disable(logging.CRITICAL)
        texts, counts = narrations(args.input)
        logging.disable(logging.NOTSET)
    unique = sorted({strip(t) for t in texts if t and strip(t)})
    write_jsonl(args.out, [{"text": t, "source": "real", "split": "real_test"} for t in unique])
    print(f"Files read: {counts}; unique narrations: {len(unique)} → {args.out} (contents not shown)")


if __name__ == "__main__":
    main()
