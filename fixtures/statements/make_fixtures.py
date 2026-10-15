"""
Builds the synthetic statement fixtures shared by the backend and frontend
parity tests, and writes expected.json from the Python reference parsers.

    cd backend && venv/bin/python ../fixtures/statements/make_fixtures.py

The PDFs are generated, not real bank exports: the layouts follow each
statement's published format as closely as known, but they are not a
substitute for testing against real files (see README in this folder).
Needs a TTF with the ₹ glyph (FIXTURE_FONT, default: macOS Georgia).
"""

import json
import os
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "backend"))

from app.services.csv_parser import parse_csv  # noqa: E402
from app.services.upi_statement_parser import parse_upi_statement  # noqa: E402

FONT = os.environ.get("FIXTURE_FONT", "/System/Library/Fonts/Supplemental/Georgia.ttf")
GPAY_PASSWORD = "RAHU0503"


def new_page(doc):
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="F0", fontfile=FONT)
    return page


def text(page, x, y, s, size=9):
    page.insert_text((x, y), s, fontname="F0", fontsize=size)


def save(doc, name, **kw):
    doc.subset_fonts()
    doc.save(HERE / name, garbage=4, deflate=True, **kw)


# ── Google Pay: three columns per transaction (date/time | details | amount) ──
GPAY_ROWS = [
    ("04 May, 2026", "05:23 AM", "Paid to ZEPTO MARKETPLACE PRIVATE LIMITED", "612456562367", "Paid by IndusInd Bank 8250", "₹129"),
    ("05 May, 2026", "09:10 PM", "Received from Rahul Sharma", "612456562368", "Paid to IndusInd Bank 8250", "₹1,500"),
    ("06 May, 2026", "11:45 AM", "Self transfer to HDFC Bank 4321", "612456562369", "Paid by IndusInd Bank 8250", "₹10,000"),
    ("07 May, 2026", "01:05 PM", "Paid to 9876543210@ybl", "612456562370", "Paid by IndusInd Bank 8250", "₹45.50"),
]


def make_gpay():
    doc = pymupdf.open()
    page = new_page(doc)
    text(page, 40, 50, "Transaction statement", 14)
    text(page, 40, 68, "Rahul Sharma · rahul.s@gmail.com · 9876501234")
    text(page, 40, 84, "Google Pay")
    text(page, 40, 110, "Date & time")
    text(page, 160, 110, "Transaction details")
    text(page, 480, 110, "Amount")
    y = 135
    for date, time, detail, utr, bank, amount in GPAY_ROWS:
        text(page, 40, y, date)
        text(page, 40, y + 12, time)
        text(page, 160, y, detail)
        text(page, 160, y + 12, f"UPI Transaction ID: {utr}")
        text(page, 160, y + 24, bank)
        text(page, 480, y, amount)
        y += 48
    save(doc, "gpay.pdf")
    save(doc, "gpay_locked.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256,
         user_pw=GPAY_PASSWORD, owner_pw="owner-" + GPAY_PASSWORD)


# ── PhonePe ───────────────────────────────────────────────────────────────────
def make_phonepe():
    doc = pymupdf.open()
    page = new_page(doc)
    text(page, 40, 50, "Transaction Statement for 9876501234", 13)
    text(page, 40, 66, "Jun 01, 2024 - Jun 30, 2024")
    for x, h in ((40, "Date"), (130, "Transaction Details"), (420, "Type"), (480, "Amount")):
        text(page, x, 95, h)
    rows = [
        ("Jun 03, 2024", "08:15 am", "Paid to Swiggy", "T2406030815123456789", "415512345678", "DEBIT", "₹348"),
        ("Jun 05, 2024", "07:47 pm", "Received from Neha Gupta", "T2406051947123456789", "415712345678", "CREDIT", "₹2,000"),
        ("Jun 09, 2024", "10:02 am", "Paid to Raju Kirana Store", "T2406091002123456789", "416112345678", "DEBIT", "₹86.40"),
    ]
    y = 120
    for date, time, detail, txn, utr, typ, amount in rows:
        text(page, 40, y, date)
        text(page, 40, y + 12, time)
        text(page, 130, y, detail)
        text(page, 130, y + 12, f"Transaction ID {txn}")
        text(page, 130, y + 24, f"UTR No. {utr}")
        text(page, 130, y + 36, "Paid by XXXXXX1234")
        text(page, 420, y, typ)
        text(page, 480, y, amount)
        y += 56
    save(doc, "phonepe.pdf")


# ── Paytm: dates without a year; year comes from the statement period ─────────
def make_paytm():
    doc = pymupdf.open()
    page = new_page(doc)
    text(page, 40, 50, "Paytm Statement for 9876501234", 13)
    text(page, 40, 66, "01 DEC'23 - 31 JAN'24")
    for x, h in ((40, "Date & Time"), (130, "Transaction Details"), (360, "Your Account"), (480, "Amount")):
        text(page, x, 95, h)
    rows = [
        ("28 Dec", "9:30 PM", "Paid to Zomato", "zomato@paytm", "335912345678", "- Rs.512"),
        ("02 Jan", "6:05 AM", "Received from Amit Kumar", "amitk@oksbi", "400212345678", "+ Rs.1,250.50"),
        ("29 Jan", "1:00 PM", "Money sent to Kavya", "kavya.r@okhdfcbank", "402912345678", "- Rs.300"),
    ]
    y = 120
    for date, time, detail, vpa, ref, amount in rows:
        text(page, 40, y, date)
        text(page, 40, y + 12, time)
        text(page, 130, y, detail)
        text(page, 130, y + 12, f"UPI ID: {vpa}")
        text(page, 130, y + 24, f"UPI Ref No: {ref}")
        text(page, 360, y, "State Bank of India - 12")
        text(page, 480, y, amount)
        y += 48
    save(doc, "paytm.pdf")


# ── Bank account statement table (HDFC-style PDF headers, which differ from CSV) ─
def make_bank_pdf():
    doc = pymupdf.open()
    cols = [(30, "Date"), (85, "Narration"), (300, "Chq./Ref.No."), (380, "Withdrawal Amt."), (450, "Deposit Amt."), (520, "Closing Balance")]
    rows = [
        ("01/08/24", ["UPI-BLINKIT-blinkit.payu@hdfcbank-", "HDFC0000499-421411112222-Order"], "0000421411112222", "623.00", "", "48,377.00"),
        ("02/08/24", ["NEFT CR-ACME CORP PAYROLL"], "N214567890", "", "85,000.00", "1,33,377.00"),
        ("03/08/24", ["UPI-SUNITA DEVI-9812345678@ybl-", "YESB0YBLUPI-421633334444-Milk"], "0000421633334444", "1,050.00", "", "1,32,327.00"),
    ]
    page = new_page(doc)
    text(page, 30, 40, "HDFC BANK Ltd.  Statement of account", 12)
    text(page, 30, 56, "MR RAHUL SHARMA   Account No : 50100123456789   IFSC : HDFC0001234")
    text(page, 30, 72, "Address: 12 MG Road, Bengaluru 560001")
    for x, h in cols:
        text(page, x, 100, h, 8)
    y = 118
    for date, narr, ref, wd, dep, bal in rows:
        text(page, 30, y, date, 8)
        for k, part in enumerate(narr):
            text(page, 85, y + 10 * k, part, 8)
        text(page, 300, y, ref, 8)
        if wd:
            text(page, 380, y, wd, 8)
        if dep:
            text(page, 450, y, dep, 8)
        text(page, 520, y, bal, 8)
        y += 10 * len(narr) + 8
    text(page, 30, y + 20, "STATEMENT SUMMARY  Opening Balance 49,000.00  Closing Balance 1,32,327.00", 8)
    text(page, 30, y + 34, "Page 1 of 1", 8)
    save(doc, "bank_hdfc.pdf")


# ── Credit card statements ────────────────────────────────────────────────────
CARDS = {
    "card_hdfc.pdf": ("HDFC Bank Credit Cards", [
        "12/03/2024 14:22:05 SWIGGY BANGALORE 450.00",
        "15/03/2024 10:01:44 AMAZON PAY INDIA 2,199.00",
        "18/03/2024 09:00:00 PAYMENT RECEIVED - THANK YOU 15,000.00 Cr",
        "20/03/2024 18:30:12 REFUND MYNTRA DESIGNS 799.00 Cr",
    ]),
    "card_icici.pdf": ("ICICI Bank Credit Card", [
        "02/04/2024 10203040506 UBER INDIA SYSTEMS 12 342.50",
        "05/04/2024 10203040507 BBPS PAYMENT RECEIVED 8,000.00 CR",
        "07/04/2024 10203040508 BOOKMYSHOW MUMBAI 25 1,040.00",
    ]),
    "card_sbi.pdf": ("SBI Card", [
        "05 Mar 24 ZOMATO GURGAON 389.00 D",
        "09 Mar 24 PAYMENT RECEIVED 000123456 5,000.00 C",
        "11 Mar 24 IRCTC E-TICKETING 1,675.40 D",
    ]),
    "card_axis.pdf": ("Axis Bank Credit Card", [
        "01/05/2024 BIGBASKET BANGALORE GROCERY 1,234.00 Dr",
        "04/05/2024 AUTOPAY PAYMENT RECEIVED 9,876.00 Cr",
        "06/05/2024 SPOTIFY INDIA ENTERTAINMENT 119.00 Dr",
    ]),
}


def make_cards():
    for name, (issuer, lines) in CARDS.items():
        doc = pymupdf.open()
        page = new_page(doc)
        text(page, 40, 50, f"{issuer} Statement", 13)
        text(page, 40, 66, "Card No: 4321 XXXX XXXX 9876   RAHUL SHARMA")
        text(page, 40, 82, "Payment Due Date: 05/06/2024   Total Amount Due: 12,345.00   Minimum Amount Due: 620.00")
        text(page, 40, 110, "Date  Transaction Details  Amount")
        y = 130
        for line in lines:
            # date / description / amount in separate runs so they become cells
            parts = line.split(" ")
            amount_at = next(i for i in range(len(parts) - 1, -1, -1) if parts[i].replace(",", "").replace(".", "").isdigit())
            date_len = 3 if name == "card_sbi.pdf" else 1
            if name == "card_hdfc.pdf":
                date_len = 2
            text(page, 40, y, " ".join(parts[:date_len]))
            text(page, 150, y, " ".join(parts[date_len:amount_at]))
            text(page, 450, y, " ".join(parts[amount_at:]))
            y += 16
        save(doc, name)


def golden():
    out = {}
    for bank in ("hdfc", "icici", "sbi", "axis", "kotak"):
        _, txns = parse_csv((HERE / f"{bank}.csv").read_bytes(), filename=f"{bank}.csv")
        out[f"{bank}.csv"] = [
            {"date": t.transaction_date.strftime("%Y-%m-%d"), "description_raw": t.merchant_raw,
             "amount": f"{t.amount:.2f}", "direction": "debit"}
            for t in txns
        ]
    _, upi = parse_upi_statement((HERE / "gpay.pdf").read_bytes())
    out["gpay.pdf"] = [
        {"date": t.transaction_date.strftime("%Y-%m-%dT%H:%M:%S"), "description_raw": t.merchant_raw,
         "amount": f"{t.amount:.2f}", "direction": "credit" if t.direction == "received" else "debit",
         "reference": t.utr, "type": "transfer" if t.direction == "self_transfer" else "transaction"}
        for t in upi
    ]
    (HERE / "expected.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    font = pymupdf.Font(fontfile=FONT)
    assert font.has_glyph(0x20B9), f"{FONT} has no ₹ glyph; set FIXTURE_FONT"
    make_gpay()
    make_phonepe()
    make_paytm()
    make_bank_pdf()
    make_cards()
    result = golden()
    print({k: len(v) for k, v in result.items()})
