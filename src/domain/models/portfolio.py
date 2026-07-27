"""Portfolio: a named collection of holdings plus a cash balance --
pure reference data, no analysis. `Portfolio Intelligence` (Phase 8)
reads this and PortfolioHolding to run its analysis; neither model
computes or stores any score itself (see PortfolioAnalysisSnapshot for
the durable analysis record).

`user_id` (Phase 10, decision 4 -- "Virtual Portfolio" is cosmetic +
ownership, not a rename) is nullable at the DB level purely to keep
the migration adding it non-destructive against any pre-existing rows;
every route that creates or reads a portfolio (src/api/routes/
portfolio.py) always supplies/enforces it -- an unowned portfolio is
simply unreachable through the ownership-filtered API, not a
supported state going forward.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
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
