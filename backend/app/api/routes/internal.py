"""
Internal endpoints for the scheduler. Not for browsers.

  POST /internal/run-reports    header X-Internal-Secret: $INTERNAL_SECRET
  POST /internal/inbound-email  from the Cloudflare Email Worker (infra/email-worker/): one email,
                                ≤ 256 KB, processed in memory; only metadata / the normalized row is kept
Refuses everything when INTERNAL_SECRET isn't configured.
"""

import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services import inbound, scheduler

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def require_secret(x_internal_secret: str = Header(default="")) -> None:
    if not settings.INTERNAL_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Internal endpoints are disabled.")
    if not hmac.compare_digest(x_internal_secret.encode(), settings.INTERNAL_SECRET.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad secret.")


@router.post("/run-reports", dependencies=[Depends(require_secret)])
def run_reports(db: Session = Depends(get_db)):
    return scheduler.run(db)


class InboundEmail(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    to: str = Field(max_length=2000)
    from_: str = Field(alias="from", max_length=500)
    subject: str = Field(default="", max_length=1000)
    text: Optional[str] = None
    html: Optional[str] = None
    auth_results: str = Field(default="", max_length=8000)


@router.post("/inbound-email", dependencies=[Depends(require_secret)])
async def inbound_email(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > inbound.MAX_EMAIL_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Email too large.")
    if inbound.inbound_host() is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="INBOUND_DOMAIN isn't configured.")
    try:
        mail = InboundEmail.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Expected {to, from, subject, text, html, auth_results}.")
    outcome = inbound.process(db, mail.to, mail.from_, mail.subject, mail.text, mail.html, mail.auth_results)
    return {"outcome": outcome}
