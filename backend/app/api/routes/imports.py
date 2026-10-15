"""
Statement import routes. Statements are parsed in the browser; the server
never receives the file.

  GET /api/import/templates/{fingerprint}  saved column mapping for a header layout
  PUT /api/import/templates/{fingerprint}  save/replace it
"""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.import_template import ImportTemplate
from app.models.user import User
from app.schemas.imports import ImportTemplateResponse, ImportTemplateUpsert

router = APIRouter(prefix="/api/import", tags=["import"])

Fingerprint = Path(pattern=r"^[0-9a-f]{64}$")


def _template(db: Session, user: User, fingerprint: str):
    return (
        db.query(ImportTemplate)
        .filter(ImportTemplate.user_id == user.id, ImportTemplate.fingerprint == fingerprint)
        .first()
    )


@router.get("/templates/{fingerprint}", response_model=ImportTemplateResponse)
def get_template(
    fingerprint: str = Fingerprint,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = _template(db, current_user, fingerprint)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No saved mapping for this layout.")
    return template


@router.put("/templates/{fingerprint}", response_model=ImportTemplateResponse)
def put_template(
    payload: ImportTemplateUpsert,
    fingerprint: str = Fingerprint,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = _template(db, current_user, fingerprint)
    if template is None:
        template = ImportTemplate(user_id=current_user.id, fingerprint=fingerprint)
        db.add(template)
    template.column_count = payload.column_count
    template.source_type = payload.source_type
    template.mapping = payload.mapping.model_dump()
    db.commit()
    db.refresh(template)
    return template
