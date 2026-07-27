"""Invoice: one billing document for a user's subscription. `provider`
records which IPaymentProvider (src/billing/provider.py) generated it
-- always "noop" today (no real gateway is integrated yet, per Phase
10 decision "billing interfaces only, no gateway"), so no invoice can
ever legitimately reach PAID in this milestone; the column exists so
a future real provider's invoices are distinguishable from historical
noop ones without a backfill.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class InvoiceStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    VOID = "VOID"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True, index=True)

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="SAR", server_default="SAR")
    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.PENDING, server_default="PENDING")

    provider = Column(String(50), nullable=False, default="noop", server_default="noop")
    provider_reference = Column(String(255), nullable=True)

    issued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    paid_at = Column(DateTime(timezone=True), nullable=True)

    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} user_id={self.user_id} amount={self.amount} status={self.status}>"
