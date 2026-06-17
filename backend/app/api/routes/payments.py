"""
Payment Routes — Phase 2

  POST /api/payments/create-subscription -> creates Razorpay subscription, returns checkout details
  POST /api/payments/webhook              -> Razorpay webhook receiver (signature-verified, unauthenticated)
  GET  /api/payments/status               -> current user's subscription status + grace period info

Webhook events handled:
  subscription.activated  -> subscription_status = "active"
  subscription.charged    -> subscription_status = "active", update current_period_end
  subscription.pending    -> subscription_status = "past_due"
  subscription.halted     -> subscription_status = "past_due" (Razorpay stops retrying)
  subscription.cancelled  -> subscription_status = "cancelled"

Grace period (3 days, per roadmap):
  When status becomes "past_due", the user is NOT immediately blocked.
  GET /api/payments/status returns grace_period_ends_at = current_period_end + 3 days.
  Data endpoints (transactions/summary) check this via require_active_subscription
  dependency (app/core/subscription.py) — only hard-block once grace period expires.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.payment import CreateSubscriptionResponse, SubscriptionStatusResponse, WebhookAck
from app.services.razorpay_service import create_subscription, verify_webhook_signature, RazorpayError
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

GRACE_PERIOD_DAYS = 3


@router.post("/create-subscription", response_model=CreateSubscriptionResponse)
def create_subscription_route(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a ₹99/month Razorpay subscription for the authenticated user.
    Returns subscription_id for the frontend to open Razorpay Checkout.
    """
    if current_user.razorpay_subscription_id and current_user.subscription_status == "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an active subscription.",
        )

    try:
        subscription = create_subscription(
            customer_email=current_user.email,
            customer_name=current_user.full_name,
        )
    except RuntimeError as e:
        # settings.require() — Razorpay not configured
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Payments are not configured yet: {e}",
        )
    except RazorpayError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    current_user.razorpay_subscription_id = subscription["id"]
    db.commit()

    return CreateSubscriptionResponse(
        subscription_id=subscription["id"],
        razorpay_key_id=settings.RAZORPAY_KEY_ID,
        short_url=subscription.get("short_url"),
    )


@router.get("/status", response_model=SubscriptionStatusResponse)
def get_subscription_status(
    current_user: User = Depends(get_current_user),
):
    """
    Returns the current user's subscription status and, if past_due,
    the grace period deadline.
    """
    grace_deadline = None
    if current_user.subscription_status == "past_due" and current_user.current_period_end:
        grace_deadline = current_user.current_period_end + timedelta(days=GRACE_PERIOD_DAYS)

    return SubscriptionStatusResponse(
        subscription_status=current_user.subscription_status or "trial",
        current_period_end=current_user.current_period_end,
        grace_period_ends_at=grace_deadline,
    )


@router.post("/webhook", response_model=WebhookAck)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Razorpay webhook receiver. NOT behind get_current_user — verified via
    HMAC signature in the X-Razorpay-Signature header instead.
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        valid = verify_webhook_signature(body, signature)
    except RuntimeError as e:
        # RAZORPAY_WEBHOOK_SECRET not configured
        logger.error(f"Webhook signature verification unavailable: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    if not valid:
        logger.warning("Razorpay webhook signature verification FAILED — possible spoofed request.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event", "")
    logger.info(f"Razorpay webhook received: {event}")

    subscription_entity = (
        payload.get("payload", {}).get("subscription", {}).get("entity", {})
    )
    subscription_id = subscription_entity.get("id")

    if not subscription_id:
        # Event not subscription-related (e.g. payment.* events we don't act on) — ack and ignore
        return WebhookAck()

    user = db.query(User).filter(User.razorpay_subscription_id == subscription_id).first()
    if not user:
        logger.warning(f"Webhook for unknown subscription_id={subscription_id}")
        return WebhookAck()

    if event == "subscription.activated":
        user.subscription_status = "active"

    elif event == "subscription.charged":
        user.subscription_status = "active"
        current_end_unix = subscription_entity.get("current_end")
        if current_end_unix:
            user.current_period_end = datetime.fromtimestamp(current_end_unix, tz=timezone.utc)

    elif event in ("subscription.pending", "subscription.halted"):
        user.subscription_status = "past_due"

    elif event == "subscription.cancelled":
        user.subscription_status = "cancelled"

    else:
        logger.info(f"Unhandled Razorpay event type: {event}")

    db.commit()
    return WebhookAck()