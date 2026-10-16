"""
Bank alert forwarding (Connect page).

  GET  /api/inbound                         address, status, per-source counts, Gmail confirmation, sender list
  POST /api/inbound/regenerate              new address; the old one stops working
  POST /api/inbound/gmail-confirmation/dismiss
"""

from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import clock
from app.core.alert_senders import BANKS
from app.core.auth import get_current_user, get_recent_user
from app.core.ratelimit import per_user
from app.core.database import get_db
from app.models.inbound import GmailConfirmation, InboundEvent
from app.models.user import User
from app.services import activity, inbound

router = APIRouter(prefix="/api/inbound", tags=["inbound"])

UNREADABLE_WINDOW_DAYS = 30


class SourceCount(BaseModel):
    bank: str
    count: int
    last_received_at: Optional[str]


class Unreadable(BaseModel):
    bank: str
    count: int


class Confirmation(BaseModel):
    link: Optional[str]
    code: Optional[str]
    received_at: str


class BankSenders(BaseModel):
    key: str
    name: str
    senders: List[str]


class InboundStatus(BaseModel):
    address: Optional[str]          # None when the server has no INBOUND_DOMAIN
    last_received_at: Optional[str]
    this_week: int
    total: int
    sources: List[SourceCount]
    unreadable: List[Unreadable]
    gmail_confirmation: Optional[Confirmation]
    banks: List[BankSenders]


def status_for(db: Session, user: User) -> InboundStatus:
    now = clock.now()
    parsed = db.query(InboundEvent).filter(InboundEvent.user_id == user.id, InboundEvent.outcome == "parsed")
    sources = (db.query(InboundEvent.bank_name, func.count(InboundEvent.id), func.max(InboundEvent.received_at))
               .filter(InboundEvent.user_id == user.id, InboundEvent.outcome == "parsed")
               .group_by(InboundEvent.bank_name).order_by(func.count(InboundEvent.id).desc()).all())
    unreadable = (db.query(InboundEvent.bank_name, func.count(InboundEvent.id))
                  .filter(InboundEvent.user_id == user.id, InboundEvent.outcome == "unparsed",
                          InboundEvent.received_at >= now - timedelta(days=UNREADABLE_WINDOW_DAYS))
                  .group_by(InboundEvent.bank_name).all())
    confirmation = (db.query(GmailConfirmation).filter(GmailConfirmation.user_id == user.id, GmailConfirmation.dismissed_at.is_(None))
                    .order_by(GmailConfirmation.received_at.desc()).first())
    last = parsed.with_entities(func.max(InboundEvent.received_at)).scalar()
    return InboundStatus(
        address=inbound.address_for(db, user),
        last_received_at=last.isoformat() if last else None,
        this_week=parsed.filter(InboundEvent.received_at >= now - timedelta(days=7)).count(),
        total=parsed.count(),
        sources=[SourceCount(bank=b or "Unknown", count=n, last_received_at=at.isoformat() if at else None) for b, n, at in sources],
        unreadable=[Unreadable(bank=b or "Unknown", count=n) for b, n in unreadable],
        gmail_confirmation=Confirmation(link=confirmation.link, code=confirmation.code,
                                        received_at=confirmation.received_at.isoformat()) if confirmation else None,
        banks=[BankSenders(key=b["key"], name=b["name"], senders=b["senders"]) for b in BANKS],
    )


@router.get("", response_model=InboundStatus)
def get_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return status_for(db, current_user)


@router.post("/regenerate", response_model=InboundStatus, dependencies=[Depends(per_user("regenerate", 10, 3600, get_recent_user))])
def regenerate(current_user: User = Depends(get_recent_user), db: Session = Depends(get_db)):
    activity.record(db, current_user, "address_regenerated")
    inbound.regenerate_address(db, current_user)          # commits
    return status_for(db, current_user)


@router.post("/gmail-confirmation/dismiss", response_model=InboundStatus)
def dismiss_confirmation(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(GmailConfirmation).filter(GmailConfirmation.user_id == current_user.id,
                                       GmailConfirmation.dismissed_at.is_(None)).update({"dismissed_at": clock.now()})
    db.commit()
    return status_for(db, current_user)
