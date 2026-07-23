"""Market/index-level snapshot model (e.g. TASI)."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.sql import func

from src.core.db.database import Base


class MarketSnapshot(Base):
    """A point-in-time snapshot of a market index (e.g. TASI)."""

    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint("index_name", "timestamp", name="uq_market_snapshot_identity"),
    )

    id = Column(Integer, primary_key=True)
    index_name = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    value = Column(Numeric(18, 4), nullable=False)
    change = Column(Numeric(18, 4), nullable=True)
    change_percent = Column(Numeric(9, 4), nullable=True)
    volume = Column(BigInteger, nullable=True)
    market_cap = Column(Numeric(24, 4), nullable=True)
    # server_default so a non-ORM insert still satisfies NOT NULL --
    # see stock.py for the same reasoning.
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketSnapshot index_name={self.index_name!r} "
            f"timestamp={self.timestamp!r} value={self.value}>"
        )
