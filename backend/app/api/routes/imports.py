"""
Statement import routes. Statements are parsed in the browser; the server
never receives the file.

  POST /api/import/batch                   sanitized JSON rows (max 500; the web app sends 50) → saved via
                                           the merchant normalizer and dedup matcher
  GET /api/import/templates/{fingerprint}  saved column mapping for a header layout
  PUT /api/import/templates/{fingerprint}  save/replace it
  GET /api/import/uploads                  uploads, and row counts per source (Settings → Imports)
  POST /api/import/delete-preview          what deleting an upload or a source would remove
  POST /api/import/delete                  delete it, then recompute (services/imports.py)
"""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core import recaptcha
from app.core.database import get_db
from app.core.ratelimit import per_user
from app.core.subscription import require_active_subscription
from app.models.import_template import ImportTemplate
from app.models.user import User
from app.schemas.imports import ImportBatch, ImportBatchResult, ImportScope, ImportTemplateResponse, ImportTemplateUpsert
from app.services import imports, transaction_service

router = APIRouter(prefix="/api/import", tags=["import"])

Fingerprint = Path(pattern=r"^[0-9a-f]{64}$")


# The web app sends 50 rows a request (frontend/src/import/submit.js) and resends a batch that timed out, so the limit
# counts requests generously: 240 an hour is 12,000 rows.
REQUESTS_PER_HOUR = 240


@router.post("/batch", response_model=ImportBatchResult, dependencies=[Depends(recaptcha.require("import")), Depends(per_user("import", REQUESTS_PER_HOUR, 3600))])
def import_batch(
    payload: ImportBatch,
    current_user: User = Depends(get_current_user),
    _subscription: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    return transaction_service.import_rows(db, current_user, payload.rows, import_id=payload.import_id)


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


@router.get("/uploads")
def list_uploads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return imports.list_imports(db, current_user)


@router.post("/delete-preview")
def delete_preview(scope: ImportScope, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return imports.preview(db, current_user, **scope.model_dump())


@router.post("/delete", dependencies=[Depends(per_user("import-delete", 30, 3600))])
def delete_import(scope: ImportScope, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return imports.delete(db, current_user, **scope.model_dump())
