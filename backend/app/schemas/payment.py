from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CreateSubscriptionResponse(BaseModel):
    subscription_id: str
    razorpay_key_id: str  # Public key — frontend needs this to open Razorpay Checkout
    short_url: Optional[str] = None  # Hosted payment page, alternative to embedded checkout


class SubscriptionStatusResponse(BaseModel):
    subscription_status: str  # trial | active | past_due | cancelled
    current_period_end: Optional[datetime] = None
    grace_period_ends_at: Optional[datetime] = None  # Set during past_due (3-day grace)


class WebhookAck(BaseModel):
    status: str = "ok"