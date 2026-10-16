"""
Your data (Settings).

  GET /api/export     one zip: data.json + a CSV per table, decrypted, built for this request and not kept
  GET /api/activity   the last 100 account events: sign-ins, exports, deletions, links, settings changes
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_recent_user
from app.core.database import get_db
from app.core.ratelimit import per_user
from app.models.user import User
from app.services import activity, export

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
