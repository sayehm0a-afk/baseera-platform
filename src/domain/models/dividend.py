"""Dividend record model."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class Dividend(Base):
    """One declared dividend for one stock, identified by its ex-date.

    `ex_date` is the natural identity key (a company does not declare
    two dividends with the same ex-date) -- the same upsert-by-natural-
    key discipline PriceBar (stock_id/timeframe/timestamp) and
    FundamentalSnapshot (stock_id/period_type/fiscal_period_end)
    already use, so ingest_dividends.py can be idempotent the same way
    ingest_ohlcv.py/ingest_fundamentals.py already are.
    """

    __tablename__ = "dividends"
    __table_args__ = (UniqueConstraint("stock_id", "ex_date", name="uq_dividend_identity"),)

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    ex_date = Column(Date, nullable=False, index=True)
    payment_date = Column(Date, nullable=True)
    amount_per_share = Column(Numeric(12, 4), nullable=False)
    # source/is_synthetic: same honesty discipline as FundamentalSnapshot
    # -- every value this platform stores must be traceable to whether
    # it's real (SAHMK) or synthetic (DevFundamentalDataProvider) data.
    source = Column(String(64), nullable=False)
    is_synthetic = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    stock = relationship("Stock", back_populates="dividends")

    def __repr__(self) -> str:
        return f"<Dividend stock_id={self.stock_id} ex_date={self.ex_date} amount={self.amount_per_share}>"
