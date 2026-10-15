"""
Anomalies.

  GET   /api/anomalies          ?status=open|dismissed (default open)
  PATCH /api/anomalies/{id}     {"status": "open" | "dismissed"}
"""

import uuid
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.anomaly import Anomaly
from app.models.user import User

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


class AnomalyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    occurred_on: str
    details: dict
    status: str


class AnomalyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["open", "dismissed"]


def _view(a: Anomaly) -> AnomalyResponse:
    return AnomalyResponse(id=a.id, type=a.type, occurred_on=a.occurred_on.isoformat(), details=a.details, status=a.status)


@router.get("", response_model=List[AnomalyResponse])
def list_anomalies(status_: Literal["open", "dismissed"] = Query(default="open", alias="status"),
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Anomaly).filter(Anomaly.user_id == current_user.id, Anomaly.status == status_)
            .order_by(Anomaly.occurred_on.desc()).all())
    return [_view(a) for a in rows]


@router.patch("/{anomaly_id}", response_model=AnomalyResponse)
def update_anomaly(anomaly_id: uuid.UUID, payload: AnomalyUpdate,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Anomaly).filter(Anomaly.id == anomaly_id, Anomaly.user_id == current_user.id).first()
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    a.status = payload.status
    db.commit()
    return _view(a)
