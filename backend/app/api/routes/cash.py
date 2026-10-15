"""
Cash wallet.

  GET  /api/cash             balance, withdrawn / received / spent since the last declaration, unaccounted
  POST /api/cash/declare     {"amount": "1500"} cash in hand now → returns the gap to allocate if any
  POST /api/cash/reconcile   {"action": "have" | "misc" | "category", "category"?: …, "amount"?: …}
"""

from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.transaction import CATEGORIES
from app.services import cash
from app.services.chat_tools import llm_safe

router = APIRouter(prefix="/api/cash", tags=["cash"])


class Declare(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    amount: str = Field(pattern=r"^\d{1,10}(\.\d{1,2})?$")


class Reconcile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["have", "misc", "category"]
    category: Optional[str] = None
    amount: Optional[str] = Field(default=None, pattern=r"^\d{1,10}(\.\d{1,2})?$")


@router.get("")
def get_wallet(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return llm_safe(cash.wallet(db, current_user.id))


@router.post("/declare")
def declare(payload: Declare, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return llm_safe({**cash.declare(db, current_user, Decimal(payload.amount)), "wallet": cash.wallet(db, current_user.id)})


@router.post("/reconcile")
def reconcile(payload: Reconcile, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.action == "category" and payload.category not in CATEGORIES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pick a known category.")
    message = cash.reconcile(db, current_user, payload.action, payload.category,
                             Decimal(payload.amount) if payload.amount else None)
    return llm_safe({"message": message, "wallet": cash.wallet(db, current_user.id)})
