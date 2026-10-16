"""
Linking a Telegram chat (Settings).

  GET    /api/telegram             linked?, weekly summary on?, bot username, configured?
  POST   /api/telegram/link-code   one-time code (10 minutes) to send as /start <code>
  PATCH  /api/telegram             {"weekly": bool}
  DELETE /api/telegram             unlink
"""

from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_sensitive_user
from app.core.ratelimit import per_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services import activity, telegram, telegram_bot

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


class TelegramStatus(BaseModel):
    configured: bool
    bot_username: Optional[str]
    linked: bool
    weekly: bool


class LinkCode(BaseModel):
    code: str
    expires_at: str
    bot_username: Optional[str]


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    weekly: bool


def _status(user: User) -> TelegramStatus:
    return TelegramStatus(configured=telegram.configured(), bot_username=settings.TELEGRAM_BOT_USERNAME or None,
                          linked=user.telegram_chat_id is not None, weekly=user.telegram_weekly)


@router.get("", response_model=TelegramStatus)
def get_status(current_user: User = Depends(get_current_user)):
    return _status(current_user)


@router.post("/link-code", response_model=LinkCode, dependencies=[Depends(per_user("telegram-link", 10, 3600, get_sensitive_user))])
def link_code(current_user: User = Depends(get_sensitive_user), db: Session = Depends(get_db)):
    code, expires = telegram_bot.new_link_code(db, current_user)
    return LinkCode(code=code, expires_at=expires.isoformat(), bot_username=settings.TELEGRAM_BOT_USERNAME or None)


@router.patch("", response_model=TelegramStatus)
def update(payload: TelegramUpdate, current_user: User = Depends(get_sensitive_user), db: Session = Depends(get_db)):
    current_user.telegram_weekly = payload.weekly
    activity.record(db, current_user, "settings_changed", {"fields": ["telegram_weekly"]})
    db.commit()
    return _status(current_user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def unlink(current_user: User = Depends(get_sensitive_user), db: Session = Depends(get_db)):
    telegram_bot.unlink(db, current_user)
