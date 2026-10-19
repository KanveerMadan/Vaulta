"""
Simulations (Phase 8): try Vaulta's pipelines on sample input before connecting anything real.

  bank_alert   a sample bank alert email (one of four banks' real formats, dated today) goes through the same
               sender check, parse and PII stripping as a forwarded alert (services/inbound.read_alert), then the
               import pipeline, as a sample row
  quick_add    a line like "150 auto cash" is parsed as Telegram and the quick-add bar parse it, and shows the bot's
               reply; saving it makes a sample cash entry
(The statement simulation runs entirely in the browser: frontend/public/samples/, nothing is sent.)

Sample rows are labelled, never counted and deleted within an hour (core/samples.py). In the demo, which is shared
and read-only, nothing is written: the same steps run and the would-be transaction is returned.
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy.orm import Session

from app.core import clock
from app.core.demo import is_demo
from app.core.samples import INCLUDE
from app.models.transaction import Transaction
from app.schemas.transaction import ManualTransactionCreate, TransactionResponse
from app.services import inbound, transaction_service
from app.services.categorizer import categorise, load_memory
from app.services.merchant_normalizer import normalize
from app.services.quick_add import parse_quick_add
from app.services.telegram_bot import _entry_text

# sender, auth domain, subject, body template (formats from tests/test_inbound.py); everything in them is made up
ALERTS = {
    "hdfc": ("HDFC Bank InstaAlerts <alerts@hdfcbank.net>", "hdfcbank.net", "You have done a UPI txn. Check details!",
             "Dear Customer, Rs.450.00 has been debited from account **1234 to VPA swiggy@icici SWIGGY on {d:%d-%m-%y}. "
             "Your UPI transaction reference number is {ref}. If you did not authorize this transaction, call us."),
    "icici": ("ICICI Bank <credit_cards@icicibank.com>", "icicibank.com", "Transaction alert",
              "INR 342.50 spent using ICICI Bank Credit Card XX9876 on {d:%d-%b-%y} on UBER INDIA SYSTEMS. "
              "Avl Limit: INR 1,20,000.00."),
    "sbi": ("SBI Card <onlinesbicard@sbicard.com>", "sbicard.com", "Transaction alert",
            "Rs.389.00 spent on your SBI Credit Card ending 5555 at ZOMATO on {d:%d/%m/%y}. Trxn. not done by you? "
            "Report at https://sbicard.com"),
    "axis": ("Axis Bank Alerts <alerts@axisbank.com>", "axisbank.com", "Transaction alert",
             "INR 1,845.25 debited from A/c no. XX7777 on {d:%d-%m-%Y} 14:22:05 IST at UPI/P2M/{ref}/BIGBASKET. "
             "Avl Bal INR 52,000.00"),
}


class SimulationError(ValueError):
    pass


def _local_today(user):
    return clock.now().astimezone(clock.zone(user.timezone)).date()


def _sample(db: Session, simulation_id: uuid.UUID) -> dict:
    t = (db.query(Transaction).execution_options(**{INCLUDE: True})
         .filter(Transaction.simulation_id == simulation_id).one())
    return TransactionResponse.model_validate(t).model_dump(mode="json")


def bank_alert(db: Session, user, bank: str) -> dict:
    if bank not in ALERTS:
        raise SimulationError(f"Pick one of: {', '.join(ALERTS)}")
    sender, domain, subject, template = ALERTS[bank]
    body = template.format(d=_local_today(user), ref="".join(secrets.choice("0123456789") for _ in range(12)))
    outcome, row, _ = inbound.read_alert(user, sender, subject, body, f"dkim=pass header.d={domain}")
    if row is None:                                   # a format this server's parser no longer reads
        raise SimulationError(f"The sample alert couldn't be read ({outcome}).")
    email = {"from": sender, "subject": subject, "text": body}
    if is_demo(user):
        d = categorise(row.description_raw, row.direction, normalize(row.description_raw), load_memory(db, user.id))
        return {"email": email, "saved": False, "transaction": {
            "transaction_date": row.date, "amount": row.amount, "direction": row.direction, "merchant_raw": row.description_raw,
            "merchant_clean": d.merchant_clean, "category": d.category, "subcategory": d.subcategory, "is_sample": True}}
    simulation_id = uuid.uuid4()
    transaction_service.import_rows(db, user, [row], simulation_id=simulation_id)
    return {"email": email, "saved": True, "transaction": _sample(db, simulation_id)}


def quick_add(db: Session, user, text: str, save: bool) -> dict:
    today = _local_today(user)
    parsed = parse_quick_add(text, today)
    if not parsed:
        raise SimulationError("Start with an amount, like “150 auto cash”.")
    payload = {**parsed, "today": today.isoformat()}
    reply = {"text": _entry_text(payload), "buttons": ["✓ Save", "✎ Edit category", "✗ Cancel"]}
    if not save or is_demo(user):
        return {"parsed": parsed, "reply": reply, "saved": False}
    simulation_id = uuid.uuid4()
    transaction_service.create_manual_transaction(db, user, ManualTransactionCreate(
        client_id=str(simulation_id), date=parsed["date"], amount=parsed["amount"], direction=parsed["direction"],
        merchant=parsed["merchant"][:100], category=parsed["category"], payment_method=parsed["payment_method"]),
        simulation_id=simulation_id)
    return {"parsed": parsed, "reply": reply, "saved": True, "transaction": _sample(db, simulation_id)}
