"""PortfolioAnalysisSnapshot: the durable record of one
PortfolioEngine.analyze() run -- named scalar columns for the common
queryable fields (the same "five named columns + one JSON blob for the
complete record" pattern RecommendationSnapshot already established),
so `GET /portfolio/{id}` and friends can read the latest snapshot
without recomputing anything. `analysis_json` is the complete,
serialized `PortfolioAnalysis` (via
src.portfolio_intelligence.repository's serializer) -- the single
source of truth; the scalar columns are a queryable convenience over
the same data.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class PortfolioAnalysisSnapshot(Base):
    __tablename__ = "portfolio_analysis_snapshots"

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, index=True)

    total_value = Column(Numeric(18, 4), nullable=False)
    cash = Column(Numeric(18, 4), nullable=False)
    health_score = Column(Numeric(6, 2), nullable=False)
    risk_score = Column(Numeric(6, 2), nullable=False)
    risk_level = Column(String(16), nullable=False)
    diversification_score = Column(Numeric(6, 2), nullable=False)
    expected_volatility_annualized_pct = Column(Numeric(9, 4), nullable=True)
    estimated_max_drawdown_pct = Column(Numeric(9, 4), nullable=True)
    portfolio_beta = Column(Numeric(9, 4), nullable=True)

    analysis_json = Column(JSON, nullable=False)
    engine_version = Column(String(32), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    portfolio = relationship("Portfolio", back_populates="analysis_snapshots")

    def __repr__(self) -> str:
        return f"<PortfolioAnalysisSnapshot portfolio_id={self.portfolio_id} generated_at={self.generated_at!r}>"
