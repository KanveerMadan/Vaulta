"""
User rules (merchant → category/kind).

  GET    /api/rules        rules with how many transactions each matches
  POST   /api/rules        create (or replace) a rule
  PATCH  /api/rules/{id}   change the value
  DELETE /api/rules/{id}   remove it; affected transactions return to their
                           automatic values (this is the toast's "Undo")
Every change re-runs detection so it applies to past transactions at once.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.rules import RuleCreate, RuleList, RuleResponse, RuleUpdate, check_rule_value
from app.services.detection import run_detection
from app.services.keys import merchant_key

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _counts(db: Session, user: User) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.person_id.is_(None)):
        key = merchant_key(t)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _view(rule: Rule, counts: dict[str, int]) -> RuleResponse:
    return RuleResponse(id=rule.id, merchant_key=rule.merchant_key, merchant=rule.merchant_label, field=rule.field,
                        value=rule.value, origin=rule.origin, matches=counts.get(rule.merchant_key, 0))


def _owned(db: Session, user: User, rule_id: uuid.UUID) -> Rule:
    rule = db.query(Rule).filter(Rule.id == rule_id, Rule.user_id == user.id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return rule


@router.get("", response_model=RuleList)
def list_rules(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    counts = _counts(db, current_user)
    rules = db.query(Rule).filter(Rule.user_id == current_user.id).order_by(Rule.merchant_label, Rule.field).all()
    return RuleList(rules=[_view(r, counts) for r in rules])


def upsert_rule(db: Session, user: User, merchant_key_: str, merchant: str, field: str, value: str, origin: str) -> Rule:
    rule = db.query(Rule).filter(Rule.user_id == user.id, Rule.merchant_key == merchant_key_, Rule.field == field).first()
    if rule is None:
        rule = Rule(user_id=user.id, merchant_key=merchant_key_, field=field)
        db.add(rule)
    rule.merchant_label, rule.value, rule.origin = merchant[:100], value, origin
    db.commit()
    run_detection(db, user)
    return rule


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(payload: RuleCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = upsert_rule(db, current_user, payload.merchant_key, payload.merchant, payload.field, payload.value, "manual")
    return _view(rule, _counts(db, current_user))


@router.patch("/{rule_id}", response_model=RuleResponse)
def update_rule(rule_id: uuid.UUID, payload: RuleUpdate, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    rule = _owned(db, current_user, rule_id)
    try:
        check_rule_value(rule.field, payload.value)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    rule.value = payload.value
    db.commit()
    run_detection(db, current_user)
    return _view(rule, _counts(db, current_user))


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned(db, current_user, rule_id))
    db.commit()
    run_detection(db, current_user)
