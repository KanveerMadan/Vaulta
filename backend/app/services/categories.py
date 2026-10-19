"""
Subcategories (taxonomy and the user's own) and tags.

A subcategory is either a taxonomy id ("food.delivery", services/taxonomy.py) or "custom:<uuid>" for one the user
made inside a group. Tags are free labels across categories (models/category.py).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.category import CustomSubcategory, Tag, TransactionTag
from app.models.rule import Rule
from app.models.transaction import Budget, Transaction
from app.services import taxonomy

MAX_NAME = 40
MAX_TAGS_PER_TRANSACTION = 10


class CategoryError(ValueError):
    pass


def custom_subcategories(db: Session, user_id) -> dict[str, CustomSubcategory]:
    return {c.key: c for c in db.query(CustomSubcategory).filter(CustomSubcategory.user_id == user_id)}


def group_of(db: Session, user_id, subcategory: Optional[str], custom: Optional[dict] = None) -> Optional[str]:
    """The group a subcategory belongs to, or None if it isn't a taxonomy id or one of the user's own."""
    if not subcategory:
        return None
    if subcategory.startswith(taxonomy.CUSTOM_PREFIX):
        custom = custom if custom is not None else custom_subcategories(db, user_id)
        c = custom.get(subcategory)
        return c.group if c else None
    return taxonomy.group_of(subcategory)


def label(subcategory: Optional[str], custom: dict) -> Optional[str]:
    if subcategory and subcategory in custom:
        return custom[subcategory].name
    return taxonomy.label(subcategory)


def _clean(name: str) -> str:
    name = " ".join((name or "").split())
    if not name or len(name) > MAX_NAME:
        raise CategoryError(f"Names are 1–{MAX_NAME} characters.")
    return name


def create_subcategory(db: Session, user, group: str, name: str) -> CustomSubcategory:
    if group not in taxonomy.GROUPS:
        raise CategoryError("Pick one of the category groups.")
    name = _clean(name)
    taken = {s["name"].lower() for s in taxonomy.GROUPS[group]["subcategories"]}
    taken |= {c.name.lower() for c in custom_subcategories(db, user.id).values() if c.group == group}
    if name.lower() in taken:
        raise CategoryError(f"{group} already has “{name}”.")
    row = CustomSubcategory(id=uuid.uuid4(), user_id=user.id, group=group, name=name)
    db.add(row)
    db.commit()
    return row


def delete_subcategory(db: Session, user, row: CustomSubcategory) -> None:
    """Transactions and budgets using it fall back to the group alone."""
    for field in ("subcategory", "auto_subcategory"):
        db.query(Transaction).filter(Transaction.user_id == user.id, getattr(Transaction, field) == row.key).update({field: None})
    db.query(Budget).filter(Budget.user_id == user.id, Budget.subcategory == row.key).update({"is_active": False})
    db.query(Rule).filter(Rule.user_id == user.id, Rule.field == "category", Rule.value == row.key).delete()
    db.delete(row)
    db.commit()


# ── Tags ──────────────────────────────────────────────────────────────────────

def tags_by_id(db: Session, user_id) -> dict[uuid.UUID, Tag]:
    return {t.id: t for t in db.query(Tag).filter(Tag.user_id == user_id)}


def tag_names_for(db: Session, user_id, transaction_ids: list) -> dict[uuid.UUID, list[str]]:
    """{transaction id: sorted tag names} for these transactions."""
    if not transaction_ids:
        return {}
    names = {t.id: t.name for t in db.query(Tag).filter(Tag.user_id == user_id)}
    out: dict = {}
    for tid, tag_id in db.query(TransactionTag.transaction_id, TransactionTag.tag_id).filter(
            TransactionTag.user_id == user_id, TransactionTag.transaction_id.in_(transaction_ids)):
        out.setdefault(tid, []).append(names[tag_id])
    return {k: sorted(v, key=str.lower) for k, v in out.items()}


def find_tag(db: Session, user_id, name: str) -> Optional[Tag]:
    """Case-insensitive (names are encrypted, so this matches in Python)."""
    name = " ".join((name or "").split()).lower()
    return next((t for t in db.query(Tag).filter(Tag.user_id == user_id) if t.name.lower() == name), None)


def set_tags(db: Session, user, txn: Transaction, names: list[str]) -> list[str]:
    """Replace the transaction's tags with `names`, creating tags that don't exist yet. Caller commits."""
    clean: dict[str, str] = {}
    for n in names:
        clean.setdefault(_clean(n).lower(), _clean(n))      # same name in another case: the first spelling wins
    clean = list(clean.values())
    if len(clean) > MAX_TAGS_PER_TRANSACTION:
        raise CategoryError(f"Up to {MAX_TAGS_PER_TRANSACTION} tags per transaction.")
    tags = []
    for name in clean:
        tag = find_tag(db, user.id, name)
        if tag is None:
            tag = Tag(id=uuid.uuid4(), user_id=user.id, name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)
    db.query(TransactionTag).filter(TransactionTag.transaction_id == txn.id).delete()
    for tag in tags:
        db.add(TransactionTag(transaction_id=txn.id, tag_id=tag.id, user_id=user.id))
    db.flush()
    txn._tags = sorted((t.name for t in tags), key=str.lower)
    return txn._tags


def transaction_ids_with_tag(db: Session, user_id, name: str) -> list:
    tag = find_tag(db, user_id, name)
    if tag is None:
        return []
    return [tid for (tid,) in db.query(TransactionTag.transaction_id).filter(TransactionTag.tag_id == tag.id)]


def delete_unused_tags(db: Session, user_id) -> None:
    used = {tag_id for (tag_id,) in db.query(TransactionTag.tag_id).filter(TransactionTag.user_id == user_id)}
    for tag in db.query(Tag).filter(Tag.user_id == user_id):
        if tag.id not in used:
            db.delete(tag)
