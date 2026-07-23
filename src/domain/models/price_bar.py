"""OHLCV price-bar model."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from src.core.db.database import Base


class Timeframe(str, enum.Enum):
    """Supported OHLCV bar intervals."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class PriceBar(Base):
    """A single OHLCV bar for one stock, one timeframe, one timestamp."""

    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint("stock_id", "timeframe", "timestamp", name="uq_price_bar_identity"),
    )

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    timeframe = Column(Enum(Timeframe), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Numeric(18, 4), nullable=False)
    high = Column(Numeric(18, 4), nullable=False)
    low = Column(Numeric(18, 4), nullable=False)
    close = Column(Numeric(18, 4), nullable=False)
    volume = Column(BigInteger, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    stock = relationship("Stock", back_populates="price_bars")

    def __repr__(self) -> str:
        return (
            f"<PriceBar stock_id={self.stock_id} timeframe={self.timeframe} "
            f"timestamp={self.timestamp!r} close={self.close}>"
        )
