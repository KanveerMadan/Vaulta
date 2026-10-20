"""
One-click unsubscribe from a report type (link in every report email).

  GET  /unsubscribe?token=…   turns that email off and shows a confirmation page
  POST /unsubscribe?token=…   the same, for mail clients' one-click (RFC 8058)
No login: the token is signed (services/report_email.py).
"""

import uuid
from html import escape

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ratelimit import per_ip
from app.core.database import get_db
from app.core.scope import find_user
from app.services.report_email import read_unsubscribe_token

router = APIRouter(tags=["unsubscribe"], include_in_schema=False)


def _page(title: str, body: str, code: int) -> HTMLResponse:
    return HTMLResponse(status_code=code, content=(
        f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title></head>'
        f'<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#F2F7F3;color:#1A2E1E;padding:40px 16px">'
        f'<div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #D4E4D7;border-radius:12px;padding:24px">'
        f'<h1 style="font-size:20px;margin:0 0 8px">{escape(title)}</h1><p style="font-size:14px;line-height:1.6">{body}</p>'
        f'</div></body></html>'))


def _unsubscribe(token: str, db: Session) -> HTMLResponse:
    parsed = read_unsubscribe_token(token)
    user = None
    if parsed:
        try:
            user = find_user(db, "id", uuid.UUID(parsed[0]))
        except ValueError:
            user = None
    if user is None:
        return _page("Link not valid", "This unsubscribe link isn't valid. You can change emails in vaulta.in's Settings.", 400)
    setattr(user, f"email_{parsed[1]}", False)
    db.commit()
    settings_url = f"{settings.APP_BASE_URL.rstrip('/')}/settings"
    return _page("Unsubscribed", f"You won't get {escape(parsed[1])} report emails any more. The reports are still in the app. "
                                 f'<a href="{escape(settings_url)}">Change email settings</a>.', 200)


@router.get("/unsubscribe", dependencies=[Depends(per_ip("unsubscribe", 30, 60))])
def unsubscribe_page(token: str = Query(max_length=200), db: Session = Depends(get_db)):
    return _unsubscribe(token, db)


@router.post("/unsubscribe", dependencies=[Depends(per_ip("unsubscribe", 30, 60))])
def unsubscribe_one_click(token: str = Query(max_length=200), db: Session = Depends(get_db)):
    return _unsubscribe(token, db)
