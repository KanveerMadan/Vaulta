"""
Simulations and their sample rows (Phase 8; core/samples.py).

  GET    /api/simulations           {samples}: how many sample rows the user has now
  DELETE /api/simulations           clear them all now (they also go by themselves after an hour)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import samples

router = APIRouter(prefix="/api/simulations", tags=["simulations"])


@router.get("")
def sample_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    samples.purge_expired(db, user)
    return {"samples": samples.count(db, user)}


@router.delete("")
def clear_samples(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"cleared": samples.clear(db, user)}
