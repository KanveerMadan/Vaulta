"""
Reports.

  GET  /api/reports              archive (newest first)
  GET  /api/reports/{id}         one report: JSON + narrative
  POST /api/reports/generate     {"period_type": weekly|monthly|annual, "date"?: YYYY-MM-DD}
                                 builds the report for that period now (default: the last
                                 complete one); returns the existing one if already built
"""

import uuid
from datetime import date as Date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.services import getting_started
from app.models.report import Report
from app.models.user import User
from app.services import reports

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportSummary(BaseModel):
    id: uuid.UUID
    period_type: str
    period_start: Date
    period_end: Date
    label: str
    spend: str
    created_at: str


class ReportDetail(ReportSummary):
    data: dict
    narrative: str
    narrative_source: str


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_type: Literal["weekly", "monthly", "annual"]
    date: Optional[Date] = None   # a day inside the period


def _summary(r: Report) -> dict:
    return {"id": r.id, "period_type": r.period_type, "period_start": r.period_start, "period_end": r.period_end,
            "label": r.json["period"]["label"], "spend": r.json["totals"]["spend"], "created_at": r.created_at.isoformat()}


def _detail(r: Report) -> ReportDetail:
    return ReportDetail(**_summary(r), data=r.json, narrative=r.narrative, narrative_source=r.narrative_source)


@router.get("", response_model=List[ReportSummary])
def list_reports(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Report).filter(Report.user_id == current_user.id).order_by(Report.period_start.desc(), Report.period_type).all()
    return [ReportSummary(**_summary(r)) for r in rows]


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.query(Report).filter(Report.id == report_id, Report.user_id == current_user.id).first()
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    getting_started.note_opened(db, current_user, "report")      # a getting-started checklist item
    return _detail(r)


@router.post("/generate", response_model=ReportDetail)
def generate(payload: GenerateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    day = payload.date or reports.last_complete(payload.period_type)
    report, _ = reports.generate(db, current_user.id, payload.period_type, day)
    return _detail(report)
