"""PortfolioNewsAlert: one alert generated when a critical news event
affects a held position -- durable, queryable history of what the
News Intelligence Engine flagged for a portfolio, and when. Reuses
`AlertSeverity` from `market_alert.py` rather than a second identical
enum (the same INFO/WARNING/CRITICAL scale applies to both). Every
alert generated here also produces a `Notification(type=PORTFOLIO_ALERT)`
row -- this table is the structured, queryable record; `Notification`
is the existing per-user delivery/read-tracking mechanism, reused
rather than duplicated.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base
from src.domain.models.market_alert import AlertSeverity


class PortfolioAlertType(str, enum.Enum):
    UPGRADE = "UPGRADE"
    DOWNGRADE = "DOWNGRADE"
    HIGH_RISK = "HIGH_RISK"
    MAJOR_OPPORTUNITY = "MAJOR_OPPORTUNITY"


class PortfolioNewsAlert(Base):
    __tablename__ = "portfolio_news_alerts"

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    news_event_id = Column(Integer, ForeignKey("news_events.id"), nullable=False, index=True)

    alert_type = Column(Enum(PortfolioAlertType), nullable=False, index=True)
    severity = Column(Enum(AlertSeverity), nullable=False)
    message = Column(Text, nullable=False)
    # Pre-launch safety fix (2026-08-22, Priority 2): Arabic presentation
    # companion to `message` -- nullable so rows written before this
    # column existed still read back cleanly (frontend falls back to
    # `message`). Never used by any decision/classification logic.
    message_ar = Column(Text, nullable=True)

    generated_at = Column(DateTime(timezone=True), nullable=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    portfolio = relationship("Portfolio")
    news_event = relationship("NewsEvent")

    def __repr__(self) -> str:
        return f"<PortfolioNewsAlert id={self.id} alert_type={self.alert_type} symbol={self.symbol!r}>"
