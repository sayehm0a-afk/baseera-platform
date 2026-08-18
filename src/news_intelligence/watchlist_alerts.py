"""watchlist_alerts.py: WatchlistNewsAlertEngine -- the watchlist-side
mirror of `PortfolioNewsAlertEngine` (RADAR-C Phase I). Re-evaluates a
user's *watched-but-not-necessarily-owned* symbols whenever critical
news arrives, using the exact same classification rule
(`classify_alert_type`/`build_alert_message`, reused as-is -- both are
pure functions with no portfolio-specific assumption) so a watched
symbol and a held position are judged by one consistent bar, not two
divergent ones.

Every alert is persisted twice: once as a structured, queryable
`WatchlistNewsAlert` row, and once as a `Notification(type=MARKET_ALERT)`
row for the watchlist's owner -- reusing the existing per-user
notification feed rather than building a second delivery mechanism.
Idempotent: an alert is never generated twice for the same
(watchlist, news_event) pair.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.domain.models import (
    NewsCategory,
    NewsEntity,
    NewsEntityType,
    NewsEvent,
    Notification,
    NotificationType,
    UserWatchlist,
    WatchlistNewsAlert,
)
from src.news_intelligence.portfolio_alerts import _SEVERITY_BY_ALERT_TYPE, build_alert_message, classify_alert_type
from src.news_intelligence.types import WatchlistAlert


class WatchlistNewsAlertEngine:
    def generate_and_persist(
        self, session: Session, watchlist: UserWatchlist, symbols: List[str], since: Optional[datetime] = None
    ) -> List[WatchlistAlert]:
        """Scans each watched `symbols` entry for canonical, analyzed
        news events published since `since` (defaults to "no lower
        bound"), classifies each via the same rule
        `PortfolioNewsAlertEngine` uses, and persists any that clear
        the bar -- skipping any (watchlist, news_event) pair already
        alerted on."""
        alerts: List[WatchlistAlert] = []
        for symbol in symbols:
            query = (
                session.query(NewsEvent)
                .join(NewsEntity, NewsEntity.news_event_id == NewsEvent.id)
                .filter(
                    NewsEntity.entity_type == NewsEntityType.COMPANY,
                    NewsEntity.symbol == symbol,
                    NewsEvent.duplicate_of_id.is_(None),
                    NewsEvent.analyzed_at.isnot(None),
                )
            )
            if since is not None:
                query = query.filter(NewsEvent.published_at >= since)

            for event in query.all():
                alert_type = classify_alert_type(
                    event.category or NewsCategory.OTHER, event.sentiment_score or 0.0, event.confidence or 0.0
                )
                if alert_type is None:
                    continue

                already_alerted = (
                    session.query(WatchlistNewsAlert.id)
                    .filter_by(watchlist_id=watchlist.id, news_event_id=event.id)
                    .first()
                )
                if already_alerted is not None:
                    continue

                severity = _SEVERITY_BY_ALERT_TYPE[alert_type]
                message = build_alert_message(symbol, alert_type, event)
                generated_at = datetime.now(timezone.utc)

                alert_row = WatchlistNewsAlert(
                    watchlist_id=watchlist.id, symbol=symbol, news_event_id=event.id, alert_type=alert_type,
                    severity=severity, message=message, generated_at=generated_at,
                )
                session.add(alert_row)
                session.flush()  # populates alert_row.id before it's threaded into the returned dataclass
                if watchlist.user_id is not None:
                    session.add(
                        Notification(
                            user_id=watchlist.user_id, type=NotificationType.MARKET_ALERT,
                            title=f"{symbol}: {alert_type.value.replace('_', ' ').title()}", body=message,
                        )
                    )
                alerts.append(
                    WatchlistAlert(
                        id=alert_row.id, watchlist_id=watchlist.id, symbol=symbol, news_event_id=event.id,
                        alert_type=alert_type, severity=severity, message=message, generated_at=generated_at,
                    )
                )

        if alerts:
            session.commit()
        return alerts
