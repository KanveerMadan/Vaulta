import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, Date, String, SmallInteger, Boolean, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=True)

    # --- Data source connection flags ---
    # NOTE: gmail_connected is DEPRECATED — Gmail integration was removed entirely
    # (see Master Prompt Section 4/9: Google's restricted-scope OAuth verification
    # requires an ongoing paid annual security audit and caps unverified apps at
    # 100 test users, incompatible with Vaulta's fully-public goal). Column is
    # kept (not dropped) to avoid a destructive migration, but nothing writes to
    # it anymore and it should always read False for all users going forward.
    gmail_connected = Column(Boolean, default=False, nullable=False)
    sms_connected = Column(Boolean, default=False, nullable=False)
    aa_connected = Column(Boolean, default=False, nullable=False)

    # --- Settings ---
    ai_chat_enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    timezone = Column(String(64), nullable=False, default="Asia/Kolkata", server_default="Asia/Kolkata")
    # Which reports are built for the user, and which are also emailed
    reports_weekly = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    reports_monthly = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    reports_annual = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    email_weekly = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    email_monthly = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    email_annual = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    # --- Inbound alert email: <token>@in.<INBOUND_DOMAIN> ---
    # sha256 of the token for lookup; the token itself encrypted (ENCRYPTION_KEY) so the
    # address can be shown again. Regenerating replaces both; the old address stops working.
    inbound_token_hash = Column(String(64), nullable=True, unique=True)
    inbound_token_encrypted = Column(String, nullable=True)

    # --- Telegram bot ---
    telegram_chat_id = Column(BigInteger, nullable=True, unique=True)
    telegram_weekly = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Week end (Sunday) of the last unaccounted-cash reminder sent on Telegram
    cash_reminded_week = Column(Date, nullable=True)

    # --- Alerts: per-type channel choices ({type: {"telegram": bool, "email": bool}}; missing = default)
    # and Telegram quiet hours in local time (start hour inclusive, end hour exclusive)
    alert_prefs = Column(JSON, nullable=True)
    quiet_start = Column(SmallInteger, nullable=False, default=22, server_default=text("22"))
    quiet_end = Column(SmallInteger, nullable=False, default=8, server_default=text("8"))

    # --- Subscription status (Phase 2) ---
    # Values: trial | active | past_due | cancelled
    subscription_status = Column(String, nullable=True, default="trial")

    # Razorpay subscription ID — set when create-subscription is called.
    # Used to reconcile webhook events and fetch current period info.
    razorpay_subscription_id = Column(String, nullable=True, index=True)

    # End of the current billing period (from Razorpay subscription.charged event).
    # Used to compute the 3-day grace period when status == past_due:
    #   grace_deadline = current_period_end + 3 days
    current_period_end = Column(DateTime(timezone=True), nullable=True)

    # --- Phase 6: Family Finance Dashboard prep ---
    # household_id added NOW so every auth check written in Phases 0-5 can account
    # for future household scoping without a full API surface audit later.
    household_id = Column(
        UUID(as_uuid=True),
        ForeignKey("households.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # --- Relationships ---
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.id} | {self.email}>"


class Household(Base):
    """
    Phase 6 stub — table must exist now so User.household_id FK resolves.
    No routes or logic built until Phase 6. Schema is minimal on purpose.
    """
    __tablename__ = "households"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), nullable=True)  # No FK loop — owner set after User creation
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    def __repr__(self) -> str:
        return f"<Household {self.id} | {self.name}>"