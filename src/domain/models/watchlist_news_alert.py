"""WatchlistNewsAlert: one alert generated when a critical news event
affects a symbol on a user's personal watchlist -- the watchlist-side
mirror of PortfolioNewsAlert (RADAR-C Phase I). Durable, queryable
history of what the News Intelligence Engine flagged for a watched
symbol, and when. Every alert generated here also produces a
`Notification(type=MARKET_ALERT)` row -- this table is the structured,
queryable record; `Notification` is the existing per-user delivery/
read-tracking mechanism, reused rather than duplicated.

Reuses `PortfolioAlertType`/`AlertSeverity` rather than a second
identical enum pair -- the same UPGRADE/DOWNGRADE/HIGH_RISK/
MAJOR_OPPORTUNITY classification and INFO/WARNING/CRITICAL severity
scale apply to both a held position and a watched-but-unheld symbol.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base
from src.domain.models.market_alert import AlertSeverity
from src.domain.models.portfolio_news_alert import PortfolioAlertType


class WatchlistNewsAlert(Base):
    __tablename__ = "watchlist_news_alerts"

    id = Column(Integer, primary_key=True)
    watchlist_id = Column(Integer, ForeignKey("user_watchlists.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    news_event_id = Column(Integer, ForeignKey("news_events.id"), nullable=False, index=True)

    alert_type = Column(Enum(PortfolioAlertType), nullable=False, index=True)
    severity = Column(Enum(AlertSeverity), nullable=False)
    message = Column(Text, nullable=False)

    generated_at = Column(DateTime(timezone=True), nullable=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    watchlist = relationship("UserWatchlist")
    news_event = relationship("NewsEvent")

    def __repr__(self) -> str:
        return f"<WatchlistNewsAlert id={self.id} alert_type={self.alert_type} symbol={self.symbol!r}>"
