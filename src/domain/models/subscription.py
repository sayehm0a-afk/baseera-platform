"""Subscription: a user's customer-lifecycle state -- deliberately
separate from User.is_staff/staff_role (RBAC: "who works at Baseerah"),
per Phase 10 decision 1. `plan` and `status` are independent columns:
a TRIAL-plan subscription's `status` still moves TRIALING -> EXPIRED
on its own (lazy, at check-time -- see src.subscriptions.
subscription_service), and a MONTHLY/YEARLY subscription can
independently be ACTIVE, PAST_DUE, or CANCELED once real billing
exists (M10.7). One-to-one with User (unique user_id): every
registered user gets exactly one Subscription row, auto-provisioned
as a TRIAL at registration time (src.auth.user_service.register).
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class SubscriptionPlan(str, enum.Enum):
    TRIAL = "TRIAL"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", name="uq_subscription_user"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    plan = Column(Enum(SubscriptionPlan), nullable=False)
    status = Column(Enum(SubscriptionStatus), nullable=False)

    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False, server_default="false")

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    user = relationship("User", back_populates="subscription")

    def __repr__(self) -> str:
        return f"<Subscription id={self.id} user_id={self.user_id} plan={self.plan} status={self.status}>"
