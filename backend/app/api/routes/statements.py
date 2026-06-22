"""
Unified statement upload route — Phase 1.5

Accepts both CSV bank statements and UPI app statement PDFs at a single
endpoint. File type is auto-detected: .csv dispatches to ingest_csv,
.pdf dispatches to ingest_upi_statement. No manual source selection from
the client — auto-detection covers everything (Section 3 / master prompt).

Replaces /api/csv/upload (csv_upload.py). Frontend StatementUpload.jsx
already posts to /api/statements/upload.
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.subscription import require_active_subscription
from app.models.user import User
from app.services import transaction_service
from app.services.csv_parser import CSVParseError
from app.services.upi_statement_parser import UPIParseError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/statements", tags=["statements"])

# 20 MB max — PDFs are larger than CSVs; a year of Google Pay history
# with receipts is well under 10 MB in practice, but give headroom.
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_statement(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    _subscription: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """
    Upload a bank statement (CSV) or UPI app statement (PDF).

    Supported CSV sources: HDFC, ICICI, SBI, Axis, Kotak.
    Supported PDF sources: Google Pay (PhonePe and Paytm coming soon).

    - Source is auto-detected from file contents; no manual selection needed.
    - Merchant names are normalized automatically.
    - Re-uploading the same file is safe — duplicates are skipped.
    - Cross-source deduplication runs automatically if both a bank CSV and a
      UPI statement are uploaded for the same period.

    Returns:
        For CSV: {bank, total_rows, inserted, matched_existing, skipped_duplicate}
        For PDF: {source, total_rows, inserted, matched_existing,
                  skipped_duplicate, by_nature}
    """
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("csv", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Only .csv and .pdf files are accepted. "
                "Export your bank statement as CSV, or export your UPI app "
                "statement as PDF."
            ),
        )

    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    try:
        if ext == "csv":
            result = transaction_service.ingest_csv(
                db=db,
                user=current_user,
                file_bytes=file_bytes,
                filename=filename,
            )
        else:
            result = transaction_service.ingest_upi_statement(
                db=db,
                user=current_user,
                file_bytes=file_bytes,
                filename=filename,
            )

    except (CSVParseError, UPIParseError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"Statement upload failed: user={current_user.id}, file={filename!r}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your file. Please try again.",
        )

    return result