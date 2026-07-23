"""Stock reference-data model."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from src.core.db.database import Base


class Stock(Base):
    """A Tadawul-listed company.

    Reference data only -- no price history (see PriceBar) and no
    fundamentals (a later milestone's concern per the approved M2
    engineering blueprint).
    """

    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(16), nullable=False, unique=True, index=True)
    name_en = Column(String(255), nullable=False)
    name_ar = Column(String(255), nullable=True)
    sector = Column(String(128), nullable=True)
    currency = Column(String(3), nullable=False, default="SAR")
    lot_size = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    listed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    price_bars = relationship("PriceBar", back_populates="stock", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Stock symbol={self.symbol!r} name_en={self.name_en!r}>"
