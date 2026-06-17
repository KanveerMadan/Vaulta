"""
Subscription Gating — Phase 2

Provides FastAPI dependencies that gate data endpoints based on subscription_status:

  - require_active_subscription: hard-blocks endpoints once a "past_due" user's
    3-day grace period expires AND once "cancelled". "trial" and "active" pass.

  - get_data_date_floor: returns the earliest transaction_date a user is allowed
    to query. Trial/free users see last 30 days only (per roadmap). Active
    subscribers see everything (returns None = no floor).

Usage in routes:
    @router.get("/summary")
    def get_summary(
        current_user: User = Depends(get_current_user),
        _: None = Depends(require_active_subscription),
        date_floor: Optional[datetime] = Depends(get_data_date_floor),
        db: Session = Depends(get_db),
    ):
        ...

Both dependencies are no-ops (pass everything through) for the special case
where RAZORPAY_KEY_ID is not configured — i.e. local dev / before Phase 2
payments are live, the app behaves as if everyone has an active subscription.
This prevents Phase 1 functionality from breaking before Razorpay is set up.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.config import settings
from app.models.user import User

GRACE_PERIOD_DAYS = 3
TRIAL_DATA_WINDOW_DAYS = 30


def _payments_configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def require_active_subscription(current_user: User = Depends(get_current_user)) -> None:
    """
    Raises 402 Payment Required if:
      - subscription_status == "cancelled", or
      - subscription_status == "past_due" AND grace period (current_period_end + 3 days) has passed

    "trial" and "active" always pass. If Razorpay isn't configured yet
    (local dev, pre-Phase-2-setup), this is a no-op.
    """
    if not _payments_configured():
        return

    status_value = current_user.subscription_status or "trial"

    if status_value == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your subscription has been cancelled. Subscribe to continue using Vaulta.",
        )

    if status_value == "past_due":
        if current_user.current_period_end:
            grace_deadline = current_user.current_period_end + timedelta(days=GRACE_PERIOD_DAYS)
            if datetime.now(timezone.utc) > grace_deadline:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Your payment is overdue and the grace period has ended. "
                           "Please update your payment method to continue.",
                )
        # Within grace period — allow through (banner shown on frontend)

    # "trial" and "active" — pass through


def get_data_date_floor(current_user: User = Depends(get_current_user)) -> Optional[datetime]:
    """
    Returns the earliest transaction_date the user is allowed to query.

    - "active" subscribers: None (no restriction)
    - "trial" / "past_due" (within grace) / unconfigured payments: last 30 days only
    - "cancelled": handled by require_active_subscription (raises before this runs
      if used together) — but if used standalone, also returns 30-day floor as
      a safe default.
    """
    if not _payments_configured():
        return None

    if (current_user.subscription_status or "trial") == "active":
        return None

    return datetime.now(timezone.utc) - timedelta(days=TRIAL_DATA_WINDOW_DAYS)