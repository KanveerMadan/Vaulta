"""User settings. GET/PATCH /api/settings"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.chat import Settings, SettingsUpdate
from app.services import email

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _view(user: User) -> Settings:
    return Settings(**{f: getattr(user, f) for f in Settings.model_fields if f != "email_configured"},
                    email_configured=email.configured())


@router.get("", response_model=Settings)
def get_settings(current_user: User = Depends(get_current_user)):
    return _view(current_user)


@router.patch("", response_model=Settings)
def update_settings(payload: SettingsUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field in payload.model_fields_set:
        if getattr(payload, field) is not None:
            setattr(current_user, field, getattr(payload, field))
    db.commit()
    db.refresh(current_user)
    return _view(current_user)
