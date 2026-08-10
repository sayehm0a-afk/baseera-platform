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
    industry = Column(String(128), nullable=True)
    exchange = Column(String(32), nullable=True)
    currency = Column(String(3), nullable=False, default="SAR", server_default="SAR")
    lot_size = Column(Integer, nullable=False, default=1, server_default="1")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    # Persisted result of universe_policy.classify_universe() the last
    # time a SAHMK directory sync (ingest_symbols.sync_symbols with
    # discover_all=True) saw this symbol -- e.g. "MAIN_MARKET_EQUITY",
    # "ETF_FUND", "REIT", "SUKUK_BOND", "RIGHTS_ISSUE", "SUSPENDED",
    # "INACTIVE_DELISTED". Null for a symbol that was only ever added
    # explicitly (never went through directory classification) or
    # ingested before this column existed. Kept as a durable,
    # SQL-queryable record (not just an in-process diagnostic that
    # resets on every deploy) so real universe-composition evidence
    # (exact ETF/REIT/sukuk counts) survives process restarts.
    instrument_bucket = Column(String(64), nullable=True)
    exclusion_reason = Column(String(255), nullable=True)
    listed_at = Column(DateTime(timezone=True), nullable=True)
    # Set whenever a per-symbol company-profile fetch was attempted for
    # sector/industry enrichment (sync_symbols.py), regardless of
    # whether it actually found a sector -- lets that job skip retrying
    # a symbol SAHMK genuinely has no sector data for on every run
    # forever, while still rechecking it periodically in case the
    # provider adds the data later. Never set for a symbol whose
    # sector came straight from the bulk directory pass (no per-symbol
    # call was made, nothing to bound).
    sector_checked_at = Column(DateTime(timezone=True), nullable=True)
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
    fundamental_snapshots = relationship(
        "FundamentalSnapshot", back_populates="stock", cascade="all, delete-orphan"
    )
    dividends = relationship("Dividend", back_populates="stock", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Stock symbol={self.symbol!r} name_en={self.name_en!r}>"
