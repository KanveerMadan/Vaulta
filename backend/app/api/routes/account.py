"""
Your data (Settings).

  GET /api/export     one zip: data.json + a CSV per table, decrypted, built for this request and not kept
  GET /api/activity   the last 100 account events: sign-ins, exports, deletions, links, settings changes
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CodedError, get_current_user, get_recent_user, get_sensitive_user
from app.core.database import get_db
from app.core.ratelimit import per_user
from app.models.user import User
from app.services import account, activity, export

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/export", dependencies=[Depends(per_user("export", 10, 3600, get_recent_user))])
def export_data(current_user: User = Depends(get_recent_user), db: Session = Depends(get_db)):
    body = export.build_zip(db, current_user)
    activity.record(db, current_user, "export")
    db.commit()
    return Response(content=body, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="vaulta-export-{date.today().isoformat()}.zip"',
        "Cache-Control": "no-store",
    })


class ActivityItem(BaseModel):
    kind: str
    detail: Optional[dict]
    at: str


@router.get("/activity", response_model=List[ActivityItem])
def get_activity(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [ActivityItem(kind=e.kind, detail=e.detail, at=e.created_at.isoformat()) for e in activity.recent(db, current_user)]


@router.post("/account/reauth-failed", status_code=204, dependencies=[Depends(per_user("reauth-failed", 20, 3600))])
def reauth_failed(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The web app reports a failed "sign in again" (wrong password, closed popup), for the activity log."""
    activity.record(db, current_user, "reauth_failed")
    db.commit()


@router.post("/account/sign-out-everywhere", status_code=204,
             dependencies=[Depends(per_user("sign-out-everywhere", 10, 3600, get_sensitive_user))])
def sign_out_everywhere(current_user: User = Depends(get_sensitive_user), db: Session = Depends(get_db)):
    """Signs out every device, this one included. Telegram and demo sessions are unaffected."""
    account.sign_out_everywhere(db, current_user)
    db.commit()


class NewPassword(BaseModel):
    password: str = Field(max_length=512)


@router.post("/account/password", status_code=204, dependencies=[Depends(per_user("password", 10, 3600, get_recent_user))])
def change_password(payload: NewPassword, current_user: User = Depends(get_recent_user), db: Session = Depends(get_db)):
    """Change the password (or add one to a Google account). Signs out every other session; needs a recent sign-in."""
    try:
        account.set_password(db, current_user, payload.password)
    except account.PasswordRejected as e:
        raise CodedError(422, "weak_password", str(e))
    db.commit()


class Method(BaseModel):
    method: str = Field(max_length=40)


@router.get("/account/sign-in-methods")
def sign_in_methods(current_user: User = Depends(get_current_user)):
    """The ways this account can sign in, from Firebase."""
    return {"methods": [m for m in account.providers(current_user) if m in account.METHODS]}


@router.post("/account/sign-in-methods/linked", status_code=204,
             dependencies=[Depends(per_user("methods", 20, 3600, get_recent_user))])
def method_linked(payload: Method, current_user: User = Depends(get_recent_user), db: Session = Depends(get_db)):
    """After the web app links Google to this account: confirm with Firebase and log it."""
    if payload.method not in account.METHODS or not account.note_linked(db, current_user, payload.method):
        raise CodedError(409, "not_linked", "That sign-in method isn't linked to this account.")
    db.commit()


@router.delete("/account/sign-in-methods/{provider}", status_code=204,
               dependencies=[Depends(per_user("methods", 20, 3600, get_recent_user))])
def unlink_method(provider: str, current_user: User = Depends(get_recent_user), db: Session = Depends(get_db)):
    """Remove a sign-in method (never the last). Signs out every session, this one included."""
    if provider not in account.METHODS:
        raise CodedError(404, "unknown_method", "Unknown sign-in method.")
    try:
        account.unlink_method(db, current_user, provider)
    except KeyError:
        raise CodedError(404, "not_linked", "That sign-in method isn't linked to this account.")
    except account.LastMethod as e:
        raise CodedError(409, "last_method", str(e))
    db.commit()
