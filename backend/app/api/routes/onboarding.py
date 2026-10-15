"""
First-login setup (skippable, resumable). State lives in users.onboarding.

  GET   /api/onboarding             state, coverage meter, supported banks / UPI apps, test-email status
  PATCH /api/onboarding             {step?, income?, payday?, banks?, upi_apps?, timezone?, status?}
  POST  /api/onboarding/test-email  start waiting for a test email to the forwarding address
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core import clock
from app.core.alert_senders import BANKS
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.inbound import InboundEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.services import coverage
from app.services.review import build_cards

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

STEPS = ("basics", "connect", "import", "review", "finish")
UPI_APPS = ("Google Pay", "PhonePe", "Paytm", "BHIM", "Amazon Pay", "CRED")
NOT_BANKS = {"gpay", "phonepe", "paytm"}       # in the sender list for alerts, but they're UPI apps
BANK_CHOICES = [{"key": b["key"], "name": b["name"]} for b in BANKS if b["key"] not in NOT_BANKS]


class OnboardingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: Optional[Literal[STEPS]] = None
    income: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=2)
    payday: Optional[int] = Field(default=None, ge=1, le=31)
    banks: Optional[List[str]] = Field(default=None, max_length=30)
    upi_apps: Optional[List[str]] = Field(default=None, max_length=10)
    timezone: Optional[str] = Field(default=None, max_length=64)
    status: Optional[Literal["active", "done", "skipped"]] = None

    @field_validator("banks")
    @classmethod
    def known_banks(cls, v):
        keys = {b["key"] for b in BANK_CHOICES}
        if v is not None and not set(v) <= keys:
            raise ValueError("unknown bank")
        return v

    @field_validator("upi_apps")
    @classmethod
    def known_apps(cls, v):
        if v is not None and not set(v) <= set(UPI_APPS):
            raise ValueError("unknown UPI app")
        return v

    @field_validator("timezone")
    @classmethod
    def real_timezone(cls, v):
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Unknown timezone; use an IANA name like Asia/Kolkata")
        return v


def _state(db: Session, user: User) -> dict:
    # accounts that already had data before onboarding existed aren't sent through it (Settings → Resume setup)
    first = "new" if user.onboarding is not None or db.query(Transaction.id).filter(Transaction.user_id == user.id).first() is None \
        else "skipped"
    return {"step": "basics", "status": first, "income": None, "payday": None, "banks": [], "upi_apps": [],
            "basics_done": False, "test_started_at": None, **(user.onboarding or {})}


def _view(db: Session, user: User) -> dict:
    state = _state(db, user)
    test_received = False
    if state["test_started_at"]:
        test_received = db.query(InboundEvent.id).filter(
            InboundEvent.user_id == user.id,
            InboundEvent.received_at >= datetime.fromisoformat(state["test_started_at"])).first() is not None
    src = coverage.sources(db, user)
    return {
        **state, "timezone": user.timezone, "test_received": test_received,
        "coverage": coverage.meter(user, src, len(build_cards(db, user)), email_verified=test_received),
        "sources": src, "bank_choices": BANK_CHOICES, "upi_choices": list(UPI_APPS), "steps": list(STEPS),
    }


@router.get("")
def get_onboarding(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _view(db, current_user)


@router.patch("")
def update_onboarding(payload: OnboardingUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    state = _state(db, current_user)
    changes = payload.model_dump(exclude_unset=True)
    if "timezone" in changes:
        if changes["timezone"]:
            current_user.timezone = changes["timezone"]
        del changes["timezone"]
    if "income" in changes and changes["income"] is not None:
        changes["income"] = str(changes["income"])
    if {"income", "payday", "banks", "upi_apps"} & set(changes):
        state["basics_done"] = True
    if changes.get("status") in ("done", "skipped"):
        state[f"{changes['status']}_at"] = clock.now().isoformat()
    state.update({k: v for k, v in changes.items() if v is not None or k in ("income", "payday")})
    current_user.onboarding = state
    db.commit()
    return _view(db, current_user)


@router.post("/test-email")
def start_test_email(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.onboarding = {**_state(db, current_user), "test_started_at": clock.now().isoformat()}
    db.commit()
    return _view(db, current_user)
