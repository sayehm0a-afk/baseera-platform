"""Stock reference-data model."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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
    currency = Column(String(3), nullable=False, default="SAR", server_default="SAR")
    lot_size = Column(Integer, nullable=False, default=1, server_default="1")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    listed_at = Column(DateTime(timezone=True), nullable=True)
    # server_default (not just the Python-side `default=`) so any insert
    # that bypasses the SQLAlchemy ORM (raw SQL, a future async engine
    # path) still satisfies the NOT NULL constraint -- required for the
    # migration to be production-safe, not just correct via the ORM.
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

    price_bars = relationship("PriceBar", back_populates="stock", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Stock symbol={self.symbol!r} name_en={self.name_en!r}>"
