"""
Internal endpoints for the scheduler. Not for browsers.

  POST /internal/run-reports   header X-Internal-Secret: $INTERNAL_SECRET
Refuses everything when INTERNAL_SECRET isn't configured.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services import scheduler

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def require_secret(x_internal_secret: str = Header(default="")) -> None:
    if not settings.INTERNAL_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Internal endpoints are disabled.")
    if not hmac.compare_digest(x_internal_secret.encode(), settings.INTERNAL_SECRET.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad secret.")


@router.post("/run-reports", dependencies=[Depends(require_secret)])
def run_reports(db: Session = Depends(get_db)):
    return scheduler.run(db)
