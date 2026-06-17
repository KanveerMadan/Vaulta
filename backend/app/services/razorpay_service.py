"""
Razorpay Service — Phase 2

Handles subscription creation (₹99/month) and webhook signature verification.

Subscription lifecycle (driven by webhooks, see api/routes/payments.py):
  trial -> active        (subscription.activated)
  active -> past_due     (subscription.charged fails / subscription.pending)
  past_due -> active     (subscription.charged succeeds within grace period)
  past_due -> cancelled  (grace period expires without successful charge)
  any -> cancelled       (subscription.cancelled)

Grace period: 3 days (per roadmap "Payment failure UX: grace period banner (3 days),
not a hard block"). The grace period deadline is stored implicitly — when a
subscription enters past_due, current_period_end + 3 days is the cutoff;
Phase 2 doesn't need a separate column since Razorpay's subscription object
already tracks current_end, and we just gate based on subscription_status +
a computed deadline at read-time (see api/routes/payments.py:get_subscription_status).
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import razorpay

from app.core.config import settings

logger = logging.getLogger(__name__)


class RazorpayError(Exception):
    pass


def _get_client() -> "razorpay.Client":
    settings.require("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_subscription(customer_email: str, customer_name: str | None = None) -> dict:
    """
    Create a Razorpay subscription for the ₹99/month plan.

    Returns the Razorpay subscription object, including:
      - id (subscription_id)
      - short_url (hosted checkout page)
      - status ("created")

    The frontend uses `id` to open Razorpay Checkout (embedded) and/or
    redirects to `short_url` as a fallback.
    """
    settings.require("RAZORPAY_PLAN_ID")
    client = _get_client()

    try:
        subscription = client.subscription.create({
            "plan_id": settings.RAZORPAY_PLAN_ID,
            "customer_notify": 1,
            "total_count": 120,  # 10 years of monthly billing — effectively "until cancelled"
            "notes": {
                "email": customer_email,
                "name": customer_name or "",
            },
        })
    except Exception as e:
        logger.error(f"Razorpay subscription creation failed: {e}")
        raise RazorpayError(f"Failed to create subscription: {e}") from e

    return subscription


def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify Razorpay webhook signature using HMAC-SHA256 with RAZORPAY_WEBHOOK_SECRET.

    Razorpay docs: https://razorpay.com/docs/webhooks/validate-test/
    """
    settings.require("RAZORPAY_WEBHOOK_SECRET")

    expected_signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature_header)


def fetch_subscription(subscription_id: str) -> dict:
    """Fetch current subscription state from Razorpay (used for status reconciliation)."""
    client = _get_client()
    try:
        return client.subscription.fetch(subscription_id)
    except Exception as e:
        logger.error(f"Failed to fetch Razorpay subscription {subscription_id}: {e}")
        raise RazorpayError(f"Failed to fetch subscription: {e}") from e