"""PortfolioHolding: one position within one Portfolio -- quantity and
cost basis only, pure input data. Every analytical field (latest
price, market value, weight, recommendation, risk, ...) is computed
fresh by src.portfolio_intelligence at read/analyze time, never stored
here.

`symbol` is denormalized (also reachable via `stock`), the same
reasoning RecommendationSnapshot/SymbolIntelligenceRecord already
apply: a holding's identity should survive a later rename of the Stock
row it points to.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "stock_id", name="uq_portfolio_holding_identity"),
    )

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)

    quantity = Column(Numeric(18, 4), nullable=False)
    average_cost = Column(Numeric(18, 4), nullable=True)

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

    portfolio = relationship("Portfolio", back_populates="holdings")
    stock = relationship("Stock")

    def __repr__(self) -> str:
        return f"<PortfolioHolding portfolio_id={self.portfolio_id} symbol={self.symbol!r} quantity={self.quantity}>"
