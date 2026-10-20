"""
Export my data: everything Vaulta holds for the user, decrypted, as one zip built in memory for this request
(data.json, one CSV per table, README.txt). Nothing is written to disk or kept after the response.
Leaves out only key material and internal hashes (EXCLUDED), which mean nothing outside Vaulta.
"""

from __future__ import annotations

import csv
import enum
import io
import json
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core import clock
from app.core.database import Base
from app.models.user import User

EXCLUDED = {"data_key", "inbound_token_hash", "inbound_token_encrypted", "token_hash", "code_hash", "key_hash",
            "idempotency_key", "firebase_uid", "household_id"}

README = """vaulta.in data export ({when})

data.json      everything below in one file
csv/*.csv      one file per kind of record (transactions, budgets, goals, people, rules, chat history, reports, …)

Amounts are in rupees. Dates and times are ISO 8601 in UTC. This export was created when you asked for it and was
not stored by vaulta.in.
"""


def _cell(v):
    """A CSV cell. Text starting with = + - @ is prefixed with ' so spreadsheets don't run it as a formula."""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and not _is_number(v):
        return "'" + v
    return v


def _is_number(v: str) -> bool:
    try:
        Decimal(v)
        return True
    except ArithmeticError:
        return False


def _value(v):
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (Decimal, uuid.UUID)):
        return str(v)
    return v


def _rows(db: Session, model, user: User) -> list[dict]:
    columns = [c for c in model.__table__.columns if c.name not in EXCLUDED]
    if model is User:
        query = db.query(User).filter(User.id == user.id)
    else:
        query = db.query(model).filter(model.user_id == user.id)
    if "created_at" in model.__table__.columns:
        query = query.order_by(model.__table__.columns["created_at"])
    return [{c.name: _value(getattr(obj, c.key)) for c in columns} for obj in query]


def _models():
    out = []
    for mapper in sorted(Base.registry.mappers, key=lambda m: m.class_.__tablename__):
        table = mapper.class_.__table__
        if mapper.class_ is User or "user_id" in table.columns:
            out.append(mapper.class_)
    return out


def collect(db: Session, user: User) -> dict:
    return {model.__tablename__: _rows(db, model, user) for model in _models()}


def build_zip(db: Session, user: User) -> bytes:
    data = collect(db, user)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("vaulta-export/README.txt", README.format(when=clock.now().isoformat(timespec="seconds")))
        z.writestr("vaulta-export/data.json", json.dumps(data, ensure_ascii=False, indent=2, default=str))
        for table, rows in data.items():
            if not rows:
                continue
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _cell(v) for k, v in row.items()})
            z.writestr(f"vaulta-export/csv/{table}.csv", out.getvalue())
    return buf.getvalue()
