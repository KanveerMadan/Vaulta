from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.services import demo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/demo")
def start_demo(db: Session = Depends(get_db)):
    """A short-lived session token for the shared read-only demo user (no sign-in). Seeds the demo if needed."""
    demo.ensure_fresh(db, create=True)
    token, ttl = demo.new_token()
    return {"token": token, "expires_in": ttl}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns the currently authenticated user's profile.
    Frontend calls this on every app load to verify auth state.
    """
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update name or other profile fields."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=204)
def delete_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hard delete — user requests full account deletion."""
    db.delete(current_user)
    db.commit()