"""Portfolio: a named collection of holdings plus a cash balance --
pure reference data, no analysis. `Portfolio Intelligence` (Phase 8)
reads this and PortfolioHolding to run its analysis; neither model
computes or stores any score itself (see PortfolioAnalysisSnapshot for
the durable analysis record).

No user/ownership model exists yet anywhere in this codebase -- `name`
is a plain, non-unique label, the same "reference data only" scope
Stock itself has.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    cash_balance = Column(Numeric(18, 4), nullable=False, default=0, server_default="0")

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

    holdings = relationship("PortfolioHolding", back_populates="portfolio", cascade="all, delete-orphan")
    analysis_snapshots = relationship(
        "PortfolioAnalysisSnapshot", back_populates="portfolio", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Portfolio id={self.id} name={self.name!r}>"
