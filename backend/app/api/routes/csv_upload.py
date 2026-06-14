import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import transaction_service
from app.services.csv_parser import CSVParseError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/csv", tags=["csv"])

# 10 MB max — typical 12-month statement is well under 1 MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    # Excel-exported CSVs sometimes arrive as these:
    "application/vnd.ms-excel",
    "application/octet-stream",
}


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a bank statement CSV. Supports HDFC, ICICI, SBI, Axis, Kotak.

    - Bank format is auto-detected from column headers.
    - Merchant names are normalized automatically.
    - Re-uploading the same file is safe (duplicate transactions are skipped).
    - Only debit transactions are imported (credits/income: Phase 3 feature).

    Returns:
        {bank, total_rows, inserted, skipped_duplicate}
    """
    # Validate file extension
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .csv files are accepted. Export your bank statement as CSV.",
        )

    # Read and size-check
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )

    try:
        result = transaction_service.ingest_csv(
            db=db,
            user=current_user,
            file_bytes=file_bytes,
            filename=filename,
        )
    except CSVParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"CSV upload failed for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your file. Please try again.",
        )

    return result