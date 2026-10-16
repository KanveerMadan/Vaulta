from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.auth import get_current_user, get_recent_user, get_sensitive_user
from app.core.ratelimit import per_ip, per_user
from app.core.appcheck import require_app_check
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.services import account, activity, demo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/demo", dependencies=[Depends(require_app_check), Depends(per_ip("demo", settings.DEMO_SESSIONS_PER_IP, 600))])
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
    current_user: User = Depends(get_sensitive_user),
    db: Session = Depends(get_db),
):
    """Update name or other profile fields."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
        activity.record(db, current_user, "profile_changed", {"fields": ["full_name"]})
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=204, dependencies=[Depends(per_user("delete-account", 5, 3600, get_recent_user))])
def delete_me(
    current_user: User = Depends(get_recent_user),
    db: Session = Depends(get_db),
):
    """
    Delete everything, the login included (services/deletion.py). Needs a recent sign-in. If Firebase can't delete
    the login right now, the deletion is recorded and the hourly run completes it.
    """
    from app.services import deletion
    deletion.delete_account(db, current_user)


class ResetRequest(BaseModel):
    email: str = Field(max_length=320)


@router.post("/password-reset-requested", status_code=204,
             dependencies=[Depends(require_app_check), Depends(per_ip("password-reset", 10, 3600))])
def password_reset_requested(payload: ResetRequest, db: Session = Depends(get_db)):
    """
    The web app reports that a reset email was asked for (Firebase sends it). For the account's activity log only;
    the answer is the same 204 whether or not the address has an account.
    """
    account.note_reset_requested(db, payload.email)
