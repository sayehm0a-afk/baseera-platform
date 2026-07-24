"""Company financial-statement snapshot model."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class PeriodType(str, enum.Enum):
    """Reporting period granularity for a financial-statement snapshot."""

    ANNUAL = "annual"
    QUARTERLY = "quarterly"


class FundamentalSnapshot(Base):
    """One reported financial-statement snapshot for one stock, one
    period type, one fiscal period end date.

    Deliberately does not store a market price -- price-relative ratios
    (P/E, P/B, dividend yield, market cap) are computed by combining a
    snapshot with a separately-fetched PriceBar close, keeping this
    model purely about what a company reported, not what the market did
    with that information.
    """

    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "period_type", "fiscal_period_end", name="uq_fundamental_snapshot_identity"
        ),
    )

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    period_type = Column(Enum(PeriodType), nullable=False)
    fiscal_period_end = Column(Date, nullable=False, index=True)

    revenue = Column(Numeric(24, 4), nullable=False)
    gross_profit = Column(Numeric(24, 4), nullable=True)
    net_income = Column(Numeric(24, 4), nullable=False)
    total_assets = Column(Numeric(24, 4), nullable=False)
    total_liabilities = Column(Numeric(24, 4), nullable=False)
    total_equity = Column(Numeric(24, 4), nullable=False)
    current_assets = Column(Numeric(24, 4), nullable=False)
    current_liabilities = Column(Numeric(24, 4), nullable=False)
    inventory = Column(Numeric(24, 4), nullable=True)
    cash_and_equivalents = Column(Numeric(24, 4), nullable=True)
    total_debt = Column(Numeric(24, 4), nullable=True)
    shares_outstanding = Column(BigInteger, nullable=False)
    eps = Column(Numeric(12, 4), nullable=False)
    dividend_per_share = Column(Numeric(12, 4), nullable=False, default=0, server_default="0")

    # Provenance -- same labeling discipline as DevMarketDataProvider
    # (M2.1): every synthetic value must be traceable and never mistaken
    # for a real reported figure.
    source = Column(String(64), nullable=False)
    is_synthetic = Column(Boolean, nullable=False, default=False, server_default="false")

    # server_default (not just the Python-side `default=`) so any insert
    # that bypasses the SQLAlchemy ORM still satisfies the NOT NULL
    # constraint -- same reasoning as Stock/PriceBar/MarketSnapshot.
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    stock = relationship("Stock", back_populates="fundamental_snapshots")

    def __repr__(self) -> str:
        return (
            f"<FundamentalSnapshot stock_id={self.stock_id} period_type={self.period_type} "
            f"fiscal_period_end={self.fiscal_period_end!r}>"
        )
