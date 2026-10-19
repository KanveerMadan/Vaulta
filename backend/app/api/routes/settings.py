"""User settings. GET/PATCH /api/settings"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_sensitive_user
from app.core.ratelimit import per_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.chat import Settings, SettingsUpdate
from app.services import activity, alerts, email

router = APIRouter(prefix="/api/settings", tags=["settings"])


COMPUTED = {"email_configured", "alert_channels"}


def _view(user: User) -> Settings:
    return Settings(**{f: getattr(user, f) for f in Settings.model_fields if f not in COMPUTED},
                    email_configured=email.configured(), alert_channels=alerts.channels(user))


@router.get("", response_model=Settings)
def get_settings(current_user: User = Depends(get_current_user)):
    return _view(current_user)


@router.patch("", response_model=Settings, dependencies=[Depends(per_user("settings", 120, 3600, get_sensitive_user))])
def update_settings(payload: SettingsUpdate, current_user: User = Depends(get_sensitive_user), db: Session = Depends(get_db)):
    for field in payload.model_fields_set - {"alert_channels"}:
        if getattr(payload, field) is not None:
            setattr(current_user, field, getattr(payload, field))
    if payload.alert_channels:
        merged = alerts.channels(current_user)
        for kind, chans in payload.alert_channels.items():
            merged[kind].update(chans)
        current_user.alert_prefs = merged
    if payload.model_fields_set:
        activity.record(db, current_user, "settings_changed", {"fields": sorted(payload.model_fields_set)})
    db.commit()
    db.refresh(current_user)
    return _view(current_user)
