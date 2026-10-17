"""
Simulations and their sample rows (Phase 8; core/samples.py).

  GET    /api/simulations             {samples}: how many sample rows the user has now
  DELETE /api/simulations             clear them all now (they also go by themselves after an hour)
  POST   /api/simulations/bank-alert  {bank}: a sample alert through the alert pipeline → a sample transaction
  POST   /api/simulations/quick-add   {text, save}: what Telegram and quick add make of a line; save → a sample entry
Both simulations also work in the demo, where nothing is written (services/simulations.py).
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.ratelimit import check
from app.models.user import User
from app.services import samples, simulations

SIMULATIONS_PER_HOUR = 60


def _limit(user: User = Depends(get_current_user)) -> None:
    """Per user; in the shared demo, per visitor (its session), so one visitor can't use up everyone's."""
    check("simulations", getattr(user, "demo_session", None) or user.id, SIMULATIONS_PER_HOUR, 3600)


router = APIRouter(prefix="/api/simulations", tags=["simulations"])


@router.get("")
def sample_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    samples.purge_expired(db, user)
    return {"samples": samples.count(db, user)}


@router.delete("")
def clear_samples(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"cleared": samples.clear(db, user)}


class AlertSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    bank: Literal["hdfc", "icici", "sbi", "axis"] = "hdfc"


class QuickAddSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=120)
    save: bool = False


@router.post("/bank-alert", dependencies=[Depends(_limit)])
def simulate_bank_alert(payload: AlertSimulation, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return simulations.bank_alert(db, user, payload.bank)
    except simulations.SimulationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/quick-add", dependencies=[Depends(_limit)])
def simulate_quick_add(payload: QuickAddSimulation, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return simulations.quick_add(db, user, payload.text, payload.save)
    except simulations.SimulationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
